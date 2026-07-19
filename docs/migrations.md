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
