# Terminal Setup

One setup for **Linux/WSL (Bash)** and **Windows (PowerShell 5.1 or 7)**. Both install Oh My Posh, zoxide, eza, and CaskaydiaCove Nerd Font, use the same prompt theme and shortcuts, and automatically install new commits from this repository's `main` branch.

## Install

Run as your normal user. The bootstrap installs missing prerequisites; your package manager may request elevation. Profiles, terminal tools, downloads, and updates are installed for your user account.

**Linux / WSL:**

```bash
curl -fsSL https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.sh | bash
```

**Windows — paste into PowerShell:**

```powershell
& ([scriptblock]::Create((Invoke-RestMethod https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.ps1)))
```

If you prefer to download and inspect the script first:

```bash
curl -fsSL https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.sh -o terminal-setup-install.sh
less terminal-setup-install.sh
bash terminal-setup-install.sh
```

```powershell
curl.exe -fSL https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.ps1 -o terminal-setup-install.ps1
Get-Content .\terminal-setup-install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\terminal-setup-install.ps1
```

Open a new terminal after installation. Select **CaskaydiaCove Nerd Font Mono** in your terminal application's font preferences. The installer preserves your terminal application's existing settings. For WSL, the font must also be installed on the Windows host: run the Windows installer there, then select the font in Windows Terminal.

On Windows, the bootstrap enables `RemoteSigned` for the current user if the persistent policy is the default `Restricted`. It respects Group Policy and stops under `AllSigned`, which requires a signing workflow. It does not change machine-wide policy.

Run the Windows command once in each PowerShell edition you use. It discovers that edition's actual `$PROFILE` location (including redirected Documents folders) and registers it with the shared installation.

### Supported systems

- Linux x86-64 and ARM64; Bash; Python 3.10+; Git; curl; CA certificates. The bootstrap can install missing prerequisites through apt, dnf, pacman, or zypper. ARM64 eza requires glibc 2.18+ and libgcc; its upstream build is incompatible with ARM64 musl-only distributions.
- Windows x86-64 and ARM64; Windows PowerShell 5.1 or PowerShell 7. Missing Python (3.14) and Git are installed using **winget** (App Installer). Windows ARM64 uses native Oh My Posh/zoxide and the x64 eza build, so x64 emulation is required.
- WSL follows the Linux path. This release does not configure Zsh, Fish, Command Prompt, or macOS.

The tools and theme are identical across platforms. Shell syntax, OS information, and clipboard implementations follow the host shell. No administrator permissions, package-manager prompts, or PowerShell upgrades run during automatic updates.

## Dependency versions and compatibility

Verified against upstream stable releases on September 10, 2026:

- [Oh My Posh 31.2.1](https://github.com/JanDeDobbeleer/oh-my-posh/releases/tag/v31.2.1), [zoxide 0.10.0](https://github.com/ajeetdsouza/zoxide/releases/tag/v0.10.0), [eza 0.23.5](https://github.com/eza-community/eza/releases/tag/v0.23.5), and [Nerd Fonts 3.5.1](https://github.com/ryanoasis/nerd-fonts/releases/tag/v3.5.1).
- [PSReadLine 2.4.5](https://www.powershellgallery.com/packages/PSReadLine/2.4.5), installed alongside each Windows release with a verified checksum. It supports Windows PowerShell 5.1 and PowerShell 7. Modules are imported and checked in fresh processes before activation.
- Fonts are installed in directories keyed by their archive checksum. A new font release is installed even when an older same-named font exists; previous and customized files are retained.
- Windows bootstrap targets Python 3.14; compatibility tests cover maintained Python 3.10, 3.12, and 3.14. Python 3.9 is no longer a supported bootstrap runtime.
- CI uses checkout 7.0.1 and setup-python 7.0.0, both pinned to immutable commit hashes.

Existing supported Python and Git installations remain package-manager owned and are reused. This setup does not replace the operating system's Python or upgrade your PowerShell executable. PSReadLine is exposed through the active release's module path; if a custom host already loaded a different PSReadLine assembly, the profile keeps that assembly for the current session rather than attempting an unsafe replacement. `--skip-tools` also skips the managed PowerShell module.

## How updates work

Every interactive shell launch starts a background check of **`refs/heads/main` on the configured repository**. There is no seven-day interval, ping requirement, GitHub API token, or separate connectivity probe. The shell loads its installed configuration immediately; the check has a 15-second timeout and works quietly when offline.

When `main` points to a different commit, the updater:

1. Fetches that exact commit into a new release directory.
2. Carries forward compatible direct edits using Git's three-way merge and preserves local untracked files.
3. Validates the candidate and runs **its installer**, so changes to installation logic, profiles, themes, and dependency versions all apply.
4. Downloads the pinned dependencies in `tools.json`, verifies SHA-256 checksums, and checks that the binaries run.
5. Atomically switches the active release only after installation succeeds.

Changes take effect in the **next terminal you open**, or after `reload_profile`. An update never rewrites the shell session you are currently using. A per-user OS lock prevents simultaneous updates and releases automatically if a process crashes.

Network failures, invalid files, failed dependencies, and conflicting local edits leave the current release active. The next launch retries. A conflicting edit requires your decision; the updater will not silently discard it to force an update. Downloads and installation have timeouts; the whole candidate installation is limited to ten minutes.

Auto-updates execute code from this repository's `main`. Use a repository you trust. Third-party versions change only when `tools.json` changes on `main`.

## Your customizations stay yours

The installation root is:

- Linux: `${XDG_DATA_HOME:-$HOME/.local/share}/terminal-setup`
- Windows: `%LOCALAPPDATA%\terminal-setup`
- Either platform: set `TERMINAL_SETUP_HOME` before installation to choose a different location. Keep using that location for reinstalls.

Inside that directory:

```text
user/profile.bash       Bash customizations; created once, never overwritten
user/profile.ps1        PowerShell customizations; created once, never overwritten
user/my_layout.omp.json Optional personal theme; never overwritten
settings.json           Repository, update preference, installation options
current.json            Active main commit and release directory
previous.json           Previous active release for rollback
releases/               Complete installations, including their local edits
backups/                Original startup files saved before initial modification
cache/                  Downloads keyed by SHA-256
update.log              Background update output and errors
```

Use `ep` in either shell to edit your personal profile. Overrides load once, after the built-in shortcuts and before prompt initialization. For example:

```bash
# user/profile.bash
export EDITOR='code --wait'
alias gs='git status --short'
# export OMP_CONFIG="$TERMINAL_SETUP_HOME/user/my_layout.omp.json"
# export TERMINAL_SETUP_AUTO_UPDATE=0
```

```powershell
# user/profile.ps1
$env:EDITOR = 'code'
function gs { git status --short @args }
# $env:OMP_CONFIG = Join-Path $TerminalSetupRoot 'user\my_layout.omp.json'
# $env:TERMINAL_SETUP_AUTO_UPDATE = '0'
```

Existing `.bashrc`, the active Bash login file, and ordinary PowerShell profile content are backed up and retained; setup adds a small loader. Symlinks used by dotfile managers are preserved. Re-running setup does not duplicate its loader or replace your override files, history, zoxide database, SSH keys, Git checkout, or terminal settings.

Prefer `user/` for permanent changes. Direct edits inside an active release are merged forward where possible. If they conflict, `ts update` reports the problem: edit the file in the active directory shown by `ts status`, keep or move your changes into `user/`, and retry. Files edited while an update is installing also cause it to stop and retry. Old releases are retained, including their original local data; there is no automatic deletion policy. The generated `.tools/` binaries are rebuilt, so keep personal assets outside that directory.

### Migrating from the previous installer

The old `linux/setup.sh` and `windows/setup.ps1` URLs remain compatibility launchers. Re-run installation once to move to this update system; the old updater cannot upgrade its own installation architecture.

Existing `~/.config/bash/profile.bash` (respecting `XDG_CONFIG_HOME`), PowerShell `profile.ps1`, and old custom theme files remain active. Old custom themes take priority over the repository theme; move your theme to `user/my_layout.omp.json` when convenient. `debug_Override` still disables launch checks. The old interval and raw-URL overrides are replaced by `settings.json`.

A pristine legacy managed profile is backed up and replaced with a loader. If that managed profile has been edited, installation stops with its path **before overwriting it**. Move your additions into the personal override file, save the legacy file elsewhere, and retry. Arbitrary old executable profiles cannot safely be merged into this different architecture automatically.

## Commands shared by both shells

- `ts status`: show the installed commit, installation root, and settings.
- `ts update`: check and install `main` now, with visible errors.
- `ts rollback`: reactivate the previous release and disable automatic updates.
- `ep`, `reload_profile`, `show_help`: edit overrides, reload, or show help.
- `gs`, `ga`, `gc <message>`, `gpush`, `gpull`, `gcl`, `gcom <message>`, `lazyg <message>`: Git shortcuts.
- `ls`, `la`, `ll`, `mkcd <dir>`, `nf <file>`, `ff <name>`, `docs`, `dtop`, `z <dir>`: files and navigation.
- `pubip`, `sysinfo`, `cpy`, `pst`: system and clipboard helpers. Linux clipboard helpers require `wl-clipboard` or `xclip`.

`nf` creates missing files and updates timestamps without truncating existing data. Native Bash `touch`, `pkill`, and `pgrep` keep their standard behavior. The previous destructive cache cleanup and remote utility/upload wrappers are no longer installed.

To pause updates across shells, set `"auto_update": false` in `settings.json`. Set it to `true` to resume, including after rollback. Manual `ts update` still works while automatic updates are paused. To use a fork, change `"repo"` in that file to its clone URL; the branch remains `main`.

For an initial fork install:

```bash
export TERMINAL_SETUP_REPO=https://github.com/YOU/terminal-setup.git
curl -fsSL https://raw.githubusercontent.com/YOU/terminal-setup/main/install.sh | bash
```

```powershell
$env:TERMINAL_SETUP_REPO = 'https://github.com/YOU/terminal-setup.git'
& ([scriptblock]::Create((Invoke-RestMethod https://raw.githubusercontent.com/YOU/terminal-setup/main/install.ps1)))
```

## Development and verification

The two bootstrap scripts install prerequisites and call `setup.py`, the shared Python standard-library engine. `tools.json` pins official release URLs and checksums. Shell-specific defaults live in `linux/bashrc` and `windows/Microsoft.PowerShell_profile.ps1`.

Installation always reads committed **`main`**, including when invoked from a checkout. To test your local committed `main` without publishing it:

```bash
bash install.sh --repo "$PWD" --skip-tools
```

```powershell
.\install.ps1 -Repo $PWD.Path -SkipTools
```

`--skip-tools` / `-SkipTools` enables profile-only installation and persists for subsequent updates. Reinstall without the option to enable dependency installation. Use a temporary home or `TERMINAL_SETUP_HOME` for testing; the installer still connects the current user's shell startup files.

Run offline integration tests:

```bash
python3 -m unittest discover -s tests -v
```

```powershell
python -m unittest discover -s tests -v
```

Run the complete installer with real downloads in an isolated temporary home:

```bash
python3 tests/smoke_install.py
```

On Windows use `python tests/smoke_install.py`. GitHub Actions runs the offline suite on Linux and Windows with Python 3.10, 3.12, and 3.14, parses the PowerShell scripts, and runs the full dependency smoke test on x64 and ARM64 runners for both operating systems. ARM64 integration uses Python 3.14. Windows smoke tests exercise both local and downloaded bootstraps in Windows PowerShell 5.1 and PowerShell 7. These jobs run after the changes are pushed; a local Linux test does not establish native Windows compatibility.

## Credits

This project began as an expansion of [Chris Titus Tech's PowerShell profile](https://github.com/ChrisTitusTech/powershell-profile). Thanks to that project for the original shortcuts and customization approach. The installation/update engine and managed profiles have since been rewritten for shared Linux/Windows behavior.

Tools: [Oh My Posh](https://ohmyposh.dev/), [zoxide](https://github.com/ajeetdsouza/zoxide), [eza](https://github.com/eza-community/eza), and [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts). Each retains its upstream license. This repository does not currently include its own license grant; upstream licensing does not automatically license the entire repository.
