#!/usr/bin/env python3
"""Shared, standard-library-only installer and transactional updater (Python 3.10+)."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
import zipfile

DEFAULT_REPO = 'https://github.com/Gouldy-C/terminal-setup.git'
WINDOWS = os.name == 'nt'
SOURCE = Path(__file__).resolve().parent


def run(args, cwd=None, timeout=90, data=None):
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {'start_new_session': True}
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1')
    if Path(str(args[0])).stem.lower() in ('powershell', 'pwsh'):
        # A Core parent's module path can make Windows PowerShell load incompatible built-ins.
        environment.pop('PSModulePath', None)
    with subprocess.Popen([str(a) for a in args], cwd=cwd,
                          stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=environment,
                          **options) as process:
        try:
            output, errors = process.communicate(data, timeout=timeout)
        except subprocess.TimeoutExpired:
            # Git's HTTP/SSH helpers can inherit pipes; kill the whole process tree.
            if WINDOWS:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RuntimeError(f'{args[0]} timed out after {timeout} seconds') from None
        if process.returncode:
            raise RuntimeError(errors.decode(errors='replace').strip() or
                               f'{args[0]} exited with {process.returncode}')
        return output


def git(path, *args, **kwargs):
    return run(['git', '-c', 'core.autocrlf=false', '-c', 'credential.helper=',
                '-c', 'core.hooksPath=' + os.devnull, '-C', path, *args], **kwargs)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('wb') as stream:
            stream.write(data.encode('utf-8') if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_json(path, value):
    atomic_write(path, json.dumps(value, indent=2) + '\n')


def default_root():
    if os.environ.get('TERMINAL_SETUP_HOME'):
        return Path(os.environ['TERMINAL_SETUP_HOME']).expanduser().resolve()
    if WINDOWS:
        return Path(os.environ['LOCALAPPDATA']) / 'terminal-setup'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'terminal-setup'


def active(root):
    state = read_json(root / 'current.json')
    if not state:
        return None
    name = state['directory']
    if Path(name).name != name or name in ('.', '..'):
        raise RuntimeError('Invalid current.json release directory')
    release = root / 'releases' / name
    if not (release / 'setup.py').is_file():
        raise RuntimeError('Active release is missing; reinstall to repair it.')
    return release


@contextlib.contextmanager
def update_lock(root):
    """OS-held locks recover automatically after a crash, including on Windows."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'update.lock').open('a+b') as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if WINDOWS:
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            if WINDOWS:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def edit_patch(release, base_revision):
    # Machine-consumed patches must not inherit presentation or conversion settings.
    return git(release, 'diff', '--binary', '--no-color', '--no-ext-diff', '--no-textconv',
               '--src-prefix=a/', '--dst-prefix=b/', base_revision, '--', '.')


def untracked_paths(release):
    """Git emits a directory for nested repositories; include their complete local data."""
    def walk(path):
        yield path
        if path.is_dir() and not path.is_symlink():
            for child in sorted(path.iterdir()):
                yield from walk(child)

    for raw in git(release, 'ls-files', '--others', '-z').split(b'\0'):
        if raw and Path(os.fsdecode(raw)).parts[0] != '.tools':
            yield from walk(release / os.fsdecode(raw))


def local_fingerprint(release, base_revision):
    if not release:
        return None
    digest = hashlib.sha256(edit_patch(release, base_revision))
    for path in untracked_paths(release):
        digest.update(os.fsencode(path.relative_to(release)) + b'\0')
        if path.is_symlink():
            kind, content = b'link', os.fsencode(os.readlink(path))
        elif path.is_dir():
            kind, content = b'directory', b''
        else:
            kind, content = b'file', path.read_bytes()
        digest.update(kind + b'\0' + hashlib.sha256(content).digest())
    return digest.digest()


def preserve_edits(old, stage, base_revision):
    if not old:
        return
    patch = edit_patch(old, base_revision)
    if patch:
        git(stage, 'fetch', '--quiet', str(old), base_revision)
        try:
            git(stage, 'apply', '--3way', '--index', '-', data=patch)
        except RuntimeError as exc:
            raise RuntimeError('Local edits conflict with main. The active release is unchanged. '
                               'Resolve your edits there, then run the update again.\n' + str(exc)) from exc
    # Include ignored files and nested repositories; never follow local symlinks.
    for source in untracked_paths(old):
        relative = source.relative_to(old)
        target = stage / relative
        if any(parent.is_symlink() for parent in target.parents if parent != stage and stage in parent.parents):
            raise RuntimeError(f'New main conflicts with local file {relative}; parent is a symlink.')
        if target.exists() or target.is_symlink():
            if source.is_symlink() and target.is_symlink() and os.readlink(source) == os.readlink(target):
                continue
            if not source.is_symlink() and not target.is_symlink():
                if source.is_dir() and target.is_dir():
                    continue
                if source.is_file() and target.is_file() and source.read_bytes() == target.read_bytes():
                    continue
            raise RuntimeError(f'New main conflicts with local file {relative}; active release unchanged.')
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
        elif source.is_dir():
            target.mkdir()
        else:
            shutil.copy2(source, target)


def validate(stage):
    for name in ('setup.py', 'linux/bashrc', 'windows/Microsoft.PowerShell_profile.ps1',
                 'tools.json', 'my_layout.omp.json', 'linux/profile.bash', 'windows/profile.ps1'):
        if not (stage / name).is_file():
            raise RuntimeError(f'Incomplete release: {name} is missing')
    compile((stage / 'setup.py').read_bytes(), str(stage / 'setup.py'), 'exec')
    read_json(stage / 'my_layout.omp.json')
    read_json(stage / 'tools.json')
    if not WINDOWS:
        for name in ('install.sh', 'linux/setup.sh', 'linux/bashrc', 'linux/profile.bash'):
            run(['bash', '-n', stage / name])
    ps = shutil.which('pwsh') or shutil.which('powershell')
    if ps:
        for path in [stage / 'install.ps1', *sorted((stage / 'windows').glob('*.ps1'))]:
            escaped = str(path).replace("'", "''")
            command = "$e=$null; $t=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('" + escaped + "',[ref]$t,[ref]$e); if($e.Count){$e | Out-String | Write-Error; exit 1}"
            run([ps, '-NoProfile', '-NonInteractive', '-Command', command])


def download(asset, root):
    digest = asset['sha256']
    if len(digest) != 64:
        raise RuntimeError('Missing download checksum')
    cache = root / 'cache' / digest
    if cache.exists() and hashlib.sha256(cache.read_bytes()).hexdigest() == digest:
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    # Bounded by the parent apply process as well as per-socket timeouts.
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'terminal-setup'})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f"Checksum mismatch: {asset['url']}")
    atomic_write(cache, data)
    return cache


def extract_file(archive, member_name):
    """Read a single regular file without extracting archive paths to disk."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            matches = [n for n in bundle.namelist() if Path(n).name == member_name]
            if len(matches) != 1:
                raise RuntimeError(f'Expected one {member_name} in archive')
            return bundle.read(matches[0])
    with tarfile.open(archive) as bundle:
        matches = [m for m in bundle.getmembers() if m.isfile() and Path(m.name).name == member_name]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one {member_name} in archive')
        with bundle.extractfile(matches[0]) as stream:
            return stream.read()


def install_powershell_modules(root, stage):
    modules = read_json(stage / 'tools.json').get('powershell_modules', {})
    for name, asset in modules.items():
        destination = stage / '.tools' / 'modules' / name / asset['version']
        with zipfile.ZipFile(download(asset, root)) as archive:
            for member in archive.infolist():
                relative = PurePosixPath(member.filename)
                if relative.is_absolute() or '..' in relative.parts or '\\' in member.filename or ':' in member.filename:
                    raise RuntimeError(f'Unsafe module archive path: {member.filename}')
                if not member.is_dir():
                    atomic_write(destination.joinpath(*relative.parts), archive.read(member))
        manifest = destination / (name + '.psd1')
        if not manifest.is_file():
            raise RuntimeError(f'Missing module manifest: {manifest}')
        # Verify imports in fresh processes; never change a module loaded in the user's session.
        for executable in ('powershell', 'pwsh'):
            ps = shutil.which(executable)
            if ps:
                path = str(manifest).replace("'", "''")
                version = asset['version']
                command = ("$ErrorActionPreference='Stop'; $m = Import-Module '" + path + "' -PassThru; "
                           "if ($m.Version -ne [version]'" + version + "') { throw 'Module version mismatch' }")
                run([ps, '-NoProfile', '-NonInteractive', '-Command', command])


def install_tools(root, stage):
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(machine, machine)
    target = ('windows' if WINDOWS else 'linux') + '-' + arch
    manifest = read_json(stage / 'tools.json')
    if target not in manifest['platforms']:
        raise RuntimeError(f'Unsupported platform {target}. Use --skip-tools for profile-only setup.')
    directory = stage / '.tools'
    directory.mkdir(exist_ok=True)
    for name, asset in manifest['platforms'][target].items():
        archive = download(asset, root)
        content = extract_file(archive, asset['member']) if asset.get('member') else archive.read_bytes()
        binary = directory / (name + ('.exe' if WINDOWS else ''))
        atomic_write(binary, content)
        binary.chmod(0o755)
        run([binary, '--version'], timeout=15)
    if WINDOWS:
        install_powershell_modules(root, stage)
    install_font(root, manifest['font'])


def install_font(root, font):
    font_dir = (Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Windows/Fonts' if WINDOWS else
                Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'fonts')
    # A new archive gets a new directory; existing user/legacy font files are retained.
    font_dir = font_dir / 'terminal-setup' / font['sha256']
    font_path = font_dir / font['member']
    if not font_path.exists():
        atomic_write(font_path, extract_file(download(font, root), font['member']))
    if WINDOWS:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
            winreg.SetValueEx(key, 'CaskaydiaCove Nerd Font Mono Regular (TrueType)', 0, winreg.REG_SZ, str(font_path))
        import ctypes
        ctypes.windll.gdi32.AddFontResourceW(str(font_path))
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 2, 1000, None)
    elif shutil.which('fc-cache'):
        run(['fc-cache', '-f', font_dir], timeout=60)

    return font_path


def backup(root, path):
    destination = root / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]) / path.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(path, destination)
    return destination


def file_change(path, data, keep_backup=False):
    path = path.expanduser().resolve()
    original = path.read_bytes() if path.exists() else None
    return {'path': str(path), 'before': original.hex() if original is not None else None,
            'after': (data.encode('utf-8') if isinstance(data, str) else data).hex(),
            'backup': keep_backup}


def apply_file_changes(root, changes):
    """Preflight every file, then restore our writes on failure without erasing newer edits."""
    unique = {}
    for change in changes:
        previous = unique.setdefault(change['path'], change)
        if previous != change:
            raise RuntimeError(f"Conflicting startup changes for {change['path']}")
    changes = list(unique.values())

    def contents(path):
        return path.read_bytes().hex() if path.exists() else None

    def check(change):
        if contents(Path(change['path'])) != change['before']:
            raise RuntimeError(f"Startup file changed during installation: {change['path']}; retry to keep your edits.")

    for change in changes:
        check(change)
    written = []
    try:
        for change in changes:
            check(change)
            if change['before'] == change['after']:
                continue
            path = Path(change['path'])
            if change['backup'] and change['before'] is not None:
                backup(root, path)
            atomic_write(path, bytes.fromhex(change['after']))
            written.append(change)
    except BaseException:
        for change in reversed(written):
            path = Path(change['path'])
            if contents(path) != change['after']:
                # A user edited this file after our write; their latest version wins.
                continue
            if change['before'] is None:
                path.unlink()
            else:
                atomic_write(path, bytes.fromhex(change['before']))
        raise


def hook_change(root, path, hook, legacy_hash=None, transition_hash=None):
    # Preserve dotfile-manager links, Windows UTF-16 profiles, and UTF-8 BOMs.
    path = path.expanduser().resolve()
    change = file_change(path, b'', keep_backup=True)
    original = bytes.fromhex(change['before']) if change['before'] is not None else b''
    encoding = 'utf-16' if original.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
    try:
        text = original.decode(encoding)
        if WINDOWS and encoding == 'utf-8':
            encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        if not WINDOWS:
            raise RuntimeError(f'{path} is not UTF-8; convert it before installing.') from None
        encoding = 'mbcs'
        text = original.decode(encoding)
    if '# terminal-setup managed loader' in text:
        if hook not in text.replace('\r\n', '\n'):
            raise RuntimeError(f'{path} contains a different or edited terminal-setup loader. '
                               'Keep your changes and remove that loader block before reinstalling.')
        change['after'] = original.hex()
        return change
    transitional = '# terminal-setup transition-aware profile' in text
    if 'THIS FILE IS HASHED AND UPDATED AUTOMATICALLY' in text or transitional:
        # Refuse to execute an old updater alongside the new updater.
        normalized_hash = hashlib.sha256(text.replace('\r\n', '\n').encode()).hexdigest()
        if normalized_hash != (transition_hash if transitional else legacy_hash):
            raise RuntimeError(f'Legacy profile {path} has local edits. Move those edits to the user override '
                               'file and remove the old profile before retrying. Nothing was overwritten.')
        text = ''
    change['after'] = (text + '\n' + hook + '\n').encode(encoding).hex()
    return change


def append_hook(root, path, hook, legacy_hash=None, transition_hash=None):
    apply_file_changes(root, [hook_change(root, path, hook, legacy_hash, transition_hash)])


def configure_shells(root, stage, settings):
    changes = []
    user = root / 'user'
    user.mkdir(exist_ok=True, mode=0o700)
    for src, dest in [('linux/profile.bash', 'profile.bash'), ('windows/profile.ps1', 'profile.ps1')]:
        if not (user / dest).exists():
            changes.append(file_change(user / dest, (stage / src).read_bytes()))
    hashes = read_json(stage / 'legacy-hashes.json', {})
    def transition_hash(name):
        return hashlib.sha256((stage / name).read_text(encoding='utf-8-sig').replace('\r\n', '\n').encode()).hexdigest()
    if WINDOWS:
        profiles = settings.get('powershell_profiles', [])
        if not profiles:
            raise RuntimeError('Run install.ps1 from PowerShell to discover the real profile path.')
        ps_root = str(root).replace("'", "''")
        hook = ("# terminal-setup managed loader\n"
                "$global:TerminalSetupRoot = '" + ps_root + "'\n"
                "if (Test-Path -LiteralPath \"$TerminalSetupRoot\\current.json\") {\n"
                "    $tsState = Get-Content -LiteralPath \"$TerminalSetupRoot\\current.json\" -Raw | ConvertFrom-Json\n"
                "    . (Join-Path \"$TerminalSetupRoot\\releases\" (Join-Path $tsState.directory 'windows\\Microsoft.PowerShell_profile.ps1'))\n"
                "}\n# end terminal-setup managed loader")
        for profile in profiles:
            changes.append(hook_change(root, Path(profile), hook, hashes.get('windows/Microsoft.PowerShell_profile.ps1'), transition_hash('windows/Microsoft.PowerShell_profile.ps1')))
    else:
        import shlex
        # Resolve the pointer in Python so paths with spaces, quotes, and Unicode are preserved.
        loader = root / 'load.bash'
        changes.append(file_change(loader, '# Generated loader; customize user/profile.bash.\n'
                     'case $- in *i*) ;; *) return ;; esac\n'
                     '[[ ${_TERMINAL_SETUP_LOADED:-} == 1 ]] && return\n'
                     '_TERMINAL_SETUP_LOADED=1\n'
                     'export TERMINAL_SETUP_HOME=' + shlex.quote(str(root)) + '\n'
                     '_ts_release=$(' + shlex.quote(sys.executable) + ' -c ' +
                     shlex.quote('import json,pathlib,sys; r=pathlib.Path(sys.argv[1]); print(r/"releases"/json.loads((r/"current.json").read_text())["directory"])') +
                     ' "$TERMINAL_SETUP_HOME" 2>/dev/null)\n'
                     '[[ -f "$_ts_release/linux/bashrc" ]] && source "$_ts_release/linux/bashrc"\n'))
        hook = '# terminal-setup managed loader\n[ -n "${BASH_VERSION:-}" ] && [ -r ' + shlex.quote(str(loader)) + ' ] && . ' + shlex.quote(str(loader)) + '\n# end terminal-setup managed loader'
        # Migrate the old managed location only if it is the unmodified repository profile.
        legacy = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'bash/bashrc'
        if legacy.exists() and any(marker in legacy.read_bytes() for marker in
                                   (b'THIS FILE IS HASHED AND UPDATED AUTOMATICALLY', b'# terminal-setup transition-aware profile')):
            changes.append(hook_change(root, legacy, hook, hashes.get('linux/bashrc'), transition_hash('linux/bashrc')))
        changes.append(hook_change(root, Path.home() / '.bashrc', hook, hashes.get('linux/bashrc'), transition_hash('linux/bashrc')))
        # Bash reads only the first existing login file. Keep POSIX .profile syntax valid.
        login = next((Path.home() / n for n in ('.bash_profile', '.bash_login', '.profile') if (Path.home() / n).exists()), Path.home() / '.profile')
        login_hook = ('# terminal-setup managed loader\n'
                      'if [ -n "${BASH_VERSION:-}" ] && [ "${_TERMINAL_SETUP_LOADED:-}" != 1 ]; then\n'
                      '    case $- in *i*) [ -r "$HOME/.bashrc" ] && . "$HOME/.bashrc" ;; esac\n'
                      'fi\n# end terminal-setup managed loader')
        changes.append(hook_change(root, login, login_hook))
    save_json(stage / '.startup-plan.json', changes)
    settings['python'] = sys.executable


def apply(root, stage, settings, skip_tools):
    validate(stage)
    if not skip_tools:
        install_tools(root, stage)
    configure_shells(root, stage, settings)
    save_json(stage / '.install-result.json', settings)


def update(root, repo=None, skip_tools=False, profile=None, install=False):
    with update_lock(root) as acquired:
        if not acquired:
            print('Another installation or update is running.')
            return
        settings_path = root / 'settings.json'
        settings_before = settings_path.read_bytes() if settings_path.exists() else None
        settings = read_json(settings_path, {})
        if repo:
            settings['repo'] = repo
        repo = settings.get('repo', DEFAULT_REPO)
        if install:
            settings['skip_tools'] = skip_tools
        if profile:
            settings['powershell_profiles'] = sorted(set(settings.get('powershell_profiles', []) + [profile]))
        old = active(root)
        base_revision = read_json(root / 'current.json', {}).get('revision')
        # Query the actual main ref, with no ICMP or unrelated connectivity probe.
        remote = run(['git', '-c', 'credential.helper=', 'ls-remote', '--exit-code', '--', repo, 'refs/heads/main'], timeout=15).decode().split()
        if len(remote) != 2 or len(remote[0]) not in (40, 64):
            raise RuntimeError('Could not resolve main to a commit')
        sha = remote[0]
        if old and read_json(root / 'current.json')['revision'] == sha and not install:
            print('Already up to date: ' + sha[:12])
            return
        releases = root / 'releases'
        releases.mkdir(exist_ok=True)
        stage = releases / (sha[:12] + '-' + uuid.uuid4().hex[:8])
        try:
            stage.mkdir()
            git(stage, 'init', '--quiet')
            git(stage, 'remote', 'add', 'origin', repo)
            git(stage, 'fetch', '--quiet', '--depth=1', 'origin', sha)
            git(stage, 'checkout', '--quiet', '--detach', 'FETCH_HEAD')
            original_edits = local_fingerprint(old, base_revision)
            preserve_edits(old, stage, base_revision)
            validate(stage)
            # The incoming revision owns installation logic, including future dependency changes.
            request = root / ('apply-' + uuid.uuid4().hex + '.json')
            try:
                save_json(request, settings)
                args = [sys.executable, stage / 'setup.py', 'apply', '--root', root, '--request', request]
                if settings.get('skip_tools'):
                    args.append('--skip-tools')
                result = run(args, timeout=600)
                if result:
                    print(result.decode(errors='replace').strip())
            finally:
                request.unlink(missing_ok=True)
            settings = read_json(stage / '.install-result.json')
            (stage / '.install-result.json').unlink()
            if original_edits != local_fingerprint(old, base_revision):
                raise RuntimeError('Local files changed during installation; retry to include the latest edits.')
            settings_now = settings_path.read_bytes() if settings_path.exists() else None
            if settings_now != settings_before:
                raise RuntimeError('Settings changed during installation; retry to keep the latest settings.')
            # One atomic pointer switch activates the complete profile + theme + tools together.
            previous = read_json(root / 'current.json')
            changes = read_json(stage / '.startup-plan.json', [])
            for name, value in [('previous.json', previous), ('settings.json', settings),
                                ('current.json', {'revision': sha, 'directory': stage.name})]:
                if value is not None:
                    change = file_change(root / name, json.dumps(value, indent=2) + '\n')
                    if name == 'settings.json':
                        change['before'] = settings_before.hex() if settings_before is not None else None
                    changes.append(change)
            apply_file_changes(root, changes)
            (stage / '.startup-plan.json').unlink(missing_ok=True)
            print('Installed main at ' + sha[:12] + '. Open a new terminal to load it.')
            print('Customizations: ' + str(root / 'user'))
        except BaseException:
            # A candidate is disposable; the old release and user data never are.
            current = read_json(root / 'current.json', {})
            if stage.exists() and current.get('directory') != stage.name:
                shutil.rmtree(stage, onerror=remove_readonly)
            raise


def remove_readonly(func, path, _exc):
    os.chmod(path, 0o700)
    func(path)


def launch(root):
    settings = read_json(root / 'settings.json', {})
    if not settings.get('auto_update', True) or os.environ.get('TERMINAL_SETUP_AUTO_UPDATE', '1') == '0':
        return
    release = active(root)
    if not release:
        return
    with (root / 'update.log').open('ab') as log:
        options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {'start_new_session': True}
        subprocess.Popen([sys.executable, str(release / 'setup.py'), 'update', '--root', str(root)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **options)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'update', 'launch', 'status', 'rollback', 'apply'])
    parser.add_argument('--root', type=Path, default=default_root())
    parser.add_argument('--repo')
    parser.add_argument('--skip-tools', action='store_true')
    parser.add_argument('--powershell-profile')
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if args.command in ('install', 'update'):
        update(root, args.repo, args.skip_tools, args.powershell_profile, args.command == 'install')
    elif args.command == 'apply':
        if not args.request:
            parser.error('apply requires --request')
        apply(root, SOURCE, read_json(args.request), args.skip_tools)
    elif args.command == 'launch':
        launch(root)
    elif args.command == 'status':
        print(json.dumps({'root': str(root), 'current': read_json(root / 'current.json'),
                          'settings': read_json(root / 'settings.json')}, indent=2))
    elif args.command == 'rollback':
        with update_lock(root) as acquired:
            if not acquired:
                raise RuntimeError('An update is running; try again later.')
            previous = read_json(root / 'previous.json')
            if not previous or not (root / 'releases' / previous['directory']).is_dir():
                raise RuntimeError('No previous installation is available.')
            current = read_json(root / 'current.json')
            settings = read_json(root / 'settings.json')
            settings['auto_update'] = False
            save_json(root / 'settings.json', settings)
            save_json(root / 'current.json', previous)
            save_json(root / 'previous.json', current)
            print('Rolled back. Auto-updates disabled in settings.json; open a new terminal.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f'terminal-setup: {error}', file=sys.stderr)
        sys.exit(1)
