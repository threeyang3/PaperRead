#!/usr/bin/env sh
set -eu

METHOD="${1:-pipx}"
SOURCE="${2:-.}"

python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
case "$METHOD" in
  pipx) pipx install "$SOURCE" ;;
  uv) uv tool install "$SOURCE" ;;
  pip) python3 -m pip install "$SOURCE" ;;
  *) echo "Usage: install.sh [pipx|uv|pip] [source]" >&2; exit 2 ;;
esac
echo "PaperFlow installed. No Vault was created and no credentials were read."
echo 'Next: paperflow init --vault "/path/to/Vault"'
