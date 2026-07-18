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

Template bundle v3 adds the caption-backed visual guide without changing the
flat paper YAML schema. Existing Workspaces migrate generated data with:

```powershell
paperflow migrate visual-assets
```

The command acquires the Workspace lock, creates a complete Workspace backup,
updates the template contract, extracts local PDF figures, persists only
Derived records, and rerenders notes through the normal merge-safe renderer.
Customized templates that lack the visual block are emitted as `.new` merge
candidates and are never overwritten. The operation is idempotent and can be
rerun after a per-paper failure.
