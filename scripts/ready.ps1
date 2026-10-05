param([switch]$Reproduce, [switch]$Calibration, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectPath
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
    }
    $labPython = Join-Path $projectPath '.venv\Scripts\python.exe'
    function Run-Lab([string[]]$Arguments) {
        & $labPython @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed: $Arguments" }
    }
    Run-Lab @('-m', 'pip', 'install', '-e', '.[plots,reports]')
    if ($Reproduce -or $Calibration) {
        if ($Calibration) { Run-Lab @('scripts/reproduce.py', '--calibration') }
        else { Run-Lab @('scripts/reproduce.py') }
    }
    Run-Lab @('scripts/verify.py')
    Run-Lab @('scripts/build_proposal.py')
    Run-Lab @('scripts/build_report.py')
    Run-Lab @('scripts/audit_pdfs.py')
    Run-Lab @('scripts/build_release.py')
    Write-Host 'Verified package: output/release. Start the demo: .venv\Scripts\python.exe -m paritylab demo'
} finally { Pop-Location }
