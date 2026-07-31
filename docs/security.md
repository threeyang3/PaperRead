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
- Private Annotation/Review data never enters the public outbox implicitly.
- Community snapshots reject local paths, email/credentials, active HTML,
  unsafe URI schemes, images/PDFs, payloads over 64 KiB, and source quotations
  over 500 characters.
- Zotero integration binds only to loopback and requires authenticated bearer
  sessions for data routes. Initial pairing stores a device secret only in
  Zotero local preferences; Core stores its hash and can rotate the short-lived
  session after restart. Session tokens, pairing secrets, and `auth.json` are
  classified as `SECRET` even when located under runtime/state directories.
- Zotero writes use public object APIs only. PaperFlow never reads or modifies
  `zotero.sqlite`, and annotation mirrors are SYSTEM_MANAGED read-only copies
  of Zotero Reader data.
