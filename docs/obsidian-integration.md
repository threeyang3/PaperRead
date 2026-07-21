# Obsidian integration

Manual paper entry remains official Form Flow 0.0.8+ and creates a validated
request file. The versioned integration bundle includes the form, request
template, script, compatibility metadata, and tests.

Install, inspect, repair, or upgrade with `paperflow integration`. If a user
changed a managed form or template, PaperFlow keeps it and writes the new
bundle as `.new` for merge review. Known managed files are backed up before
safe replacement.

Bases are generated from configured Base, paper-note, and Inbox roots.
Generated paper notes record `system_template_version: 5`. Re-rendering first
merges the User sidecar and existing `user_*` properties and preserves all text
inside `USER_NOTES_START/END`.

Template v5 adds a bilingual, adaptive category-grouped visual guide backed by local,
checksummed PDF figure crops. Original captions fold by default, and every
figure links to the source PDF page. Existing Workspaces use
`paperflow migrate workspace-v2 --apply`; routine refresh is available as
`paperflow paper visuals --all`.

Recurring work uses the local `PaperFlow Automation` Obsidian plugin while
Obsidian is open. It registers file events after the Obsidian layout is ready,
debounces Form Flow request writes, performs a startup pass, keeps a five-minute
fallback interval, and checks the daily `Asia/Shanghai` schedule once per
minute. Windows Task Scheduler is neither installed nor required.

PaperFlow Automation 1.5.0 also provides a ribbon-accessible Control Center
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

The Automation plugin ships a self-contained `main.js`. Reading-workspace code
is bundled into that entry point; startup does not use relative `require()`
calls whose resolution could depend on Electron's renderer context or cwd.
