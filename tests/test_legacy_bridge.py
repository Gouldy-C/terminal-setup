"""Regression coverage for the original file-only updater receiving this release."""
import os
from pathlib import Path
import shlex
import subprocess
import unittest

import test_setup


@unittest.skipIf(os.name == 'nt', 'Historical Bash updater migration')
class LegacyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_setup.InstallationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.legacy = self.fixture.home / 'config/bash/bashrc'
        self.legacy.parent.mkdir(parents=True)
        self.legacy.write_bytes((test_setup.REPO / 'tests/fixtures/legacy-bashrc').read_bytes())
        (self.legacy.parent / 'profile.bash').write_text(
            'debug_Override=true\n'
            'repo_root_Override=' + shlex.quote(self.fixture.origin.as_uri()) + '\n'
            'CUSTOM_LOADS=$(( ${CUSTOM_LOADS:-0} + 1 ))\n'
            "alias gs='git status --short'\n")
        (self.fixture.home / '.bashrc').write_text('source ' + shlex.quote(str(self.legacy)) + '\n')

    def shell(self, command):
        result = subprocess.run(['bash', '--noprofile', '--norc', '-ic', command],
                                env=self.fixture.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_original_updater_transition_and_installer_migration(self):
        # Exercise the actual previously published updater, using a local file URL.
        self.shell('source "$HOME/.bashrc"; update_bashrc')
        self.assertEqual(self.legacy.read_bytes(), (self.fixture.origin / 'linux/bashrc').read_bytes())
        # The old installer can source .bashrc twice from a login profile.
        result = self.shell('source "$HOME/.bashrc"; source "$HOME/.bashrc"; ts status; printf "LOADS=%s\\n" "$CUSTOM_LOADS"; alias gs')
        self.assertIn('Legacy terminal setup is active', result.stdout)
        self.assertIn('LOADS=1', result.stdout)
        self.assertIn('git status --short', result.stdout)
        self.assertNotIn("can't open file", result.stderr)
        # Deliver the curl payload locally, then exercise the advertised ts update
        # command and its real bootstrap clone/install path without network access.
        self.shell('source "$HOME/.bashrc"; reload_profile; '
                   '[[ "$CUSTOM_LOADS" == 2 ]] || exit 1; '
                   'curl() { [[ "$*" == *https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.sh* ]] || return 1; '
                   'cp ' + shlex.quote(str(self.fixture.origin / 'install.sh')) + ' "${@: -1}"; }; '
                   'TERMINAL_SETUP_REPO=' + shlex.quote(str(self.fixture.origin)) + ' ts update --skip-tools')
        self.assertIn('managed loader', self.legacy.read_text())
        result = self.shell('source "$HOME/.bashrc"; ts status; printf "LOADS=%s\\n" "$CUSTOM_LOADS"')
        self.assertIn('LOADS=1', result.stdout)
        self.assertNotIn('Legacy terminal setup is active', result.stdout)

    def test_edited_transition_profile_is_retained(self):
        self.legacy.write_bytes((self.fixture.origin / 'linux/bashrc').read_bytes() + b'\n# personal edit\n')
        before = self.legacy.read_bytes()
        result = self.fixture.cli('install', '--repo', self.fixture.origin, '--skip-tools', success=False)
        self.assertIn('local edits', result.stderr)
        self.assertEqual(self.legacy.read_bytes(), before)
        self.assertFalse((self.fixture.root / 'current.json').exists())


if __name__ == '__main__':
    unittest.main()
