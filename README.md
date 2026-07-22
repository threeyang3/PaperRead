# PaperFlow

PaperFlow is a local-first, installable paper-learning workflow for arbitrary
Obsidian Vaults. It discovers and imports papers, validates PDFs, records
versioned source metadata, runs configurable Codex/Claude/ChatGPT Web/Mock analysis,
preserves personal reading data, renders Obsidian notes and Bases, and can
exchange privacy-scanned structured records through a Public Feed.

The application and each Vault are separate:

- the installable application lives in `src/paperflow`;
- every Vault has its own `.paperflow/workspace.yaml`;
- Raw and AI records are immutable/versioned;
- User Data remains local and is never published;
- Markdown, Bases, dashboards, briefs, PDF indexes, and read-only Community
  Notes are derived projections.
- private Annotations and Reviews remain local User data;
- Community Contributions are immutable opt-in public snapshots and
  subscription caches never become User or AI data.

Public software and public data are also separate:

- application code, releases, migrations, schemas, templates, and Obsidian
  integrations live in
  [`threeyang3/PaperRead`](https://github.com/threeyang3/PaperRead);
- the versioned, privacy-scanned subscription Feed lives in
  [`threeyang3/ArXiv-data`](https://github.com/threeyang3/ArXiv-data).

The code is MIT licensed. Published data records use CC BY 4.0, while linked
papers and third-party resources retain their original licenses.

## Install and initialize

Python 3.11 or newer is required.

```powershell
pipx install .
paperflow init --vault "D:\Notes\Research"
paperflow doctor
```

For automation, PaperFlow uses the Vault's `PaperFlow Automation` Obsidian
plugin while Obsidian is open. Manual paper entry remains the official Form
Flow plugin (`form-flow`) 0.0.8 or newer. Windows Task Scheduler is not used;
the visible `schedule` commands only remove or inspect legacy tasks. Hidden
compatibility names cannot install tasks; `run-now` directly invokes PaperFlow.

Chinese Obsidian locales receive Chinese UI labels, dashboards, prompts, and
generated explanation sections where practical. Original paper titles,
abstracts, quotations, citations, and extracted text are not mechanically
translated.

PaperFlow Automation 1.5.0 includes an Obsidian-native Control Center. It
opens automatically after the Obsidian workspace is ready (this can be
disabled in the plugin settings). Its first view is an extensible research task
workspace: collecting and discovering papers, browsing the library, continuing
the reading or reproduction queues, reviewing daily intake, analyzing imported
papers, and configuring an Agent are independent entry points. Feed
synchronization, publishing, migration, and maintenance are grouped under
Advanced tools. Open a generated paper note and run **PaperFlow: Open paper
reading workspace** to arrange the versioned PDF, private annotations, private
review, and read-only Community Note. PDF++ is recommended; native Obsidian
page links remain the fallback. These are independent capabilities.
The layout uses four distinct leaves: PDF and Review are explicitly anchored in
the main split, while Annotation and Community occupy separate right-sidebar
leaves; completion waits for and focuses the PDF leaf.
The installed plugin entry point is self-contained: `main.js` has no relative
runtime module dependency, so Obsidian Electron can load it independently of
the renderer's current working directory or CommonJS resolution base.
Use **PaperFlow: Create annotation from current PDF / selection** from the
command palette, ribbon, file menu, or Control Center. PDF++ 0.40.31 can supply
its selection-link syntax through a feature-detected command/clipboard adapter;
otherwise the modal uses a native page link and explicit text input. All saves
go through the PaperFlow CLI, private Annotation schema, conflict guard, and
index rebuild. The reading workspace asks the central CLI for the configured
per-paper index path instead of assuming a year-based folder; legacy index
files are retained and user-authored text is imported without duplication.
Direct PDF editing remains disabled.
There is no arbitrary shell input; remote push has a separate confirmation and
repeats validation and privacy scanning.

Imported PDFs now produce a caption-backed visual guide in each paper note.
For arXiv papers, PaperFlow first tries the version-pinned HTML reading page
and downloads the original single-image figure; unavailable or composite
figures safely fall back to PDF cropping.
Architecture, framework, overview, and pipeline figures are prioritized; the
original figure text and captions are not translated. Template v6 selects a
variable number of traceable figures by quality, semantic coverage, and
duplication, with 12 only as a safety ceiling. Captions collapse by default and every image records
its HTML/PDF provenance and links to its original PDF page. Existing papers can be updated from the Control
Center with **Extract paper figures** or with `paperflow paper visuals --all`.
The derived PNGs and manifests stay local and are excluded from Public Feeds.

Paper Workspace artifacts are separated by ownership: `10 Papers` is the
stable Paper Hub, `20 AI Analyses` contains generated analysis snapshots, and
`60 User Notes` contains prose that PaperFlow never regenerates. Existing
`USER_NOTES_START/END` blocks can be migrated with a backup and dry-run:
`paperflow migrate user-notes --dry-run` followed by `--apply`. Display titles
(`paper_display_title`/`paper_short_title`) are derived from the source title;
ID-based filenames remain stable and user aliases are preserved. Built-in and
custom Template Sets are managed with `paperflow templates list|copy|use|validate|preview`.
Templates receive a versioned Paper View Model and run inside a Jinja sandbox.
See [docs/paper-workspace-artifacts.md](docs/paper-workspace-artifacts.md).

Three Obsidian-native automation tracks can independently synchronize enabled
Feed subscriptions, run opt-in safety-gated publishing on a data-source host,
and discover/SHA256-stage stable PaperFlow releases. Applying an update remains
confirmation-gated and includes Workspace backup, runtime rollback, migration,
and plugin resource finalization. See
[docs/automation.md](docs/automation.md).

The tested capability, portability, packaging, and reproduction status is
recorded in [docs/verification-matrix.md](docs/verification-matrix.md).

## Core commands

```text
paperflow init
paperflow doctor
paperflow status
paperflow config ...
paperflow ai ...
paperflow paths ...
paperflow migrate ...
paperflow integration ...
paperflow annotation ...
paperflow review ...
paperflow community ...
paperflow paper ...
paperflow discover
paperflow daily
paperflow inbox
paperflow source ...
paperflow publish ...
paperflow workspace ...
paperflow update ...
```

The legacy `paperflow add` command remains available as an alias for
`paperflow paper add`.

## Safe migration

Before migrating an existing schema-2 Vault to PaperFlow 1.5:

```powershell
paperflow migrate workspace-v3 --dry-run
paperflow migrate workspace-v3 --apply
paperflow migrate verify-workspace-v3
paperflow migrate rollback-workspace-v3 --dry-run
paperflow migrate history
```

Workspace v3 copies PDFs into immutable vN paths, re-renders existing notes
through the central compose/render path, and verifies PDF hashes plus note
links while preserving `user_*`, user tags and bounded user notes. Its explicit
rollback is dry-run by default, restores only checksummed formal-backup files,
and does not delete later user-created paths. Legacy files are preserved.

The same `workspace-v3 --apply` command is deliberately re-runnable on schema
3. It repairs a partial 1.5 migration by atomically updating rebuildable
Derived PDF path fields before re-rendering; Raw, AI, User and visual PNG paths
are not changed. A failed final verification reports
`status=verification-failed` and exits non-zero while retaining the formal
backup.

## Public Feed safety

`paperflow publish build` only creates a local, deterministic Feed.
`paperflow publish scan` blocks user fields, user-note markers, local paths,
credentials, logs, SQLite files, and PDFs. PDF policy is link-only by default.
Build and Git push are intentionally separate.

Feed v2 keeps v1 Raw/AI paths and adds optional Community records. Community
publishing is disabled by default. Quotes are capped at 500 characters; active
content, images and PDFs are rejected. Subscribers recompute the publisher's
canonical `content_sha256` and reject altered revisions before cache writes.
`community publish submit-pr` remains a local dry-run until separately approved.

PaperFlow source code is available under the MIT License. Each public Feed
declares its own data licence; this workspace publishes Feed data under
CC BY 4.0 and retains source-paper attribution and licence metadata.

## Documentation

- [用户与维护者中文总指南](docs/维护者与用户指南.md)
- [PaperFlow 1.5 用户与维护者指南](docs/PaperFlow-1.5-用户与维护者指南.md)
- [私有标注与评审](docs/annotations-and-reviews.md)
- [PDF 版本](docs/pdf-versioning.md)
- [PDF++ 集成](docs/pdf-plus-integration.md)
- [社区贡献](docs/community-contributions.md)
- [社区订阅](docs/community-subscriptions.md)
- [Feed v2](docs/feed-v2.md)
- [社区隐私与版权](docs/community-privacy-copyright.md)
- [阅读工作区](docs/reading-workspace.md)
- [1.5 迁移指南](docs/1.5-migration-guide.md)
- [PaperFlow 1.4 用户指南](docs/用户指南-1.4.md)
- [PaperFlow 1.4 维护者指南](docs/维护者指南-1.4.md)
- [ChatGPT 网页分析与隐私](docs/ChatGPT网页分析与隐私.md)
- [Nutstore Sync 兼容建议](docs/Nutstore兼容建议.md)
- [1.4 迁移指南](docs/1.4迁移指南.md)
- [Installation](docs/installation/windows.md)
- [Configuration](docs/configuration.md)
- [Architecture and data layers](docs/architecture.md)
- [Migrations](docs/migrations.md)
- [AI providers](docs/ai-providers.md)
- [Obsidian integration](docs/obsidian-integration.md)
- [中文属性显示说明](docs/中文属性显示说明.md)
- [论文图片处理说明](docs/论文图片处理说明.md)
- [Obsidian Control Center](docs/control-center.md)
- [Public Feed](docs/public-feed.md)
- [Repository separation](docs/repository-separation.md)
- [Obsidian-native automation](docs/automation.md)
- [Security and privacy](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
