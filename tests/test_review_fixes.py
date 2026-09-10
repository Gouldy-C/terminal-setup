"""Regressions found during independent install/update review."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import test_setup as existing

installer = existing.installer


class ReviewFixTests(unittest.TestCase):
    # Reuse the isolated home and committed local upstream fixture, without rerunning
    # the inherited integration tests under a second class.
    setUp = existing.InstallationTests.setUp
    tearDown = existing.InstallationTests.tearDown
    git = existing.InstallationTests.git
    commit = existing.InstallationTests.commit
    cli = existing.InstallationTests.cli
    install = existing.InstallationTests.install
    current = existing.InstallationTests.current
    release = existing.InstallationTests.release

    def legacy_startup(self):
        legacy = self.home / 'config/bash/bashrc'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes((existing.REPO / 'tests/fixtures/legacy-bashrc').read_bytes())
        expected_hash = json.loads((existing.REPO / 'legacy-hashes.json').read_text())['linux/bashrc']
        self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(), expected_hash)
        bashrc = self.home / '.bashrc'
        bashrc.write_text('source "' + str(legacy) + '"\n')
        login = self.home / '.profile'
        login.write_text('# personal login\n')
        return {path: path.read_bytes() for path in (legacy, bashrc, login)}

    def test_update_ignores_git_diff_presentation_preferences(self):
        self.install()
        config = self.home / 'gitconfig'
        config.write_text('[diff]\n    noprefix = true\n    mnemonicprefix = true\n[color]\n    ui = always\n')
        self.env['GIT_CONFIG_GLOBAL'] = str(config)
        local = self.release() / 'linux/bashrc'
        local.write_text(local.read_text() + '\n# personal comment\n')
        (self.origin / 'README.md').write_text('Unrelated upstream edit\n')
        sha = self.commit('unrelated update')
        self.cli('update')
        self.assertEqual(self.current()['revision'], sha)
        self.assertIn('# personal comment', (self.release() / 'linux/bashrc').read_text())

    def test_nested_untracked_repository_and_empty_directories_survive(self):
        self.install()
        nested = self.release() / 'personal-checkout'
        nested.mkdir()
        subprocess.run(['git', '-C', str(nested), 'init', '-q'], check=True, env=self.env)
        (nested / 'notes.txt').write_text('personal notes')
        (nested / 'empty').mkdir()
        outside = self.home / 'external'
        outside.mkdir()
        (outside / 'untouched').write_text('outside data')
        linked = False
        try:
            (nested / 'external-link').symlink_to(outside, target_is_directory=True)
            linked = True
        except OSError:
            pass  # Windows symlink creation may require Developer Mode.
        before = installer.local_fingerprint(self.release(), self.current()['revision'])
        if linked:
            (outside / 'untouched').write_text('changed outside data')
            self.assertEqual(installer.local_fingerprint(self.release(), self.current()['revision']), before)
        (nested / 'notes.txt').write_text('updated personal notes')
        self.assertNotEqual(installer.local_fingerprint(self.release(), self.current()['revision']), before)
        (self.origin / 'README.md').write_text('Unrelated update\n')
        self.commit('update with nested checkout')
        self.cli('update')
        copied = self.release() / nested.name
        self.assertEqual((copied / 'notes.txt').read_text(), 'updated personal notes')
        self.assertTrue((copied / 'empty').is_dir())
        self.assertEqual((copied / '.git/config').read_bytes(), (nested / '.git/config').read_bytes())
        if linked:
            self.assertTrue((copied / 'external-link').is_symlink())
            self.assertEqual(os.readlink(copied / 'external-link'), os.readlink(nested / 'external-link'))
            self.assertEqual((copied / 'external-link').resolve(), outside.resolve())
            self.assertEqual((outside / 'untouched').read_text(), 'changed outside data')

    @unittest.skipIf(os.name == 'nt', 'Legacy Bash symlink migration')
    def test_legacy_bashrc_symlink_is_preflighted_once(self):
        originals = self.legacy_startup()
        bashrc = self.home / '.bashrc'
        legacy = self.home / 'config/bash/bashrc'
        bashrc.unlink()
        bashrc.symlink_to(legacy)
        self.install()
        self.assertTrue(bashrc.is_symlink())
        self.assertEqual(legacy.read_text().count('# terminal-setup managed loader'), 1)
        backups = list((self.root / 'backups').glob('*/*'))
        self.assertIn(originals[legacy], [path.read_bytes() for path in backups])

    @unittest.skipIf(os.name == 'nt', 'Legacy Bash migration')
    def test_invalid_login_file_preflights_before_replacing_legacy_profile(self):
        originals = self.legacy_startup()
        login = self.home / '.profile'
        login.write_bytes(b'# legacy locale comment: \xff\n')
        originals[login] = login.read_bytes()
        result = self.cli('install', '--repo', self.origin, '--skip-tools', success=False)
        self.assertIn('not UTF-8', result.stderr)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / 'current.json').exists())
        self.assertFalse((self.root / 'load.bash').exists())
        self.assertFalse((self.root / 'user/profile.bash').exists())

    @unittest.skipIf(os.name == 'nt', 'Legacy Bash migration')
    def test_activation_failure_restores_written_hooks_and_settings(self):
        originals = self.legacy_startup()
        real_write = installer.atomic_write
        saw_written_hooks = []

        def fail_activation(path, data):
            if path == self.root / 'current.json':
                saw_written_hooks.append(b'managed loader' in (self.home / '.bashrc').read_bytes())
                raise OSError('simulated activation failure')
            return real_write(path, data)

        with mock.patch.dict(os.environ, self.env), mock.patch.object(installer, 'atomic_write', side_effect=fail_activation):
            with self.assertRaisesRegex(OSError, 'simulated activation failure'):
                installer.update(self.root, str(self.origin), skip_tools=True, install=True)
        self.assertEqual(saw_written_hooks, [True])
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        for name in ('current.json', 'settings.json', 'load.bash', 'user/profile.bash'):
            self.assertFalse((self.root / name).exists(), name)
        self.assertEqual(list((self.root / 'releases').iterdir()), [])

    @unittest.skipIf(os.name == 'nt', 'Bash startup edit during candidate installation')
    def test_user_edit_after_hook_staging_is_not_overwritten(self):
        originals = self.legacy_startup()
        target = self.origin / 'setup.py'
        target.write_text(target.read_text().replace(
            '    configure_shells(root, stage, settings)\n',
            '    configure_shells(root, stage, settings)\n'
            '    with (Path.home() / ".bashrc").open("a") as user_file:\n'
            '        user_file.write("# latest user edit\\n")\n'))
        self.commit('simulate user editing startup during candidate installation')
        result = self.cli('install', '--repo', self.origin, '--skip-tools', success=False)
        self.assertIn('Startup file changed', result.stderr)
        bashrc = self.home / '.bashrc'
        self.assertEqual(bashrc.read_bytes(), originals[bashrc] + b'# latest user edit\n')
        for path, original in originals.items():
            if path != bashrc:
                self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / 'current.json').exists())

    def test_rollback_keeps_edits_made_after_our_hook_write(self):
        first, second = self.home / 'startup', self.home / 'other-startup'
        first.write_text('original\n')
        changes = [installer.file_change(first, 'installed\n'), installer.file_change(second, 'other\n')]
        real_write = installer.atomic_write

        def concurrent_edit_then_failure(path, data):
            if path == second.resolve():
                first.write_text('latest user edit\n')
                raise OSError('simulated failure')
            return real_write(path, data)

        with mock.patch.object(installer, 'atomic_write', side_effect=concurrent_edit_then_failure):
            with self.assertRaisesRegex(OSError, 'simulated failure'):
                installer.apply_file_changes(self.root, changes)
        self.assertEqual(first.read_text(), 'latest user edit\n')

    def test_transition_profile_requires_exact_candidate_hash(self):
        profile = self.home / 'transitional-profile'
        pristine = '# terminal-setup transition-aware profile\n# defaults\n'
        profile.write_text(pristine)
        digest = hashlib.sha256(pristine.encode()).hexdigest()
        hook = '# terminal-setup managed loader\n# loader\n# end terminal-setup managed loader'
        installer.append_hook(self.root, profile, hook, transition_hash=digest)
        self.assertEqual(profile.read_text(encoding='utf-8-sig'), '\n' + hook + '\n')
        self.assertTrue(list((self.root / 'backups').glob('*/*')))
        edited = pristine + '# personal addition\n'
        profile.write_text(edited)
        with self.assertRaisesRegex(RuntimeError, 'local edits'):
            installer.append_hook(self.root, profile, hook, transition_hash=digest)
        self.assertEqual(profile.read_text(), edited)


if __name__ == '__main__':
    unittest.main()
