# Changelog

## Unreleased

- Added a unified Chinese guide for users and maintainers, covering setup,
  Obsidian-native operation, repository ownership, testing, packaging,
  publishing, upgrades, and recovery.
- Separated the MIT-licensed PaperRead application from the CC BY 4.0
  `ArXiv-data` public subscription Feed.
- Verified real Claude Code 2.1.206 analysis through Xiaomi `mimo-v2.5` on the
  π0, FAST, and π0.5 paper series.
- Made Claude structured output compatible with its JSON Schema parser while
  retaining full Draft 2020-12 validation after inference.
- Expanded caption-backed paper visuals from three to six images by default.
- Added balanced architecture, result, and task/hardware figure selection,
  including Chinese and Extended Data figure captions.
- Added template bundle v4 with grouped visuals, folded original captions, and
  direct links to the source PDF page.
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
