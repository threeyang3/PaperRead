param(
  [ValidateSet("pipx", "uv", "pip")]
  [string]$Method = "pipx"
)

$ErrorActionPreference = "Stop"
switch ($Method) {
  "pipx" { & pipx uninstall paperflow }
  "uv"   { & uv tool uninstall paperflow }
  "pip"  { & python -m pip uninstall -y paperflow }
}
exit $LASTEXITCODE
