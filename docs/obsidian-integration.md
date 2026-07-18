# Obsidian integration

Manual paper entry remains official Form Flow 0.0.8+ and creates a validated
request file. The versioned integration bundle includes the form, request
template, script, compatibility metadata, and tests.

Install, inspect, repair, or upgrade with `paperflow integration`. If a user
changed a managed form or template, PaperFlow keeps it and writes the new
bundle as `.new` for merge review. Known managed files are backed up before
safe replacement.

Bases are generated from configured Base, paper-note, and Inbox roots.
Generated paper notes record `system_template_version: 2`. Re-rendering first
merges the User sidecar and existing `user_*` properties and preserves all text
inside `USER_NOTES_START/END`.

Recurring work uses the local `PaperFlow Automation` Obsidian plugin while
Obsidian is open. It registers file events after the Obsidian layout is ready,
debounces Form Flow request writes, performs a startup pass, keeps a five-minute
fallback interval, and checks the daily `Asia/Shanghai` schedule once per
minute. Windows Task Scheduler is neither installed nor required.

PaperFlow Automation 1.3.1 also provides a ribbon-accessible Control Center
for paper import, AI profile configuration, GitHub Feed subscriptions,
synchronization, publication preflight, and controlled Git commit/push. See
[PaperFlow Control Center](control-center.md).

When Obsidian uses Chinese, the plugin presents Chinese display labels for all
78 stable generated-paper properties without renaming the underlying YAML
keys. Original paper content remains unchanged. See
[PaperFlow 中文属性显示说明](中文属性显示说明.md).
