"""Network smoke test: full bootstrap, real binaries/fonts, profile initialization."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import importlib.util

REPO = Path(__file__).resolve().parents[1]
base = Path(tempfile.mkdtemp(prefix='terminal-setup-smoke-'))
home = base / 'home'
home.mkdir()
origin = base / 'origin'
shutil.copytree(REPO, origin, ignore=shutil.ignore_patterns('.git', '__pycache__'))
os.environ.update(HOME=str(home), USERPROFILE=str(home), LOCALAPPDATA=str(home / 'AppData/Local'),
                  XDG_DATA_HOME=str(home / 'data'), XDG_CONFIG_HOME=str(home / 'config'),
                  XDG_CACHE_HOME=str(home / 'cache'),
                  TERMINAL_SETUP_HOME=str(home / 'terminal-setup'), TERMINAL_SETUP_AUTO_UPDATE='0',
                  TERMINAL_SETUP_REPO=str(origin), GIT_CONFIG_GLOBAL=os.devnull)
# Let each PowerShell edition construct its own standard module search path.
os.environ.pop('PSModulePath', None)
for args in [('init', '-b', 'main'), ('add', '.'),
             ('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')]:
    subprocess.run(['git', '-C', str(origin), *args], check=True)
if os.name == 'nt':
    # Avoid touching the real runner profile: pass the isolated path through $PROFILE.
    profile = home / 'Documents/PowerShell/Microsoft.PowerShell_profile.ps1'
    quote = lambda path: "'" + str(path).replace("'", "''") + "'"
    downloaded = base / 'install.ps1'
    shutil.copy2(origin / 'install.ps1', downloaded)
    for ps in ['powershell', 'pwsh']:
        if not shutil.which(ps):
            continue
        for launcher in [origin / 'install.ps1', downloaded]:
            command = "$PROFILE=" + quote(profile) + '; & ' + quote(launcher)
            subprocess.run([ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', command], check=True)
        command = "$ErrorActionPreference='Stop'; $PROFILE=" + quote(profile) + '; . $PROFILE; oh-my-posh --version; zoxide --version; eza --version; ts status'
        subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', command], check=True)
else:
    subprocess.run(['bash', str(origin / 'install.sh')], check=True)
    subprocess.run(['bash', '--noprofile', '--norc', '-ic',
                    'set -e\nsource "$HOME/.bashrc"\noh-my-posh --version\nzoxide --version\neza --version\nts status'], check=True)
root = home / 'terminal-setup'
state = json.loads((root / 'current.json').read_text())
release = root / 'releases' / state['directory']
assert (release / '.tools').is_dir()
# Also exercise the pinned PowerShell module on Linux when pwsh is available.
if os.name != 'nt' and shutil.which('pwsh'):
    spec = importlib.util.spec_from_file_location('installer', REPO / 'setup.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    installer.install_powershell_modules(root, release)
for ps in ['powershell', 'pwsh']:
    if not shutil.which(ps):
        continue
    module = release / '.tools/modules/PSReadLine/2.4.5/PSReadLine.psd1'
    command = ("$ErrorActionPreference='Stop'; $m=Import-Module '" + str(module).replace("'", "''") +
               "' -PassThru; if($m.Version -ne [version]'2.4.5'){throw 'Unexpected PSReadLine version'}; "
               "Set-PSReadLineOption -HistoryNoDuplicates -BellStyle None; $m.Version.ToString()")
    subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', command], check=True)
print('Real install passed. Isolated home:', home)
