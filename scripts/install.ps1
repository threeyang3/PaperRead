param(
  [ValidateSet("pipx", "uv", "pip")]
  [string]$Method = "pipx",
  [string]$Source = ""
)

$ErrorActionPreference = "Stop"
if (-not $Source) {
  $wheel = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "paperflow-*.whl" |
    Sort-Object Name |
    Select-Object -Last 1
  if (-not $wheel) {
    $wheel = Get-ChildItem -LiteralPath (Split-Path $PSScriptRoot -Parent) -Filter "paperflow-*.whl" |
      Sort-Object Name |
      Select-Object -Last 1
  }
  if (-not $wheel) { throw "No PaperFlow wheel was found beside the installer." }
  $Source = $wheel.FullName
}

switch ($Method) {
  "pipx" {
    $tool = Get-Command pipx -ErrorAction SilentlyContinue
    if (-not $tool) {
      throw "pipx is not installed. Install pipx first, or rerun with -Method uv or -Method pip."
    }
    & $tool.Source install $Source
  }
  "uv" {
    $tool = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $tool) {
      throw "uv is not installed. Install uv first, or rerun with -Method pipx or -Method pip."
    }
    & $tool.Source tool install $Source
  }
  "pip" {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "Python 3.11 or newer is required for -Method pip." }
    $version = & $python.Source -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
    if ([version]$version -lt [version]"3.11") {
      throw "Python 3.11 or newer is required; found $version."
    }
    & $python.Source -m pip install $Source
  }
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$paperflow = Get-Command paperflow -ErrorAction SilentlyContinue
if (-not $paperflow) {
  throw "Installation completed but the paperflow console script is not discoverable. Check the selected tool's bin directory."
}
& $paperflow.Source --version
if ($LASTEXITCODE -ne 0) { throw "paperflow --version failed after installation." }
& $paperflow.Source --help *> $null
if ($LASTEXITCODE -ne 0) { throw "paperflow --help failed after installation." }

Write-Host "PaperFlow installed. No Vault was created and no AI credentials were read."
Write-Host 'Next: paperflow init --vault "C:\path\to\your\Vault"'
