# Security and privacy

- AI processes receive staged paper inputs only and cannot edit the Vault.
- Paper, LaTeX, repository, Feed, and install scripts are never executed as
  content.
- Codex/Claude credentials and global configuration are never read or copied.
- Public Feed scanning blocks `user_*`, user-note markers, absolute local
  paths, likely secrets, logs, SQLite, and unlicensed PDFs.
- Raw and AI snapshots are immutable; User Data is local and merge-protected.
- Migration and integration replacement operations use backups and atomic
  writes.
- `workspace.local.yaml`, runtime data, backups, logs, PDFs, and current Vault
  notes must remain outside source and release artifacts.
- PDF-derived PNGs and their local manifests remain Derived Workspace data;
  Public Feed builds do not include them.
