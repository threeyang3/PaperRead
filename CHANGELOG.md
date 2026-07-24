# Changelog

## 1.5.0 - 2026-07-21

- Added template bundle v6: queryable metadata stays in YAML while generated
  body duplication, empty boilerplate sections, and excessive blank lines are
  removed without changing preserved user notes.
- AI analysis snapshots now project recommendation, scores, and provenance into
  properties and omit Hub-only recommendation/provenance blocks from the body.
- Preferred version-pinned original arXiv HTML PNG figures, with strict host,
  content-type, size, and image validation plus caption-backed PDF crop fallback.
- Made private Annotation/Review selection project into the public Community
  contract, excluding local PDF paths and coordinates; normalized before hashing.
- Rendered verified Community subscriptions into visible read-only per-paper notes,
  and added regression coverage proving Markdown edits cannot alter Feed AI data.
- Unified AnnotationStore, the visible per-paper index, and the reading
  workspace on the configured Annotation root without a hard-coded year.
  Index rebuilds atomically refresh the visible note, preserve user content,
  and import user-authored legacy year-scaffold content without deleting the
  legacy file.
- Normalized HTML-escaped PDF++ links (`&amp;`) before parsing selection and
  color, and added the central `annotation ensure-index` command.
- Bumped the Automation integration resource contract to 10 for the updated
  reading-workspace/index handshake.
- Added the formal `paths-0002-readable-redirect-labels` migration: legacy
  ID-only paper paths now show the target title and an explicit open-note link;
  user-authored redirect text is held for manual review.
- Added entity navigation documentation clarifying the intentional separation
  of Topic, Method, and Dataset projections (including the two Diffusion Policy
  views) and their same-layer duplicate normalization.
- Added a loopback-only, GET-only Zotero Local API adapter plus reproducible
  migration plan/apply-result/verify/rollback commands. Plans include PDF
  source hashes and Collection membership but never write Zotero objects.
- Added standalone Core Data Root planning/initialization, while preserving the
  existing Vault `.paperflow` layout, and added guarded Zotero Item Tree columns,
  Item Pane status projection, and one-second Notifier debounce adapters.
- Added a Core-side Zotero Connector event state machine that waits for a regular
  item, stable PDF, configured Collection, and resolved identity before queuing
  analysis; repeated PDF hash/profile pairs become complete without re-analysis.
- Added an authenticated Zotero Core client with explicit loopback session pairing,
  public-API event publishing, manual analysis enqueue, subscription preview, and
  community publish preview menus; bearer tokens remain in Zotero local preferences.
- Added a SYSTEM_MANAGED Zotero annotation mirror for highlights, underlines, image
  annotations, comments, colors, tags, pages, positions, and deletion state; old
  Obsidian private annotations remain untouched.
- Added a guarded Core worker that consumes analysis/render jobs only for a configured
  PaperFlow Workspace under the existing pipeline lock; standalone Data Roots remain
  queue-only and Windows stop now removes stale session/token files after verified exit.
- Persisted Core analysis, render, and subscription jobs under `state/jobs`, added
  authenticated job/list endpoints, and made Zotero's status action show recent
  job states while recovering queued work after a Core restart.
- Added reader-focused Zotero AI Markdown projections with compact frontmatter,
  explicit SYSTEM_MANAGED permission, content-hash conflict refusal, and a
  plugin-required attachment plan; Obsidian user outputs remain separate.
- Added reverse Topic/Method/Dataset indexes with explicit Chinese entity-type
  labels; `paperflow migrate entity-index` refreshes only the generated paper
  list section and preserves entity prose.
- Fixed manual imports and Feed subscription rendering to use the configured
  readable Paper Hub filename template instead of silently creating new
  ID-only Markdown files; updates keep the persisted note path. Generated
  Topic/Method pages now show same-label counterpart links when both views
  exist.
- Added a single `_version.py` application-version source and Workspace 3,
  Feed 2, Annotation 1, and Community 1 contracts.
- Made PDFs immutable and version-addressed, with SHA-256 indexes and explicit
  revision-preserving reanchor workflows.
- Added plugin-independent private Annotation and Review protocols with
  Markdown truth, rebuildable JSON, conflict refusal, selectors, and anchors.
- Added the official PDF++ integration with compatibility checks,
  non-overwriting configuration, `.new` candidates, native-link fallback, and
  direct-PDF-editing disabled by default.
- Added opt-in Community Contributions, privacy/copyright scanning, local
  outbox, dry-run GitHub PR planning, revisions/retractions, read-only
  subscription cache, separate notes, preferences, and ratings.
- Added Feed v2 capability negotiation and per-paper Community manifests while
  retaining v1 Raw/AI paths.
- Added the Obsidian reading workspace, five parallel feature entrances, and
  six corresponding Bases.
- Added Workspace v3 migration; old PDFs are copied to vN paths and never
  deleted.
- Made Workspace v3 re-render existing paper notes through the central
  compose/render path, preserve user fields/tags/notes, and verify migrated
  PDF links.
- Added a formal-backup-only Workspace v3 rollback that defaults to dry-run and
  never deletes paths absent from the backup.
- Recomputed Community contribution `content_sha256` during subscription
  ingestion and rejected tampered revisions before cache writes.
- Fixed Workspace v3 rendering when the rebuildable Derived layer still held a
  legacy `paper_pdf_path`; migration now atomically updates modeled Derived PDF
  source paths before composing notes while preserving visual PNG paths.
- Made `workspace-v3 --apply` safely repair an already-schema-3 partial
  migration using its existing formal backup, and return a non-zero CLI result
  with `status=verification-failed` whenever final verification is not clean.
- Bundled the reading-workspace implementation into the Automation plugin's
  `main.js`, removing its Electron-incompatible runtime dependency on
  `require("./reading-workspace")`.
- Fixed reading-workspace layout creation by anchoring the Review split to the
  PDF leaf, awaiting PDF reveal, and explicitly focusing the visible PDF leaf.
- Added a bilingual PDF annotation loop to the Automation plugin: command
  palette, ribbon, file-menu, reading-workspace and Control Center entries;
  optional feature-detected PDF++ selection capture; explicit manual fallback;
  and central CLI writes with automatic private-index refresh.
- Bumped the Automation integration resource contract to 9 so an existing
  1.5.0 installation safely stages the updated single-file plugin resources.
- Separated PDF++ four-integer selection coordinates from quoted text, retained
  versioned page/selection/color links, and kept Annotation schema v1 backward
  compatible without fabricating selectors from legacy free text.

## 1.4.0 - 2026-07-19

- Released the PaperFlow 1.4.0 implementation contract: Workspace schema 2,
  template v5, and `paper-analysis-v3`.
- Added strict UTF-8 quality gates, source/display title separation, immutable
  Raw captures, and repair-oriented Workspace health reporting.
- Added a consent-gated Playwright/Edge ChatGPT Web provider with dedicated
  external browser state, strongest-visible-model selection, staged PDF
  uploads, schema validation, and fail-closed user handoff.
- Unified every render path through Raw/AI/User/Derived composition so
  subscription refreshes retain existing figure embeds.
- Added adaptive visual selection, citation/semantic relationship separation,
  topic/method/dataset entity notes, and backlinks-friendly YAML projections.
- Separated plugin static settings from runtime state and added concurrent
  write/conflict refusal for Nutstore-compatible operation.
- Added formal Workspace v2 migration plus curated portable and template-Vault
  release artifacts.

- Added a unified Chinese guide for users and maintainers, covering setup,
  Obsidian-native operation, repository ownership, testing, packaging,
  publishing, upgrades, and recovery.
- Separated the MIT-licensed PaperRead application from the CC BY 4.0
  `ArXiv-data` public subscription Feed.
- Verified real Claude Code 2.1.206 analysis through Xiaomi `mimo-v2.5` on the
  π0, FAST, and π0.5 paper series.
- Made Claude structured output compatible with its JSON Schema parser while
  retaining full Draft 2020-12 validation after inference.
- Added adaptive caption-backed paper visuals with semantic coverage,
  deduplication, a configurable safety ceiling, grouped presentation, folded
  original captions, and direct links to the source PDF page.
- Tightened architecture classification and crop fallbacks after visual QA on
  Diffusion Policy, NIST IDB, TacForeSight, and RoboTTT PDFs.
- Added architecture-first Obsidian Cards views for the full paper library,
  tactile papers, and daily intake while retaining sortable table views; card
  metadata labels now follow the Chinese Obsidian locale.
- Made existing-paper AI analysis fully local-first: it reuses the stored
  metadata, extracted text, PDF, and visual manifest without querying arXiv or
  attempting to rewrite immutable Raw records.
- Rejected generic or bibliography-only GitHub and dataset links, and verified
  the official Octo and OpenVLA project, code, and dataset resources.
- Made public Feed text output LF-stable with generated `.gitattributes`, so
  checksums survive Windows `core.autocrlf` clones.
- Made CLI output tolerant of characters unsupported by legacy Windows console
  code pages without changing UTF-8 data on disk.
- Made migration verification distinguish local migrated Raw records from valid
  subscription-cache Raw records.
- Fixed generated paper-note boolean capability fields and avoided false
  Obsidian CLI Doctor failures on slower Windows application startup.

## 1.3.2 - 2026-07-18

- Added caption-backed PDF figure extraction with architecture-first semantic
  ranking, page-aware cropping, SHA256 manifests, and no fabricated diagrams.
- Added a bilingual visual guide to template bundle v3 while preserving
  original paper captions and the stable flat YAML schema.
- Added `paper visuals`, the backed-up `migrate visual-assets` workflow, and
  an Obsidian Control Center quick action for existing papers.
- Classified `layer_paths` correctly as Derived data so generated-paper
  refreshes never attempt to mutate immutable Raw records.

## 1.3.1 - 2026-07-18

- Added Chinese display labels for all 78 generated paper properties in
  Obsidian's native Properties panel when the application language is Chinese.
- Kept the stable English YAML keys unchanged for migrations, queries, Bases,
  public Feeds, and interoperability; focusing a property name reveals its
  underlying key.

## 1.3.0 - 2026-07-18

- Added Obsidian-native scheduled synchronization for all explicitly enabled
  Feed subscriptions.
- Added opt-in unattended Feed build/validate/privacy-scan/commit/push with a
  fixed origin and no-change suppression.
- Added real GitHub Release discovery, SHA256-verified staging, Workspace
  backup, runtime rollback, migration finalization, and confirmation-gated
  application of updates.
- Added a three-track automation orchestrator and complete source trust,
  disable, and removal controls to the bilingual Control Center.
- Fixed `update info` reporting a migration unconditionally and removed stale
  release-version pins from CI.

## 1.2.0 - 2026-07-18

- Redesigned the Obsidian Control Center around independent, user-oriented
  task entry points for collecting papers, analyzing imported papers, and
  configuring execution Agents; advanced publishing and maintenance tools are
  collapsed by default.
- Added a dedicated existing-paper analysis action and exposed Codex reasoning
  effort in both the CLI and Obsidian UI.
- Made the enforced Agent tool boundary visible: staged input only, Codex
  read-only sandbox, and Claude tools disabled.
- Added explicit Chinese/English UI tests and broader scheduler catch-up tests.
- PaperFlow Automation opens the Control Center automatically after Obsidian
  finishes loading the workspace, with an opt-out setting.
- Selected the MIT License for PaperFlow source code and CC BY 4.0 for this
  workspace's published Feed data.

## 1.1.0 - 2026-07-17

- Added the Obsidian-native PaperFlow Control Center for paper import,
  automation, AI profile configuration, diagnostics, migration previews,
  GitHub Feed subscriptions, synchronization, and controlled publishing.
- Added atomic non-interactive AI profile configuration for plugin clients.
- Added GitHub HTTPS URL validation, local Feed Git initialization/status,
  disabled Git hooks, and explicit confirmation for remote push.
- Excluded `.git` metadata from Feed checksums, privacy scans, diffs, and
  snapshots.
- Kept all external processes on a fixed command allowlist with `shell: false`;
  arbitrary shell commands are not supported.

## 1.0.0 - 2026-07-17

- separated the installable application from arbitrary per-user Workspaces;
- introduced independent Workspace, Raw, AI, User, Feed, template, and Form
  Flow version contracts;
- added reversible migrations, strict layered config, safe path templates,
  four-layer storage, AI provider profiles, Public Feed publishing/sync, and
  privacy scanning;
- productized Form Flow and Obsidian-only recurring automation;
- added wheel, sdist, Windows portable, checksums, CI workflows, installation
  scripts, examples, and first-user documentation;
- migrated the current Workspace without downloads, AI calls, or path moves.
## Unreleased

- 增加只读 Zotero 环境审计：识别真实安装、Profile、自定义 data directory 和 loopback Local API；不读取或修改 `zotero.sqlite`。
- 增加 `paperflow zotero detect/status/doctor` 与 Zotero 7 插件安全骨架。
- 增加 `entities-0002-display-labels` 迁移，统一生成实体的可读标题，同时保留 Topic/Method/Dataset 类型边界、别名和用户正文。
- 增加 Zotero Workspace 配置、loopback Core 服务、精确身份映射 dry-run 和脱敏 Zotero JSON fixture；停止后台服务前会校验 PID 命令行，避免误终止无关进程。
## Unreleased

- 将 Zotero 主工作流继续前移：Core 可使用显式 standalone `data-root`，不依赖 Obsidian Vault。
- 增加 `ArtifactPolicy`/`PermissionGuard`/`PublishScanner`，阻止系统写入覆盖用户笔记并在发布前扫描私有文件。
- Zotero 插件新增身份与附件校验快照回传；Core 校验后保存 mapping 和附件 SHA-256 状态，不直接触碰 `zotero.sqlite`。
- AI Markdown 支持 Zotero、Obsidian 或双目标投影，并保存 render state；费曼问题与用户答案分离。
