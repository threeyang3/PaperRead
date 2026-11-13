# Releasing

## 1.5 post-audit Release Candidate gate

CI and tag-triggered Release call `.github/workflows/quality-gates.yml`. Routine CI
uses a reduced platform matrix; **Release explicitly requests the full gate**.
The release gate still covers Python 3.11–3.13 on Windows, Ubuntu and macOS,
locked/latest-compatible dependencies, all Python tests, five Node integration
entries, Ruff, format, Mypy, coverage, pip-audit, Feed/migration contracts,
build, packaging, wheel install, initialized-workspace/Doctor smoke and the
real Windows Offline Installer smoke. Ubuntu/Python 3.13 is covered by the
quality/coverage job instead of a second identical full pytest job.

## CI frequency and scope

- Automatic validation runs once for a main push or PR; feature-branch pushes
  do not start a second copy. New commits cancel superseded validation only.
  Release has no cancellation group and still waits for all quality gates.
- Routine application, test, schema, template and prompt changes run Linux
  Python 3.13 full pytest/coverage, static checks, version checks, dependency
  audit and the five Linux Node integration entries. The full pytest includes
  the golden workflow, Feed, migrations, compatibility and packaging tests.
- OS/path/storage integration, dependencies, installers/build tooling,
  workflows and unknown files additionally run the full compatibility matrix
  and Windows release build. Expensive Python jobs wait for the base quality
  gate. Scope rules and real multi-commit/rename/PR-range tests live in
  `.github/ci_scope.py` and `.github/test_ci_scope.py`.
- Documentation-only changes run a Linux package build/audit because docs,
  README and licence files are shipped in the sdist/install archives. They do
  not run unrelated cross-platform tests. Templates/prompts are product
  inputs, not documentation-only changes.
- `Build`, `Feed validation` and `Migration tests` are manual diagnostic
  workflows; their checks remain in automatic CI, without duplicate runs.
- **Before release**, require the final commit's full checks: use CI → Run
  workflow for manual verification when necessary. A version tag always runs
  the full reusable gates before publication, even for documentation-only
  changes. Never reuse a result from a different commit or skip a required
  gate to save minutes. Do not create a tag without release authorization.
- Validate locally and batch related changes before pushing. Dependencies are
  cached, but installs, audits and required checks still run. Do not repeatedly
  retry quota failures or deterministic test failures.

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
