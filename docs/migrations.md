# Migrations

Every versioned data migration declares a unique ID, source/target versions, affected data
types, reversibility, plan, apply, verify, and rollback behaviour.

`migrate plan` is read-only and reports every source hash and target path.
`migrate apply` obtains the Workspace-global lock, snapshots sources, writes
staging data, validates it, atomically installs files, logs history, validates
SQLite and note paths, and restores affected targets if any step fails.

Legacy mixed records are preserved. Known properties are separated into Raw,
AI, User, and Derived records; unknown properties are retained in
`extensions`. The migration performs no downloads and makes no AI calls.

## Visual asset migration

Template bundle v6 removes duplicated metadata and empty generated sections,
compresses generated whitespace while preserving the user-notes boundary, and
prefers version-pinned arXiv HTML originals with PDF-crop fallback. Apply it with
`paperflow migrate visual-assets --apply`; the command backs up the Workspace,
rebuilds Derived manifests, installs templates, and re-renders through the central
composer.

Template bundle v5 expands the caption-backed visual guide and adds formally
migrated relationship projections to the flat paper YAML schema. It adaptively groups figures by architecture/method,
experiments/results, and task/hardware context, folds source captions, and links
each figure to its PDF page. Existing Workspaces migrate generated data with
`paperflow migrate workspace-v2 --apply`.

For the complete 1.4 migration use:

```powershell
paperflow migrate workspace-v2 --dry-run
paperflow migrate workspace-v2 --apply
paperflow migrate verify-workspace-v2
```

The legacy `paperflow migrate visual-assets` command remains available when
only Derived images need to be re-extracted. Customized templates are emitted
as `.new` merge candidates and are never overwritten.

## Workspace schema 3

```powershell
paperflow migrate workspace-v3 --dry-run
paperflow migrate workspace-v3 --apply
paperflow migrate verify-workspace-v3
paperflow migrate rollback-workspace-v3 --dry-run
```

This backs up `.obsidian`, private/community data and every PDF; copies current
PDFs to immutable vN paths; keeps legacy files; builds pdf-index records; adds
Annotation/Review/Community roots; re-renders existing paper notes through the
central compose/render path while preserving user fields, tags and bounded user
notes; verifies note/PDF links; and rebuilds every Base. Network, AI, public PR,
and old-PDF deletion counts are zero.

The migration atomically updates the aggregate compatibility record and the
rebuildable Derived PDF path fields that `compose_record()` applies last.
Extraction/visual source PDF fields are updated only when they use the modeled
PDF path keys; visual PNG asset paths and PDF hashes remain unchanged.

Running `workspace-v3 --apply` again on schema 3 enters repair mode and reuses
the existing formal pre-1.5 backup. It is the supported recovery for a partial
1.5 apply with stale Derived paths. Verification failure produces
`status=verification-failed` and a non-zero CLI exit instead of reporting a
successful apply.

`rollback-workspace-v3` is dry-run by default. It restores only checksummed
files from a formal `pre-paperflow-1.5-*` backup and never deletes paths absent
from that backup, so later user-created files are preserved. Add `--apply` only
after reviewing the restore list.
