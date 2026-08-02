# Upgrading

Five operations are deliberately separate:

1. **Upgrade the application** with pipx, uv, pip, or the wheel inside a new
   Offline Installer Bundle.
2. **Upgrade the Workspace** with `paperflow update workspace` after reviewing
   `paperflow migrate plan`.
3. **Sync public paper data** with `paperflow source sync`.
4. **Reanalyse a paper** with `paperflow paper analyze`; old AI records remain.
5. **Re-render Markdown** with `paperflow paper render`; User Data is merged.

PaperFlow 1.5.1 can discover stable releases from a fixed GitHub repository and
stage a wheel only after checking `SHA256SUMS`. Discovery and verified staging
may run automatically inside Obsidian. Applying an update remains
confirmation-gated: PaperFlow backs up the Workspace, validates the new runtime
in isolation, preserves the previous runtime for rollback, then migrates the
Workspace and upgrades versioned Obsidian resources.

Package-manager installation remains supported and is the recovery path when a
release changes dependencies in a way that the existing managed runtime cannot
import.

After upgrading an existing Workspace to PaperFlow 1.4.0, run
`paperflow migrate workspace-v2 --apply` once to back up the Workspace,
activate template v5, restore Derived visual embeds, and rebuild relationship
projections. Customized templates are emitted as `.new` merge candidates.

Program releases are discovered from PaperRead. ArXiv-data is an independent
paper-data subscription and must never be used as an application update source.

After installing 1.5.1, run `paperflow migrate workspace-v3 --dry-run`, review
the per-paper PDF copy plan, then apply and verify Workspace v3. Old PDFs remain
rollback material; migration does not enable Community publication.

For template bundle v6 and HTML-first figure extraction, run
`paperflow migrate visual-assets --dry-run` and then `--apply`. Custom templates
remain merge candidates; user fields, tags, and `USER_NOTES_START/END` are preserved.
