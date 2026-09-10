# Compatibility launcher for the original installation URL.
[CmdletBinding()]
param([string]$Repo = 'https://github.com/Gouldy-C/terminal-setup.git', [switch]$SkipTools)
$ErrorActionPreference = 'Stop'
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot '..\install.ps1'))) {
    & (Join-Path $PSScriptRoot '..\install.ps1') -Repo $Repo -SkipTools:$SkipTools
} else {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $script = (Invoke-WebRequest 'https://raw.githubusercontent.com/Gouldy-C/terminal-setup/main/install.ps1' -UseBasicParsing -TimeoutSec 60).Content
    & ([scriptblock]::Create($script)) -Repo $Repo -SkipTools:$SkipTools
}
