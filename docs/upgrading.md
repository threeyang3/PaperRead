# Upgrading

Five operations are deliberately separate:

1. **Upgrade the application** with pipx, uv, pip, or a new portable package.
2. **Upgrade the Workspace** with `paperflow update workspace` after reviewing
   `paperflow migrate plan`.
3. **Sync public paper data** with `paperflow source sync`.
4. **Reanalyse a paper** with `paperflow paper analyze`; old AI records remain.
5. **Re-render Markdown** with `paperflow paper render`; User Data is merged.

PaperFlow 1.3.1 can discover stable releases from a fixed GitHub repository and
stage a wheel only after checking `SHA256SUMS`. Discovery and verified staging
may run automatically inside Obsidian. Applying an update remains
confirmation-gated: PaperFlow backs up the Workspace, validates the new runtime
in isolation, preserves the previous runtime for rollback, then migrates the
Workspace and upgrades versioned Obsidian resources.

Package-manager installation remains supported and is the recovery path when a
release changes dependencies in a way that the existing managed runtime cannot
import.

After upgrading an existing Workspace to PaperFlow 1.3.2, run
`paperflow migrate visual-assets` once to back up the Workspace, activate
template v4, and regenerate a category-balanced visual guide with up to six
caption-backed Derived figures per local PDF. Official template v3 is upgraded
automatically; customized templates are emitted as `.new` merge candidates.
