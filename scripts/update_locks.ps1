param()

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
  foreach ($version in @("3.11", "3.12", "3.13")) {
    $suffix = $version.Replace(".", "")
    uv pip compile pyproject.toml `
      --extra dev `
      --extra quality `
      --extra browser `
      --python-version $version `
      --generate-hashes `
      --output-file "requirements/release-py$suffix.txt"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
} finally {
  Pop-Location
}
