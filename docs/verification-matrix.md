# PaperFlow 1.3.2 verification matrix

Verified on 2026-07-18 against the real
`E:/ObsidianVaults/ArxivLearn` Workspace.

| Capability | Verdict | Evidence |
| --- | --- | --- |
| Chinese UI selection | Pass | `paperflow language` resolved `zh-CN` from Obsidian. Unit tests cover `zh`, `zh-CN`, explicit English override, and both translation branches. Original paper titles, abstracts, quotations, citations, and extracted text remain unchanged. |
| Obsidian-native scheduling | Pass | The plugin lifecycle test covers startup, Vault events, Inbox debounce, five-minute polling, daily due/catch-up rules, and disabled catch-up. Doctor reports `daily=08:00`, `inbox=5m`, and Windows scheduler independence. |
| Offline daily workflow | Pass | `paperflow daily --offline` completed with no errors and generated `40 Daily Briefs/2026-07-18.md` without arXiv requests or AI calls. |
| Agent provider and model settings | Pass | The Control Center and `ai set-profile` atomically configure profile, Codex/Claude/Mock provider, model, timeout, fallback, reuse, and reanalysis policy. Provider probes found Codex, Claude Code, and deterministic Mock. |
| Codex reasoning effort | Pass | `low`, `medium`, `high`, and `xhigh` are validated and passed to Codex as a bounded `model_reasoning_effort` config override. The current triage/full-analysis profiles use `low`/`high`. |
| Agent tool settings | Intentional fixed boundary | Arbitrary tools are not user-configurable. Codex receives staged inputs in a read-only sandbox; Claude starts with an empty tool set. Neither may write the Vault or execute paper, LaTeX, repository, or installer scripts. The Control Center explains this boundary. |
| User-focused Control Center | Pass | The running Obsidian DOM contains one task shelf with six current goals: collect, discover, library, reading, reproduction, and daily review. Analysis and Agent configuration are separate input cards. Inbox, daily brief, import requests, and runtime status remain one-click actions. The structure is extensible and does not imply a linear workflow. |
| Control Center i18n | Pass | Plugin integration tests render and assert both Chinese and English UI branches. The running Obsidian DOM reported language `zh`. |
| Caption-backed paper figures | Pass | Four real local PDFs produced 12 Derived PNGs with architecture-first ranking. Diffusion Policy, TacForeSight, the NIST cable-insertion pipeline, and RoboTTT architecture crops were visually inspected. All four manifests pass schema, Vault-bound path, source-PDF SHA256, and PNG SHA256 validation. |
| Visual-note preservation | Pass | Template bundle v3 embeds source captions and Vault-relative PNG links in a bilingual visual guide. Regression tests prove records without `extraction` still render and `USER_NOTES_START/END` content survives refresh. |
| Migration and data preservation | Pass | `migrate status`, `plan`, and `verify` passed. The migration is reversible, preserves legacy records, validates SQLite and links, and keeps raw, AI, user, and derived layers separate. |
| Path and Workspace validation | Pass | `paths validate`, `workspace validate`, Doctor, and audit all passed. Path templates enforce allowlists and traversal/root checks. |
| Release packaging | Pass | The final build creates wheel, sdist, Windows x64 portable ZIP, schema ZIP, template ZIP, checksums, and migration notes for 1.3.2. Packaging tests verify required resources and exclude current Vault/user data. |
| Clean installation | Pass | The final 1.3.2 wheel and all declared dependencies install into a new isolated virtual environment. The version probe, update-manager import, and embedded Obsidian plugin resource probe are covered by the release workflow. |
| Automated regression | Pass | 174 pytest tests plus Obsidian lifecycle and scheduler Node integration suites passed. |
| Runtime plugin health | Pass | The managed runtime and installed plugin report 1.3.2 / integration 7. Obsidian plugin reload reports no captured errors and an empty captured error-level console. The live application displays the Chinese Control Center and paper notes at template version 3. |

## Portability assessment

PaperFlow's Python application is distributed as a wheel and sdist, while the
current turnkey portable bundle and Obsidian runtime bootstrap target Windows
x64. Moving the Workspace to another Windows machine is supported through the
documented installer, versioned resources, migration checks, and
`workspace export-user-data` / `workspace import-user-data`.

The data model and Python package are designed to be portable, but macOS and
Linux are not yet turnkey targets: the Obsidian plugin currently defaults to a
Windows virtual-environment path and no platform-specific portable archives are
built for those systems. Reproduction on any machine also requires Obsidian
Desktop and the official Form Flow integration; Codex or Claude Code is
optional when Mock or non-AI workflows are used.

## Reproduction sequence

1. Install the 1.3.2 wheel or use the Windows x64 portable archive.
2. Initialize or import a PaperFlow Workspace and open it in Obsidian Desktop.
3. Install/enable the versioned Form Flow and PaperFlow Automation resources.
4. Run `paperflow doctor`, `paperflow migrate verify`, `paperflow paths
   validate`, and `paperflow workspace validate`.
5. Run the default pytest suite and the two Node integration suites when
   developing from source.

No Windows Task Scheduler registration or user `PATH` mutation is required for
normal automation. Scheduled work runs only while Obsidian Desktop is open and
catches up after the next launch when configured.
