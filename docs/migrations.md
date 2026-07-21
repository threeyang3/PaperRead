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

# Visual asset migration

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

# Workspace schema 3

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

`rollback-workspace-v3` is dry-run by default. It restores only checksummed
files from a formal `pre-paperflow-1.5-*` backup and never deletes paths absent
from that backup, so later user-created files are preserved. Add `--apply` only
after reviewing the restore list.
