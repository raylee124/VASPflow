# User-adjustable parameters. Credentials are entered only in native OpenSSH.
param([string]$Python = 'python', [switch]$EnableAgent)
$ErrorActionPreference = 'Stop'
if ($EnableAgent) {
    # Invoked with UAC only after the user agrees inside the wizard.
    if ((Get-Service -Name ssh-agent).StartType -eq 'Disabled') {
        Set-Service -Name ssh-agent -StartupType Manual
    }
    Start-Service -Name ssh-agent
    exit
}
try {
    & $Python -B (Join-Path $PSScriptRoot 'onboard.py')
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message
    [void](Read-Host 'Python could not start. Default: press Enter to close')
    exit 1
}
