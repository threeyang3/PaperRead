# Architecture and data layers

PaperFlow separates the installed application, per-user Workspace, Obsidian
Vault projections, Public Feed, and local User Data.

## Four data layers

- **Raw**: immutable source/version snapshots containing factual metadata and
  source URLs, never AI scores or user state.
- **AI**: immutable append-only analyses keyed by paper content hash, provider,
  model, prompt version, schema version, and analysis profile.
- **User**: local sidecars plus `user_*` Obsidian properties. Existing note
  values and user tags are merged and never overwritten by Feed sync.
- **Derived**: Markdown notes, Bases, dashboards, briefs, indexes, and caches;
  these can be rebuilt only after merging User Data.

Schema and application versions are independent. Data newer than the installed
reader is rejected; older data requires an explicit migration.
