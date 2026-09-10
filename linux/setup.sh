#!/usr/bin/env bash
# Compatibility launcher for the original installation URL.
set -euo pipefail
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$script_dir/../install.sh" ]]; then exec bash "$script_dir/../install.sh" "$@"; fi
fi
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
curl -fsSL --connect-timeout 10 --max-time 60 https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.sh -o "$scratch/install.sh"
bash "$scratch/install.sh" "$@"
