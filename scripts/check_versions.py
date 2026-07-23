from __future__ import annotations

import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
version_text = (ROOT / "src/paperflow/_version.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', version_text)
if not match:
    raise SystemExit("_version.py does not declare __version__")
version = match.group(1)

pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
if 'dynamic = ["version"]' not in pyproject or (
    'path = "src/paperflow/_version.py"' not in pyproject
):
    raise SystemExit("pyproject does not use the unified version source")

manifest = json.loads(
    (ROOT / "integrations/obsidian-paperflow-automation/manifest.json").read_text(
        encoding="utf-8"
    )
)
integration = json.loads(
    (ROOT / "integrations/obsidian-paperflow-automation/integration.json").read_text(
        encoding="utf-8"
    )
)
zotero = json.loads(
    (ROOT / "integrations/zotero-paperflow/manifest.json").read_text(encoding="utf-8")
)
if manifest["version"] != version or integration["version"] != version or zotero["version"] != version:
    raise SystemExit(
        f"version mismatch: app={version}, plugin={manifest['version']}, "
        f"integration={integration['version']}, zotero={zotero['version']}"
    )

tag = os.environ.get("GITHUB_REF_NAME", "")
if tag.startswith("v") and tag[1:] != version:
    raise SystemExit(f"tag {tag} does not match application version {version}")

print(json.dumps({
    "application": version,
    "plugin": manifest["version"],
    "integration": integration["version"],
    "zotero": zotero["version"],
    "pyproject": "dynamic",
    "tag": tag or None,
}))
