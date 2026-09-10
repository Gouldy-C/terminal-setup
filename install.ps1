# Windows PowerShell 5.1+ / PowerShell 7. Run as your normal user.
[CmdletBinding()]
param([string]$Repo = 'https://github.com/Gouldy-C/terminal-setup.git', [switch]$SkipTools)
$ErrorActionPreference = 'Stop'
if ($env:TERMINAL_SETUP_REPO) { $Repo = $env:TERMINAL_SETUP_REPO }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# Configure the persisted policy, even when this bootstrap was launched with -ExecutionPolicy Bypass.
$policies = Get-ExecutionPolicy -List
$persistentPolicy = @('MachinePolicy','UserPolicy','CurrentUser','LocalMachine') |
    ForEach-Object { $scope = $_; $policies | Where-Object { $_.Scope -eq $scope -and $_.ExecutionPolicy -ne 'Undefined' } } |
    Select-Object -First 1
if (-not $persistentPolicy -or $persistentPolicy.ExecutionPolicy -eq 'Restricted') {
    if ($persistentPolicy -and $persistentPolicy.Scope -in @('MachinePolicy','UserPolicy')) {
        throw 'Group Policy disables PowerShell profiles. Ask your administrator to permit them before installing.'
    }
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
} elseif ($persistentPolicy.ExecutionPolicy -eq 'AllSigned') {
    throw 'AllSigned requires signed profiles. Configure an approved signing workflow before installing.'
}
function Find-Python {
    foreach ($candidate in @('py', 'python', 'python3')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            try { $result = & $candidate -c 'import sys; print(sys.executable) if sys.version_info >= (3,10) else sys.exit(1)' 2>$null } catch { continue }
            if ($LASTEXITCODE -eq 0 -and $result) { return ($result | Select-Object -Last 1) }
        }
    }
    foreach ($candidate in @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue)) {
        $result = & $candidate.FullName -c 'import sys; print(sys.executable) if sys.version_info >= (3,10) else sys.exit(1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $result }
    }
}
function Install-Package([string]$Id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer (winget) from Microsoft Store, then retry.' }
    & winget install --exact --id $Id --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "winget could not install $Id (exit $LASTEXITCODE)." }
    $env:Path = $env:Path + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
$pythonExe = Find-Python
if (-not $pythonExe) { Install-Package 'Python.Python.3.14'; $pythonExe = Find-Python }
if (-not $pythonExe) { throw 'Python 3.10+ could not be found. Restart PowerShell and retry.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Install-Package 'Git.Git'
    foreach ($gitDir in @("$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd")) {
        if (Test-Path "$gitDir\git.exe") { $env:Path = "$gitDir;$env:Path" }
    }
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git could not be found. Restart PowerShell and retry.' }
$setupArgs = @('install','--repo',$Repo,'--powershell-profile',[string]$PROFILE)
if ($SkipTools) { $setupArgs += '--skip-tools' }
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'setup.py'))) {
    & $pythonExe (Join-Path $PSScriptRoot 'setup.py') @setupArgs
    if ($LASTEXITCODE -ne 0) { throw 'Terminal setup failed. See the error above.' }
} else {
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ('terminal-setup-' + [Guid]::NewGuid())
    try {
        # stdin avoids Windows PowerShell 5.1 stripping quotes from native -c arguments.
        @'
import os, subprocess, sys
subprocess.run(['git', '-c', 'credential.helper=', 'clone', '--quiet', '--depth=1',
                '--branch', 'main', '--single-branch', '--', sys.argv[1], sys.argv[2]],
               check=True, timeout=90, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
'@ | & $pythonExe - $Repo $scratch
        if ($LASTEXITCODE -ne 0) { throw 'Could not download main.' }
        & $pythonExe (Join-Path $scratch 'setup.py') @setupArgs
        if ($LASTEXITCODE -ne 0) { throw 'Terminal setup failed. See the error above.' }
    } finally {
        if (Test-Path $scratch) { Remove-Item -LiteralPath $scratch -Recurse -Force }
    }
}
