# Releasing

For PaperFlow 1.5.0 source release candidates, run:

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

The release workflow creates a published stable GitHub Release for
`vMAJOR.MINOR.PATCH` tags. PaperFlow source code is MIT licensed. A public
Feed must still declare its independent data licence; the current public data
repository uses CC BY 4.0. PyPI upload and remote publication require explicit
owner authorization.

PaperRead and ArXiv-data are released independently. A PaperRead tag publishes
software artifacts. An ArXiv-data push validates the Feed and builds the
`ArXiv-data-feed.zip` workflow artifact, but does not create or imply a
PaperRead software version.

Normal feature-branch commits and draft PR updates do not create a release.
Do not create a `v1.5.0` tag until the owner separately authorizes the public
GitHub Release. Never stage `.paperflow`, PDFs, current Vault notes, backups,
logs, databases, Community outbox content, or subscription caches.
