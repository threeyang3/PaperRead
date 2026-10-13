# 2026-10-13 source submission review

This review consolidates the migrated Windows environment work and the dual
Zotero/Obsidian workflow into an unreleased source update. Version remains 1.5.1;
preview artifacts are local, and this is not a formal release acceptance report.

## Changes and verified behavior

- Obsidian first-run initialization uses a read-only preview, approved digest,
  staged validation, configuration backup, exclusive file creation and a final
  Workspace marker. Existing files and concurrent personal edits are preserved.
- Core startup verifies authentication and exact Windows process identity.
  Exclusive binding prevents competing services from replacing session state.
  Current-user login startup supports enabled Core scheduling without Obsidian.
- Zotero settings support pairing in an empty library, device-based renewal,
  separated historical/current job failures and retry controls. Reader mirrors
  update the configured private Obsidian index without becoming public content.
- AI Markdown includes complete analysis sections; Feynman answers survive
  question reordering. Community draft submission requires an explicit approved
  snapshot and repeated privacy/integrity checks.
- Native Obsidian reload, workspace/path validation and authenticated Core start
  pass on the selected ArxivLearn Vault. Python regressions: 411 passed, 1 skipped;
  all nine JavaScript suites pass. Ruff and mypy checks pass. CI now runs all nine
  JavaScript suites. Source/document links and personal-file hashes are checked.

## Remaining acceptance scope

- Temporary initialization and extracted-wheel smoke tests use the existing
  development dependencies; a fresh Windows machine is not yet accepted.
- Zotero settings-preview2 was confirmed by the user. Preview4 job controls need
  native interaction acceptance. No new public Community content is submitted.
- Ordinary initialization exceptions roll back safely. Forced process termination
  or power loss can leave partial files requiring a new preview/manual review.
- Frontend plugins do not bundle Python, dependencies, AI credentials or Form Flow.

Machine-specific evidence and backups remain local under
`.paperflow/backups/submission-review-20261013` and the earlier dated audit folders.
