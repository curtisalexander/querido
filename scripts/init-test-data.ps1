# Initialize test databases with sample data.
# Run from the project root: .\scripts\init-test-data.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Push-Location $ProjectDir
try {
    uv run python scripts/init_test_data.py
} finally {
    Pop-Location
}
