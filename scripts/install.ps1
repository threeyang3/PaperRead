param(
  [ValidateSet("pipx", "uv", "pip")]
  [string]$Method = "pipx",
  [string]$Source = "."
)

$ErrorActionPreference = "Stop"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python 3.11 or newer is required." }
$version = & python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ([version]$version -lt [version]"3.11") {
  throw "Python 3.11 or newer is required; found $version."
}

switch ($Method) {
  "pipx" { & pipx install $Source }
  "uv"   { & uv tool install $Source }
  "pip"  { & python -m pip install $Source }
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PaperFlow installed. No Vault was created and no AI credentials were read."
Write-Host 'Next: paperflow init --vault "C:\path\to\your\Vault"'
