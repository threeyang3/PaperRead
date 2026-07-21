# Repository separation

PaperFlow uses two public GitHub repositories with different responsibilities:

| Repository | Purpose | License | Update trigger |
| --- | --- | --- | --- |
| `threeyang3/PaperRead` | Python application, schemas, migrations, templates, Obsidian integrations, tests and releases | MIT | reviewed software changes |
| `threeyang3/ArXiv-data` | generated Raw metadata, validated AI analyses, manifests and checksums | CC BY 4.0 | safety-gated data publication |

The split prevents a routine paper refresh from creating a software release and
prevents application source changes from altering the subscribed data history.
It also gives each artifact an accurate license and a stable URL.

## Data boundary

`ArXiv-data` may contain only:

- normalized source metadata;
- schema-valid AI analysis with complete provenance;
- feed manifests, schemas and checksums;
- explicitly selected, licensed and canonical-hash-verified Community
  contribution revisions when that capability is intentionally enabled;
- repository documentation and validation automation.

It must not contain PDFs, extracted full text, rendered notes, User records,
credentials, local paths, logs, databases, caches or executable content supplied
by a publisher.

PaperFlow enforces this boundary with `publish build`, `publish validate` and
`publish scan` before any commit or push. Subscribers clone the repository as
data, validate it, recompute Community `content_sha256`, and never execute
repository content. PaperRead feature branches and PRs contain application
code only; they must not carry a real Vault outbox or user contribution.

## Branches and automation

Both repositories use `main` as their default branch. PaperRead runs
cross-platform tests, build, migration and Feed-compatibility checks; tagged
software releases remain a separate owner-authorized action. ArXiv-data runs
its own validate-and-package workflow on pushes and pull requests. That
workflow installs the validator from PaperRead `main`, validates all records
and checksums, runs the public-data scan, and uploads a portable Feed ZIP.

The canonical subscription endpoint remains:

```text
https://github.com/threeyang3/ArXiv-data.git
```

The PaperFlow 1.5 source and simulated migration tests can be complete while
the real `ArxivLearn` Vault is still on Workspace schema 2. That Vault's
dry-run, apply, link verification, Doctor and audit belong to the separate
Vault project and are never performed by pushing PaperRead.
