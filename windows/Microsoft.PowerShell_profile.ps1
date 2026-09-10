# Managed profile. Personal settings belong in terminal-setup/user/profile.ps1.
if ($global:TerminalSetupLoaded) { return }
$global:TerminalSetupLoaded = $true
$global:TerminalSetupRelease = Split-Path $PSScriptRoot -Parent
$env:Path = (Join-Path $TerminalSetupRelease '.tools') + [IO.Path]::PathSeparator + $env:Path
$tsModulePath = Join-Path $TerminalSetupRelease '.tools\modules'
if (Test-Path -LiteralPath $tsModulePath) {
    $env:PSModulePath = $tsModulePath + [IO.Path]::PathSeparator + $env:PSModulePath
}

function terminal_setup {
    $settings = Get-Content -LiteralPath (Join-Path $TerminalSetupRoot 'settings.json') -Raw | ConvertFrom-Json
    & $settings.python (Join-Path $TerminalSetupRelease 'setup.py') @args --root $TerminalSetupRoot
}
Set-Alias ts terminal_setup
function Update-Profile { terminal_setup update }
function reload_profile {
    $global:TerminalSetupLoaded = $false
    . $PROFILE
}
Set-Alias reload-profile reload_profile
function ep {
    $file = Join-Path $TerminalSetupRoot 'user\profile.ps1'
    if ($env:EDITOR) { & $env:EDITOR $file } else { notepad $file }
}
function gs { git status @args }
function ga { git add . @args }
function Invoke-TerminalGitCommit { git commit -m ($args -join ' ') }
Set-Alias gc Invoke-TerminalGitCommit -Force
function gpush { git push @args }
function gpull { git pull @args }
function gcl { git clone @args }
function gcom {
    git add .
    if ($LASTEXITCODE -eq 0) { git commit -m ($args -join ' ') }
}
function lazyg {
    gcom @args
    if ($LASTEXITCODE -eq 0) { git push }
}
function mkcd([string]$Path) {
    New-Item -ItemType Directory -Path $Path -Force -ErrorAction Stop | Out-Null
    Set-Location -LiteralPath $Path
}
function nf {
    foreach ($file in $args) {
        if (Test-Path -LiteralPath $file) {
            (Get-Item -LiteralPath $file).LastWriteTime = Get-Date
        } else { New-Item -ItemType File -Path $file -ErrorAction Stop | Out-Null }
    }
}
function ff([string]$Name) { Get-ChildItem -Recurse -Filter "*$Name*" -ErrorAction SilentlyContinue }
function docs { Set-Location ([Environment]::GetFolderPath('MyDocuments')) }
function dtop { Set-Location ([Environment]::GetFolderPath('Desktop')) }
function pubip { Invoke-RestMethod 'https://api.ipify.org' -TimeoutSec 10 }
function sysinfo { Get-ComputerInfo }
function cpy { Set-Clipboard -Value ($args -join ' ') }
function pst { Get-Clipboard }
if (Get-Command eza -ErrorAction SilentlyContinue) {
    function Invoke-TerminalList { eza --icons=auto --git @args }
    Set-Alias ls Invoke-TerminalList -Force
    function la { eza -la --icons=auto --git @args }
    function ll { eza -la --icons=auto --git @args }
} else {
    function la { Get-ChildItem -Force @args }
    function ll { Get-ChildItem -Force @args }
}
function show_help {
    Write-Host @'
Terminal setup
  ts status | ts update | ts rollback
  ep / reload_profile       Edit your overrides / reload this shell
  gs, ga, gc <message>, gpush, gpull, gcl, gcom <message>, lazyg <message>
  ls, la, ll, mkcd <dir>, nf <file>, ff <name>, docs, dtop, z <dir>
  pubip, sysinfo, cpy/pst
'@
}
Set-Alias Show-Help show_help
$tsInteractive = -not ([Environment]::GetCommandLineArgs() | Where-Object { $_ -match '^-(NonInteractive|Command|c|File|f)$' })
if ($tsInteractive -and (Get-Module -ListAvailable PSReadLine)) {
    # A host may preload a binary module; replacing its assembly in-process is unsafe.
    if (-not (Get-Module PSReadLine)) { Import-Module PSReadLine }
    Set-PSReadLineOption -EditMode Windows -HistoryNoDuplicates -BellStyle None
    Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward
    Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
    Set-PSReadLineKeyHandler -Key Tab -Function MenuComplete
    if ((Get-Command Set-PSReadLineOption).Parameters.ContainsKey('PredictionSource')) {
        Set-PSReadLineOption -PredictionSource History
    }
}
# Keep legacy user customizations active and load each override only once.
$tsLegacyDir = Split-Path $PROFILE -Parent
$tsLegacyProfile = Join-Path $tsLegacyDir 'profile.ps1'
if (Test-Path -LiteralPath $tsLegacyProfile) { . $tsLegacyProfile }
$tsCustom = Join-Path $TerminalSetupRoot 'user\profile.ps1'
if (Test-Path -LiteralPath $tsCustom) { . $tsCustom }
if (Get-Command oh-my-posh -ErrorAction SilentlyContinue) {
    if (Get-Command Get-Theme_Override -ErrorAction SilentlyContinue) { Get-Theme_Override }
    else {
        $tsTheme = $env:OMP_CONFIG
        if (-not $tsTheme) {
            $tsTheme = @((Join-Path $TerminalSetupRoot 'user\my_layout.omp.json'),
                         (Join-Path $tsLegacyDir 'my_layout.omp.json'),
                         (Join-Path $TerminalSetupRelease 'my_layout.omp.json')) |
                       Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        }
        oh-my-posh init pwsh --config $tsTheme | Out-String | Invoke-Expression
    }
}
if (Get-Command zoxide -ErrorAction SilentlyContinue) {
    zoxide init powershell --cmd z | Out-String | Invoke-Expression
}
if ($tsInteractive -and -not $debug_Override -and $env:TERMINAL_SETUP_AUTO_UPDATE -ne '0') {
    terminal_setup launch *> $null
}
