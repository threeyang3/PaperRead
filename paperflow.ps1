$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = (Join-Path $Root "src") + [IO.Path]::PathSeparator + $env:PYTHONPATH
$Python = Join-Path $Root ".paperflow\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "py" }
& $Python -m paperflow.cli @args
exit $LASTEXITCODE
