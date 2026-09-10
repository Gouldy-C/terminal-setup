#!/usr/bin/env bash
# Linux / WSL bootstrap. The body is parsed completely before main runs.
main() {
set -euo pipefail
repo="${TERMINAL_SETUP_REPO:-https://github.com/Gouldy-C/terminal-setup.git}"
case "$(uname -s)" in
    Linux) ;;
    *) echo 'Use install.ps1 on Windows. This launcher supports Linux and WSL.' >&2; exit 1 ;;
esac
missing=()
for tool in python3 git curl; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if ((${#missing[@]})); then
    elevate=()
    if ((EUID != 0)); then elevate=(sudo); fi
    if command -v apt-get >/dev/null 2>&1; then
        "${elevate[@]}" apt-get update
        "${elevate[@]}" apt-get install -y python3 git curl ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
        "${elevate[@]}" dnf install -y python3 git curl ca-certificates
    elif command -v pacman >/dev/null 2>&1; then
        "${elevate[@]}" pacman -S --needed --noconfirm python git curl ca-certificates
    elif command -v zypper >/dev/null 2>&1; then
        "${elevate[@]}" zypper --non-interactive install python3 git curl ca-certificates
    else
        echo 'Install Python 3.10+, Git, curl, and CA certificates, then retry.' >&2; exit 1
    fi
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else "Python 3.10+ is required")'
# A local checkout is used only when explicitly running its launcher file.
script_dir=''
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -n "$script_dir" && -f "$script_dir/setup.py" ]]; then
    exec python3 "$script_dir/setup.py" install --repo "$repo" "$@"
fi
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
# Hard wall-clock deadline includes DNS, connection, and checkout.
python3 - "$repo" "$scratch/repo" <<'PY'
import os, subprocess, sys
subprocess.run(['git','-c','credential.helper=','clone','--quiet','--depth=1','--branch','main','--single-branch','--',sys.argv[1],sys.argv[2]],
               check=True, timeout=90, env=dict(os.environ,GIT_TERMINAL_PROMPT='0'))
PY
python3 "$scratch/repo/setup.py" install --repo "$repo" "$@"

}
main "$@"
