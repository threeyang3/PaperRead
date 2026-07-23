# Public PaperFlow Feed

A Feed v2 publishes normalized Raw records, versioned AI records, schemas,
deterministic manifests, hashes, attribution, and original PDF URLs. It does
not publish User Data, rendered notes, Vault paths, logs, databases, cache,
credentials, sessions, or PDFs by default.

Build locally with `publish plan`, `build`, `validate`, `scan`, and `diff`.
Build never commits or pushes. A separate data repository should be reviewed
and pushed explicitly.

Community capability is optional and disabled by default. It contains only
explicit immutable snapshots after privacy/copyright scanning, under per-paper
manifests. Feed v1 remains accepted as Raw/AI-only.

Subscription trust modes are `metadata-only`, `metadata-and-ai`, and
`disabled`. Sync validates reader/schema versions and every checksum, imports
immutable data, preserves conflicting analyses, and never executes remote
scripts, plugins, commands, local paths, or configuration.
