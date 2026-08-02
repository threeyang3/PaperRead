# Releasing

## 1.5 post-audit Release Candidate gate

CI and tag-triggered Release call `.github/workflows/quality-gates.yml`; Release
does not maintain a smaller parallel test list. The shared gate covers Python
3.11-3.13 on Windows, Ubuntu and macOS, locked/latest-compatible dependencies,
all Python tests, five Node integration entries, Ruff, format, Mypy, coverage,
pip-audit, Feed/migration contracts, build, packaging, wheel install and the
real Windows Offline Installer smoke.

The tag workflow checks that the tag version matches Python, Obsidian and
Zotero manifests, and that the tag commit belongs to `main`. It then enters the
protected `production-release` Environment, creates a Draft Release, uploads
and verifies every file plus `SHA256SUMS`, and only then publishes the draft.
Configure the Environment required reviewer in GitHub repository settings.

Install from `requirements/release-py311.txt`, `release-py312.txt`, or
`release-py313.txt` with `--require-hashes`. Regenerate all three only through
`scripts/update_locks.ps1`, review the diff, run both dependency lanes, and run
pip-audit. The Offline Installer contains no `paperflow.cmd` shim: after
installation use the installed `paperflow` console script. It is an install
bundle, not a truly portable Python runtime.

For PaperFlow 1.5.1 source release candidates, run:

```powershell
.\.venv\Scripts\python.exe -m pytest
node --test tests/integration/test_scheduler_core.js tests/integration/test_automation_plugin_lifecycle.js
.\.venv\Scripts\python.exe scripts/check_versions.py
git diff --check
.\.venv\Scripts\python.exe scripts/build_release.py
.\.venv\Scripts\python.exe -m pytest tests/packaging/test_artifacts.py
```

Verify every line of `dist/SHA256SUMS`, run Doctor and audit against a
disposable initialized Workspace, and confirm archive privacy tests exclude
Vault data. Passing these gates verifies the application source and release
artifacts; it does not claim that the separate real `ArxivLearn` Vault has
completed its Workspace v3 migration.

The release workflow creates a draft-first GitHub Release for
`vMAJOR.MINOR.PATCH` tags and publishes it only after asset verification.
PaperFlow source code is MIT licensed. A public
Feed must still declare its independent data licence; the current public data
repository uses CC BY 4.0. PyPI upload and remote publication require explicit
owner authorization.

Every PaperFlow 1.5 Release includes both reader integrations:

- `PaperFlow-Zotero-<version>.xpi` and `zotero-update.json`;
- `PaperFlow-Obsidian-<version>.zip`, containing the complete
  `paperflow-automation/` plugin directory;
- exact `main.js`, `manifest.json`, and `styles.css` assets for Obsidian
  release installers such as BRAT.

All of these files must appear in `dist/SHA256SUMS` and pass the packaging
audit before a tag is pushed.

PaperRead and ArXiv-data are released independently. A PaperRead tag publishes
software artifacts. An ArXiv-data push validates the Feed and builds the
`ArXiv-data-feed.zip` workflow artifact, but does not create or imply a
PaperRead software version.

Normal feature-branch commits and draft PR updates do not create a release.
Do not create a `v1.5.1` tag until the owner separately authorizes the public
GitHub Release. Never stage `.paperflow`, PDFs, current Vault notes, backups,
logs, databases, Community outbox content, or subscription caches.
