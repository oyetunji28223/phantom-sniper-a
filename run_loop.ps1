param(
    [string]$MarketData = 'market_data.example.json',
    [string]$Config = 'paper_config.json',
    [string]$OutputDirectory = 'paper_runs',
    [double]$IntervalSeconds = 3600,
    [int]$Runs = 0,
    [double]$TargetUnits = 0,
    [switch]$Force
)

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

    if ($IntervalSeconds -le 0) {
        throw 'IntervalSeconds must be positive.'
    }
    if ($Runs -lt 0) {
        throw 'Runs must be zero or positive.'
    }

    $env:PYTHONDONTWRITEBYTECODE = '1'
    $Arguments = @(
        'run_loop.py',
        '--market-data', $MarketData,
        '--config', $Config,
        '--output-dir', $OutputDirectory,
        '--interval', [string]$IntervalSeconds,
        '--runs', [string]$Runs
    )
    if ($TargetUnits -gt 0) {
        $Arguments += @('--target-units', [string]$TargetUnits)
    }
    if ($Force) {
        $Arguments += '--force'
    }

    & py -3 @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Paper loop failed.'
    }
}
finally {
    Pop-Location
}
