"""Offline integration tests against real Git repositories and isolated user homes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', REPO / 'setup.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='terminal setup spaces ')
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.root = self.home / 'data' / 'terminal setup'
        self.origin = self.base / 'upstream'
        shutil.copytree(REPO, self.origin, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        LOCALAPPDATA=str(self.home / 'AppData/Local'),
                        XDG_DATA_HOME=str(self.home / 'data'), XDG_CONFIG_HOME=str(self.home / 'config'),
                        TERMINAL_SETUP_HOME=str(self.root), TERMINAL_SETUP_AUTO_UPDATE='0',
                        XDG_CACHE_HOME=str(self.home / 'cache'),
                        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.env.pop('PSModulePath', None)
        self.profile = self.home / 'Documents/PowerShell/Microsoft.PowerShell_profile.ps1'
        self.git('init', '-b', 'main')
        self.commit('initial')

    def tearDown(self):
        shutil.rmtree(self.base, onerror=installer.remove_readonly)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-c', 'user.name=Test',
                                        '-c', 'user.email=test@example.invalid', '-C', str(self.origin), *args],
                                       env=self.env, stderr=subprocess.STDOUT)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def cli(self, command, *args, success=True):
        result = subprocess.run([sys.executable, str(REPO / 'setup.py'), command, '--root', str(self.root), *map(str, args)],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def install(self):
        return self.cli('install', '--repo', self.origin, '--skip-tools', '--powershell-profile', self.profile)

    def current(self):
        return json.loads((self.root / 'current.json').read_text())

    def release(self):
        return self.root / 'releases' / self.current()['directory']

    def test_install_repeat_preserves_user_files_and_startup(self):
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text('# personal PowerShell code\n')
        (self.home / '.bashrc').write_text('# personal bash code\n')
        self.install()
        custom = self.root / 'user/profile.bash'
        custom.write_text('export PERSONAL_VALUE=kept\n')
        theme = self.root / 'user/my_layout.omp.json'
        theme.write_text('{"custom":true}')
        startup = self.profile if os.name == 'nt' else self.home / '.bashrc'
        first = startup.read_bytes()
        self.install()
        self.assertEqual(startup.read_bytes(), first)
        self.assertEqual(custom.read_text(), 'export PERSONAL_VALUE=kept\n')
        self.assertEqual(theme.read_text(), '{"custom":true}')
        self.assertTrue(list((self.root / 'backups').glob('*/*')))

    @unittest.skipIf(os.name == 'nt', 'Bash bootstrap on Linux')
    def test_curl_style_stdin_bootstrap(self):
        environment = dict(self.env, TERMINAL_SETUP_REPO=str(self.origin))
        result = subprocess.run(['bash', '-s', '--', '--skip-tools'],
                                input=(REPO / 'install.sh').read_text(), env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'current.json').exists())

    @unittest.skipIf(os.name == 'nt', 'Bash startup on Linux')
    def test_login_preserves_bashrc_customizations_and_symlink(self):
        original = self.home / 'dotfiles/bashrc'
        original.parent.mkdir()
        original.write_text('export PERSONAL_STARTUP=loaded\n')
        original.chmod(0o600)
        (self.home / '.bashrc').symlink_to(original)
        self.install()
        self.assertTrue((self.home / '.bashrc').is_symlink())
        self.assertEqual(original.stat().st_mode & 0o777, 0o600)
        # Source the actual login file without /etc/profile changing the isolated HOME.
        result = subprocess.run(['bash', '--noprofile', '--norc', '-ic',
                                 'source "$HOME/.profile"; printf "%s" "$PERSONAL_STARTUP"'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.stdout, 'loaded', result.stderr)

    @unittest.skipIf(os.name == 'nt', 'Legacy Bash migration')
    def test_edited_legacy_profile_is_not_overwritten(self):
        legacy = self.home / 'config/bash/bashrc'
        legacy.parent.mkdir(parents=True)
        content = '# THIS FILE IS HASHED AND UPDATED AUTOMATICALLY\n# user modifications\n'
        legacy.write_text(content)
        result = self.cli('install', '--repo', self.origin, '--skip-tools', success=False)
        self.assertIn('local edits', result.stderr)
        self.assertEqual(legacy.read_text(), content)
        self.assertFalse((self.root / 'current.json').exists())

    def test_local_edit_during_install_stops_activation(self):
        self.install()
        old = self.current()
        target = self.origin / 'setup.py'
        target.write_text(target.read_text().replace('    configure_shells(root, stage, settings)',
            '    (active(root) / "edited-during-install.txt").write_text("latest change")\n'
            '    configure_shells(root, stage, settings)'))
        self.commit('simulate concurrent editing during dependency installation')
        result = self.cli('update', success=False)
        self.assertIn('changed during installation', result.stderr)
        self.assertEqual(self.current(), old)
        self.assertEqual((self.release() / 'edited-during-install.txt').read_text(), 'latest change')

    def test_settings_edited_during_install_are_preserved(self):
        self.install()
        old = self.current()
        target = self.origin / 'setup.py'
        target.write_text(target.read_text().replace('    configure_shells(root, stage, settings)',
            '    latest = read_json(root / "settings.json")\n'
            '    latest["auto_update"] = False\n'
            '    save_json(root / "settings.json", latest)\n'
            '    configure_shells(root, stage, settings)'))
        self.commit('simulate editing preferences during installation')
        result = self.cli('update', success=False)
        self.assertIn('Settings changed', result.stderr)
        self.assertEqual(self.current(), old)
        self.assertFalse(json.loads((self.root / 'settings.json').read_text())['auto_update'])

    def test_updates_entire_revision_and_runs_new_installer(self):
        self.install()
        old = self.release()
        (self.origin / 'my_layout.omp.json').write_text('{"version":3,"blocks":[]}\n')
        with (self.origin / 'setup.py').open('a') as stream:
            stream.write('\nif __name__ == "__main__" and "apply" in sys.argv:\n    (SOURCE / "new-installer-ran").write_text("yes")\n')
        sha = self.commit('new theme and setup logic')
        self.cli('update')
        self.assertEqual(self.current()['revision'], sha)
        self.assertTrue(old.is_dir())
        self.assertEqual((self.release() / 'new-installer-ran').read_text(), 'yes')
        before = self.current()
        self.cli('update')
        self.assertEqual(before, self.current())

    def test_clean_three_way_merge_and_untracked_data(self):
        self.install()
        old = self.release()
        with (old / 'linux/bashrc').open('a') as stream:
            stream.write('\n# local customization at the bottom\n')
        (old / 'personal notes.txt').write_text('keep this')
        target = self.origin / 'linux/bashrc'
        target.write_text('# upstream addition at the top\n' + target.read_text())
        self.commit('update defaults')
        self.cli('update')
        text = (self.release() / 'linux/bashrc').read_text()
        self.assertIn('upstream addition', text)
        self.assertIn('local customization', text)
        self.assertEqual((self.release() / 'personal notes.txt').read_text(), 'keep this')
        # Local edits remain detectable across a second update.
        (self.origin / 'README.md').write_text('new docs\n')
        self.commit('docs')
        self.cli('update')
        self.assertIn('local customization', (self.release() / 'linux/bashrc').read_text())

    def test_locally_committed_edits_are_preserved(self):
        self.install()
        local = self.release()
        with (local / 'linux/bashrc').open('a') as stream:
            stream.write('\n# committed personal change\n')
        subprocess.run(['git', '-C', str(local), 'add', 'linux/bashrc'], env=self.env, check=True)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        '-C', str(local), 'commit', '-qm', 'local change'], env=self.env, check=True)
        (self.origin / 'README.md').write_text('new docs')
        self.commit('docs')
        self.cli('update')
        self.assertIn('committed personal change', (self.release() / 'linux/bashrc').read_text())

    @unittest.skipIf(os.name == 'nt', 'Bash profile reload')
    def test_reload_uses_new_default_theme_and_preserves_custom_theme(self):
        self.install()
        old_theme = str(self.release() / 'my_layout.omp.json')
        (self.origin / 'my_layout.omp.json').write_text('{"version":3,"blocks":[]}')
        self.commit('new theme')
        command = ('source "$HOME/.bashrc"; printf "BEFORE=%s\\n" "$OMP_CONFIG"; '
                   'terminal_setup update; reload_profile; printf "AFTER=%s\\n" "$OMP_CONFIG"')
        result = subprocess.run(['bash', '--noprofile', '--norc', '-ic', command],
                                env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BEFORE=' + old_theme, result.stdout)
        self.assertIn('AFTER=' + str(self.release() / 'my_layout.omp.json'), result.stdout)
        custom = self.home / 'personal theme.json'
        result = subprocess.run(['bash', '--noprofile', '--norc', '-ic',
                                 'source "$HOME/.bashrc"; reload_profile; printf "%s" "$OMP_CONFIG"'],
                                env=dict(self.env, OMP_CONFIG=str(custom)), capture_output=True, text=True)
        self.assertEqual(result.stdout, str(custom), result.stderr)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell runtime required')
    def test_downloaded_bootstrap_with_legacy_native_argument_passing(self):
        downloaded = self.base / 'downloaded.ps1'
        shutil.copy2(REPO / 'install.ps1', downloaded)
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = ("$ErrorActionPreference='Stop'; $PSNativeCommandArgumentPassing='Legacy'; $PROFILE=" +
                   quote(self.profile) + '; & ' + quote(downloaded) + ' -SkipTools -Repo ' + quote(self.origin))
        result = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-Command', command], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'current.json').exists())

    def test_conflict_keeps_active_revision_and_data(self):
        self.install()
        old = self.current()
        local = self.release() / 'linux/bashrc'
        local.write_text(local.read_text().replace('alias gs=', 'alias personal_gs='))
        upstream = self.origin / 'linux/bashrc'
        upstream.write_text(upstream.read_text().replace('alias gs=', 'alias upstream_gs='))
        self.commit('conflicting alias')
        result = self.cli('update', success=False)
        self.assertIn('conflict', result.stderr.lower())
        self.assertEqual(self.current(), old)
        self.assertIn('personal_gs', local.read_text())

    def test_untracked_collision_does_not_overwrite_local_data(self):
        self.install()
        old = self.current()
        (self.release() / 'notes.txt').write_text('personal')
        (self.origin / 'notes.txt').write_text('upstream')
        self.commit('new file')
        self.cli('update', success=False)
        self.assertEqual(self.current(), old)
        self.assertEqual((self.release() / 'notes.txt').read_text(), 'personal')

    def test_offline_and_broken_release_leave_old_active(self):
        self.install()
        old = self.current()
        settings = json.loads((self.root / 'settings.json').read_text())
        settings['repo'] = str(self.base / 'missing-remote')
        (self.root / 'settings.json').write_text(json.dumps(settings))
        self.cli('update', success=False)
        self.assertEqual(self.current(), old)
        settings['repo'] = str(self.origin)
        (self.root / 'settings.json').write_text(json.dumps(settings))
        (self.origin / 'my_layout.omp.json').write_text('not json')
        self.commit('broken theme')
        self.cli('update', success=False)
        self.assertEqual(self.current(), old)

    def test_failed_dependency_install_does_not_activate(self):
        self.install()
        old = self.current()
        target = self.origin / 'setup.py'
        target.write_text(target.read_text().replace('validate(stage)\n    if not skip_tools:',
                                                    'validate(stage)\n    raise RuntimeError("dependency failed")\n    if not skip_tools:'))
        self.commit('failed dependency step')
        result = self.cli('update', success=False)
        self.assertIn('dependency failed', result.stderr)
        self.assertEqual(self.current(), old)
        self.assertEqual(len(list((self.root / 'releases').iterdir())), 1)

    def test_rollback_disables_updates(self):
        self.install()
        old = self.current()
        (self.origin / 'README.md').write_text('new docs')
        self.commit('docs')
        self.cli('update')
        self.cli('rollback')
        self.assertEqual(self.current(), old)
        self.assertFalse(json.loads((self.root / 'settings.json').read_text())['auto_update'])

    def test_concurrent_update_lock(self):
        self.install()
        with installer.update_lock(self.root) as acquired:
            self.assertTrue(acquired)
            result = self.cli('update')
            self.assertIn('Another installation', result.stdout)
        self.cli('update')

    def test_background_launch_installs_main(self):
        self.install()
        (self.origin / 'README.md').write_text('background update')
        sha = self.commit('launch update')
        self.env['TERMINAL_SETUP_AUTO_UPDATE'] = '1'
        self.cli('launch')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and self.current()['revision'] != sha:
            time.sleep(.1)
        self.assertEqual(self.current()['revision'], sha, (self.root / 'update.log').read_text())

    @unittest.skipIf(os.name == 'nt', 'Bash startup on Linux')
    def test_bash_interactive_once_noninteractive_silent_and_touch_safe(self):
        self.install()
        custom = self.root / 'user/profile.bash'
        custom.write_text('CUSTOM_LOADS=$(( ${CUSTOM_LOADS:-0} + 1 ))\nalias gs="git status --short"\n')
        data = self.home / 'keep.txt'
        data.write_text('important data')
        command = 'source "$HOME/.bashrc"; source "$HOME/.bashrc"; touch "$HOME/keep.txt"; printf "LOADS=%s\\n" "$CUSTOM_LOADS"; alias gs; type terminal_setup'
        result = subprocess.run(['bash', '--noprofile', '--norc', '-ic', command], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('LOADS=1', result.stdout)
        self.assertIn('git status --short', result.stdout)
        self.assertEqual(data.read_text(), 'important data')
        result = subprocess.run(['bash', '--noprofile', '--norc', '-c', 'source "$HOME/.bashrc"'], env=self.env, capture_output=True)
        self.assertEqual(result.stdout + result.stderr, b'')
        self.assertFalse((self.root / 'update.log').exists())

    @unittest.skipUnless(os.name == 'nt', 'PowerShell startup on Windows')
    def test_powershell_profile_customizations_and_nf(self):
        self.install()
        (self.root / 'user/profile.ps1').write_text('$global:CustomLoads += 1\nfunction gs { "custom status" }\n')
        data = self.home / 'keep.txt'
        data.write_text('important data')
        command = "$PROFILE='" + str(self.profile).replace("'", "''") + "'; . $PROFILE; . $PROFILE; nf '" + str(data).replace("'", "''") + "'; Write-Output \"LOADS=$CustomLoads\"; gs; ts status"
        for ps in ['powershell', 'pwsh']:
            if shutil.which(ps):
                result = subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', command], env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('LOADS=1', result.stdout)
                self.assertIn('custom status', result.stdout)
        self.assertEqual(data.read_text(), 'important data')


class DownloadTests(unittest.TestCase):
    def test_checksum_failure_never_enters_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = {'url': 'https://example.invalid/binary', 'sha256': '0' * 64}
            import io
            with mock.patch('urllib.request.urlopen', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                    installer.download(asset, root)
            self.assertFalse((root / 'cache' / asset['sha256']).exists())

    def test_utf16_profile_and_bom_settings_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / 'profile.ps1'
            profile.write_text('# personal café\n', encoding='utf-16')
            hook = '# terminal-setup managed loader\n# café'
            installer.append_hook(root, profile, hook)
            installer.append_hook(root, profile, hook)
            self.assertEqual(profile.read_text(encoding='utf-16').count('managed loader'), 1)
            self.assertIn('personal café', profile.read_text(encoding='utf-16'))
            settings = root / 'settings.json'
            settings.write_text('{"auto_update": false}', encoding='utf-8-sig')
            self.assertFalse(installer.read_json(settings)['auto_update'])

    def test_subprocess_deadline(self):
        start = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            installer.run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.2)
        self.assertLess(time.monotonic() - start, 5)

    def test_module_archive_rejects_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'module.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('../../escape.ps1', 'bad')
            installer.save_json(root / 'tools.json', {'powershell_modules': {'PSReadLine': {'version': '2.4.5'}}})
            with mock.patch.object(installer, 'download', return_value=archive):
                with self.assertRaisesRegex(RuntimeError, 'Unsafe module archive path'):
                    installer.install_powershell_modules(root, root)
            self.assertFalse((root / 'escape.ps1').exists())

    @unittest.skipIf(os.name == 'nt', 'Linux font path; native Windows smoke covers registration')
    def test_font_upgrade_retains_old_and_customized_files(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'font.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('font.ttf', b'new font')
            legacy = root / 'fonts/font.ttf'
            legacy.parent.mkdir()
            legacy.write_bytes(b'legacy custom font')
            asset = {'sha256': 'a' * 64, 'member': 'font.ttf'}
            with mock.patch.dict(os.environ, XDG_DATA_HOME=str(root)), \
                 mock.patch.object(installer, 'download', return_value=archive), \
                 mock.patch.object(installer, 'run'):
                first = installer.install_font(root, asset)
                first.write_bytes(b'personal edit')
                installer.install_font(root, asset)
                second = installer.install_font(root, dict(asset, sha256='b' * 64))
            self.assertEqual(legacy.read_bytes(), b'legacy custom font')
            self.assertEqual(first.read_bytes(), b'personal edit')
            self.assertEqual(second.read_bytes(), b'new font')
            self.assertNotEqual(first, second)

    def test_windows_and_linux_ship_same_tools(self):
        manifest = json.loads((REPO / 'tools.json').read_text())
        for tools in manifest['platforms'].values():
            self.assertEqual(set(tools), {'oh-my-posh', 'zoxide', 'eza'})
            for asset in tools.values():
                self.assertEqual(len(asset['sha256']), 64)


if __name__ == '__main__':
    unittest.main()
