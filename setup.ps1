$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Push-Location $ProjectRoot
try {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $PythonLauncher) {
        throw 'Python 3.10 or newer is required. Install Python from python.org and enable the Python launcher.'
    }

    & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.10 or newer is required.'
    }

    $env:PYTHONDONTWRITEBYTECODE = '1'
    Write-Host 'Running project tests...'
    & py -3 -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw 'Project tests failed; setup stopped.'
    }

    Write-Host 'Generating a sample paper-trading run...'
    & py -3 daily_loop.py market_data.example.json --output-dir paper_runs
    if ($LASTEXITCODE -ne 0) {
        throw 'Sample run failed; setup stopped.'
    }

    Write-Host ''
    Write-Host 'Setup complete. Review the paper-only report and message drafts in paper_runs\.'
    Write-Host 'To run again: .\run_paper.ps1'
}
finally {
    Pop-Location
}
