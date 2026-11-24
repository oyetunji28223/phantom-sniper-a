param(
    [string]$MarketData = 'market_data.example.json',
    [string]$Config = 'paper_config.json',
    [string]$OutputDirectory = 'paper_runs'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Push-Location $ProjectRoot
try {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $PythonLauncher) {
        throw 'Python 3.10 or newer is required. Run .\setup.ps1 for setup instructions.'
    }

    $env:PYTHONDONTWRITEBYTECODE = '1'
    & py -3 daily_loop.py $MarketData --config $Config --output-dir $OutputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw 'Paper simulation failed.'
    }
}
finally {
    Pop-Location
}
