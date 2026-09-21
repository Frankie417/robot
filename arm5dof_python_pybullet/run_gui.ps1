param(
    [ValidateSet('dance', 'transport')]
    [string]$Demo = 'dance',
    [int]$Hold = 30
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = 'D:\robot_new\.venv-arm5dof-sim\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Simulation environment not found: $python"
}

Push-Location $scriptRoot
try {
    & $python 'run_real_examples_in_sim.py' $Demo '--hold' $Hold
} finally {
    Pop-Location
}
