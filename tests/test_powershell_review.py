"""Regression coverage for PowerShell migration and caller-scope reloads."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
POWERSHELLS = [path for name in ('powershell', 'pwsh') if (path := shutil.which(name))]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(POWERSHELLS, 'PowerShell runtime required')
class PowerShellReviewTests(unittest.TestCase):
    def run_profile(self, script, legacy=False):
        with tempfile.TemporaryDirectory(prefix='terminal-setup-powershell-') as temporary:
            home = Path(temporary)
            root = home / 'installation'
            root.mkdir()
            profile = home / 'Documents/PowerShell/Microsoft.PowerShell_profile.ps1'
            profile.parent.mkdir(parents=True)
            if legacy:
                shutil.copy2(REPO / 'windows/Microsoft.PowerShell_profile.ps1', profile)
                custom = profile.parent / 'profile.ps1'
            else:
                release = root / 'releases/test'
                (release / 'windows').mkdir(parents=True)
                (release / 'setup.py').write_text('# fixture installer\n')
                managed = release / 'windows/Microsoft.PowerShell_profile.ps1'
                shutil.copy2(REPO / 'windows/Microsoft.PowerShell_profile.ps1', managed)
                profile.write_text('$global:TerminalSetupRoot = ' + quote(root) + '\n. ' + quote(managed) + '\n')
                (root / 'user').mkdir()
                custom = root / 'user/profile.ps1'
            custom.write_text("function ReviewExisting { 'before' }\n$ReviewVariable = 'before'\n")
            theme = profile.parent / 'my_layout.omp.json'
            theme.write_text('{"version":3,"blocks":[]}')
            environment = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
                               LOCALAPPDATA=str(home / 'AppData/Local'),
                               XDG_DATA_HOME=str(home / 'data'), XDG_CACHE_HOME=str(home / 'cache'),
                               XDG_CONFIG_HOME=str(home / 'config'),
                               TERMINAL_SETUP_HOME=str(root), TERMINAL_SETUP_AUTO_UPDATE='0')
            command = ("$ErrorActionPreference='Stop'; $PROFILE=" + quote(profile) + "; $custom=" + quote(custom) + "; "
                       "function oh-my-posh { $global:ReviewTheme = $args[-1]; '# stub prompt' }; "
                       "function zoxide { '# stub navigation' }; "
                       "function eza { 'stub listing' }; "
                       "Set-Alias gc Get-Content -Option AllScope -Force; Set-Alias ls Get-ChildItem -Option AllScope -Force; "
                       "function Invoke-WebRequest { param($Uri, [switch]$UseBasicParsing, $TimeoutSec, $ErrorAction) "
                       "$global:ReviewDownloadUri=$Uri; $global:ReviewDownloads += 1; "
                       "if ($global:ReviewFailDownload) { throw 'download failed' }; "
                       "[pscustomobject]@{Content='$global:ReviewBootstrapRuns += 1'} }; "
                       ". $PROFILE; " + script)
            for executable in POWERSHELLS:
                with self.subTest(executable=executable):
                    # Each edition sees the same original fixture, before the tested edits.
                    custom.write_text("function ReviewExisting { 'before' }\n$ReviewVariable = 'before'\n")
                    result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Command', command],
                                            env=environment, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dot_sourced_reload_persists_functions_aliases_and_variables(self):
        self.run_profile(
            "@'\nfunction ReviewExisting { 'after' }\nfunction ReviewNew { 'new' }\n"
            "$ReviewVariable = 'after'\nSet-Alias ReviewAlias ReviewNew\n'@ | Set-Content -LiteralPath $custom; "
            "$advice = reload_profile 3>&1; "
            "if ((ReviewExisting) -ne 'before' -or $ReviewVariable -ne 'before') { throw 'normal invocation partially reloaded' }; "
            "if (-not ($advice -match 'leading dot')) { throw 'missing reload instruction' }; "
            ". reload_profile; "
            "if ((ReviewExisting) -ne 'after') { throw 'existing function did not reload' }; "
            "if ((ReviewNew) -ne 'new' -or (ReviewAlias) -ne 'new') { throw 'new definitions did not persist' }; "
            "if ($ReviewVariable -ne 'after') { throw 'custom variable did not persist' }")

    def test_builtin_aliases_keep_allscope_options(self):
        self.run_profile(
            "if ((Get-Alias gc).Definition -ne 'Invoke-TerminalGitCommit') { throw 'gc alias not installed' }; "
            "if ((Get-Alias ls).Definition -ne 'Invoke-TerminalList') { throw 'ls alias not installed' }; "
            "foreach ($name in 'gc','ls') { "
            "if (-not ((Get-Alias $name).Options -band [Management.Automation.ScopedItemOptions]::AllScope)) { throw 'AllScope lost' } }")

    def test_legacy_profile_keeps_customizations_and_migrates_only_on_request(self):
        self.run_profile(
            "if (-not $TerminalSetupLegacy) { throw 'legacy layout not detected' }; "
            "if ($TerminalSetupRoot -ne $env:TERMINAL_SETUP_HOME) { throw 'wrong installation root' }; "
            "if ((ReviewExisting) -ne 'before' -or $ReviewVariable -ne 'before') { throw 'lost legacy overrides' }; "
            "if ($ReviewTheme -ne (Join-Path (Split-Path $PROFILE -Parent) 'my_layout.omp.json')) { throw 'lost legacy theme' }; "
            "if ($ReviewDownloads -or $ReviewBootstrapRuns) { throw 'startup attempted migration' }; "
            "if ((ts status) -notmatch 'Legacy installation') { throw 'missing legacy status' }; "
            "ts launch; if ($ReviewDownloads) { throw 'launch attempted migration' }; "
            "Update-Profile; "
            "if ($ReviewBootstrapRuns -ne 1 -or $ReviewDownloads -ne 1) { throw 'explicit migration did not bootstrap' }; "
            "$global:ReviewFailDownload=$true; $failed=$false; "
            "try { ts update } catch { $failed=$true }; "
            "if (-not $failed -or $ReviewBootstrapRuns -ne 1) { throw 'failed HTTP download was executed' }", legacy=True)
