# Changelog

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
