# Obsidian integration

Manual paper entry remains official Form Flow 0.0.8+ and creates a validated
request file. The versioned integration bundle includes the form, request
template, script, compatibility metadata, and tests.

Install, inspect, repair, or upgrade with `paperflow integration`. If a user
changed a managed form or template, PaperFlow keeps it and writes the new
bundle as `.new` for merge review. Known managed files are backed up before
safe replacement.

Bases are generated from configured Base, paper-note, and Inbox roots.
Generated paper notes record `system_template_version: 6`. Re-rendering first
merges the User sidecar and existing `user_*` properties and preserves all text
inside `USER_NOTES_START/END`.

Template v6 keeps searchable metadata in YAML while removing repeated metadata and
empty boilerplate from the body. It adds a bilingual, adaptive category-grouped visual guide backed by local,
checksummed PDF figure crops. Original captions fold by default, and every
figure links to the source PDF page. Existing Workspaces use
`paperflow migrate workspace-v2 --apply`; routine refresh is available as
`paperflow paper visuals --all`.

The development preview adds a first-run wizard for an existing, uninitialized
Vault. It detects an installed Python/Core environment, previews managed files,
backs up configuration, refuses collisions, and offers Core pairing and Form
Flow preparation. Python, Core dependencies, and Form Flow require separate
installation; the two frontend plugins alone do not provide a runtime.
See [Windows installation](installation/windows.md).

Core can own recurring work independently of Obsidian. The local
`PaperFlow Automation` plugin retains compatibility scheduling while Obsidian
is open and yields to a verified Core owner. It registers file events after the Obsidian layout is ready,
debounces Form Flow request writes, performs a startup pass, keeps a five-minute
fallback interval, and checks the daily `Asia/Shanghai` schedule once per
minute. Core can optionally use a Windows current-user login task;
the legacy pipeline scheduler does not install tasks. See [automation](automation.md).

PaperFlow Automation 1.5.1 also provides a ribbon-accessible Control Center
for paper import, AI profile configuration, GitHub Feed subscriptions,
synchronization, publication preflight, and controlled Git commit/push. See
[PaperFlow Control Center](control-center.md).

When Obsidian uses Chinese, the plugin presents Chinese display labels for all
85 generated-paper properties, including source/display titles and relationship
projections, without renaming the underlying YAML keys. Original paper content remains unchanged. See
[PaperFlow 中文属性显示说明](中文属性显示说明.md).

The command **Open paper reading workspace** opens the current versioned PDF
and separate Annotation, Review, and Community projections. Official PDF++ is
recommended and managed through `paperflow integration pdf-plus`; PaperFlow
does not call its private API and falls back to native page links.

The Automation plugin adds a bilingual annotation modal to the command palette,
ribbon, PDF/paper file menu, reading workflow, and Control Center. Its optional
PDF++ adapter feature-detects `pdf-plus:copy-link-to-selection`, invokes it in an
isolated failure boundary, reads and validates the clipboard result, then
prefills the modal. It never enables direct PDF editing. Missing commands,
clipboard denial, or an unverifiable selection fall back to an explicit page
and selected-text form. Saving calls the PaperFlow CLI allowlist; the plugin
does not bypass the Annotation schema or Nutstore conflict checks.

The layout creates four distinct leaves. Review is split directly from the PDF
leaf with `createLeafBySplit`; Annotation and Community use separate right-side
leaves. The command awaits `revealLeaf(pdfLeaf)` and then focuses that PDF leaf,
so a successful command means all four files are open and the PDF is visible.

Before arranging that layout, the plugin runs the allowlisted
`annotation ensure-index` command and opens the configured path returned by
the CLI. It does not hard-code a year or the default Annotation root. Index
rebuilds preserve user-authored Markdown and leave legacy index files intact.

The Automation plugin ships a self-contained `main.js`. Reading-workspace code
is bundled into that entry point; startup does not use relative `require()`
calls whose resolution could depend on Electron's renderer context or cwd.
