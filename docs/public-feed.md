# Public PaperFlow Feed

- Applies to PaperFlow 1.5.x
- Workspace schema: 3
- Feed schema: 2

A Feed v2 publishes normalized Raw records, versioned AI records, schemas,
deterministic manifests, hashes, attribution, and original PDF URLs. It does
not publish User Data, rendered notes, Vault paths, logs, databases, cache,
credentials, sessions, or PDFs by default.

Remote `feed_id`, `paper_uid`, `source_id`, provider, analysis, creator and
contribution identifiers are data, never paths. Readers reject path-shaped
identifiers and encoded/NFKC collisions, then resolve every target below its
managed root and reject symlink escapes. The identical checks run for dry-run;
an unsafe Feed fails without changing `.paperflow` or writing outside the
Vault/Core root. Logical IDs such as `arxiv:2607.00001` remain unchanged in
records while storage keeps the schema-3-compatible `arxiv_2607.00001` layout.

Build locally with `publish plan`, `build`, `validate`, `scan`, and `diff`.
Build never commits or pushes. A separate data repository should be reviewed
and pushed explicitly.

Community capability is optional and disabled by default. It contains only
explicit immutable snapshots after privacy/copyright scanning, under per-paper
manifests. Feed v1 remains accepted as Raw/AI-only.

Feed v2 adds independent `raw`/`ai`/`community` capabilities,
`community_data_schema_version`, per-paper Community manifests, contributor
profiles, revisions, supersession, and retractions. Raw/AI paths remain
compatible with v1. A 1.5 reader can consume v1; an older reader must reject
unsupported v2 data instead of guessing.

Subscription trust modes are `metadata-only`, `metadata-and-ai`, and
`disabled`. Sync validates reader/schema versions and every checksum, imports
immutable data, preserves conflicting analyses, and never executes remote
scripts, plugins, commands, local paths, or configuration.

## Build safety and interrupted updates

PaperFlow builds and validates a clean sibling staging tree before it changes
the destination. Only `.gitattributes`, `feed.yaml`, `manifests/`, `papers/`,
`schemas/`, and `checksums/` are managed; `.git/`, README files, and other
publisher-owned files are preserved.

The managed-tree update writes a destination-bound transaction journal and a
complete backup before copying any managed path. Ordinary failures roll back
immediately. If the process or host is terminated during the copy, the next
Feed build detects the journal, restores and verifies the previous managed
inventory, and only then starts a new staged build. Do not manually delete
`.feed-name.paperflow-sync.json` or its sibling transaction directory; an
invalid or incomplete journal is reported as an error and requires inspection.
