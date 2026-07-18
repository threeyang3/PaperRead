# PaperFlow

PaperFlow is a local-first, installable paper-learning workflow for arbitrary
Obsidian Vaults. It discovers and imports papers, validates PDFs, records
versioned source metadata, runs configurable Codex/Claude/Mock analysis,
preserves personal reading data, renders Obsidian notes and Bases, and can
exchange privacy-scanned structured records through a Public Feed.

The application and each Vault are separate:

- the installable application lives in `src/paperflow`;
- every Vault has its own `.paperflow/workspace.yaml`;
- Raw and AI records are immutable/versioned;
- User Data remains local and is never published;
- Markdown, Bases, dashboards, and briefs are derived projections.

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

PaperFlow Automation 1.3.2 includes an Obsidian-native Control Center. It
opens automatically after the Obsidian workspace is ready (this can be
disabled in the plugin settings). Its first view is an extensible research task
workspace: collecting and discovering papers, browsing the library, continuing
the reading or reproduction queues, reviewing daily intake, analyzing imported
papers, and configuring an Agent are independent entry points. Feed
synchronization, publishing, migration, and maintenance are grouped under
Advanced tools.
There is no arbitrary shell input; remote push has a separate confirmation and
repeats validation and privacy scanning.

Imported PDFs now produce a caption-backed visual guide in each paper note.
Architecture, framework, overview, and pipeline figures are prioritized; the
original figure text and captions are not translated. Existing papers can be
updated from the Control Center with **Extract paper figures** or with
`paperflow paper visuals --all`. The derived PNGs and manifests stay local and
are excluded from Public Feeds.

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

Before migrating an existing Vault:

```powershell
paperflow migrate status
paperflow migrate plan
paperflow migrate apply
paperflow migrate verify
paperflow migrate history
```

Migration acquires a Workspace lock, hashes inputs, snapshots affected files,
writes and validates staging data, atomically installs records, verifies the
SQLite index and note links, and restores on failure. Legacy files are
preserved, and unknown properties move into `extensions`.

## Public Feed safety

`paperflow publish build` only creates a local, deterministic Feed.
`paperflow publish scan` blocks user fields, user-note markers, local paths,
credentials, logs, SQLite files, and PDFs. PDF policy is link-only by default.
Build and Git push are intentionally separate.

PaperFlow source code is available under the MIT License. Each public Feed
declares its own data licence; this workspace publishes Feed data under
CC BY 4.0 and retains source-paper attribution and licence metadata.

## Documentation

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
- [Security and privacy](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
