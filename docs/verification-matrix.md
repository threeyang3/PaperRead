# PaperFlow 1.3.2 + Unreleased verification matrix

Verified on 2026-07-19 against the real
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
| Caption-backed paper figures | Pass | 26 representative embodied-AI/tactile PDFs produced 148 Derived PNGs (3–6 per paper) with category-balanced, architecture-first ranking. All 26 manifests pass schema, Vault-bound path, source-PDF SHA256, and PNG SHA256 validation. |
| Visual-note preservation | Pass | Template bundle v4 groups architecture/method, experiment/result, and task/hardware figures; source captions fold by default and every image links to its PDF page. Regression tests prove records without `extraction` still render and `USER_NOTES_START/END` content survives refresh. |
| Visual Base browsing | Pass | `Paper Library.base` opens with 26 image-backed Cards in “视觉浏览” plus an independent “触觉论文” Cards view; sortable table views remain available. Card labels display 第一作者、年份、主要主题、综合评分、阅读状态 and 优先级 under the Chinese Obsidian locale. Obsidian 1.12.7 reports both views as `cards`, returns all 26 paths, and captures no runtime or console errors. |
| Representative sample AI analysis | Pass | All 26 curated samples report `ai_analysis_status=complete` with Codex `gpt-5.4` provenance. Original titles, captions, figures, and paper text remain in the source language while the explanatory analysis renders in Chinese. |
| Local-first reanalysis | Pass | Existing-paper analysis now reuses local metadata, extracted text, PDF, and visual manifests. Real retries completed Habitat, DIGIT, RMA, ReSkin, Octo, and OpenVLA without arXiv access; Raw snapshots remained immutable and new AI/Derived records were persisted. |
| Public Feed round trip | Pass | A GitHub Feed containing 26 Raw + 26 AI records passed schema, privacy, provenance, and checksum validation. Remote sync created 52 read-only cache records with 0 conflicts, 0 User writes, and no remote code execution; a second sync created 0 and reused all 52. |
| Cross-platform Feed checksums | Pass | Generated Feed text is LF-stable and includes `.gitattributes`. A regression test clones with Windows `core.autocrlf=true` and validates every checksum; the same fix was pushed and verified through a real GitHub clone. |
| Migration and data preservation | Pass | `migrate status`, `plan`, and `verify` passed with 26 local migrated Raw, 26 subscription-cache Raw, 26 User, 26 Derived, and 52 AI records. The migration is reversible, preserves legacy records, validates SQLite and links, and keeps raw, AI, user, derived, and subscription-cache layers separate. |
| Path and Workspace validation | Pass | `paths validate`, `workspace validate`, Doctor, and audit all passed. Doctor recognizes the live Obsidian 1.12.7 CLI on slower Windows startup. Path templates enforce allowlists and traversal/root checks. |
| Release packaging | Pass | The final build creates wheel, sdist, Windows x64 portable ZIP, schema ZIP, template ZIP, checksums, and migration notes for 1.3.2. Packaging tests verify required resources and exclude current Vault/user data. |
| Clean installation | Pass | The final 1.3.2 wheel and all declared dependencies install into a new isolated virtual environment. The version probe, update-manager import, and embedded Obsidian plugin resource probe are covered by the release workflow. |
| Automated regression | Pass | 185 pytest tests passed, including local reanalysis, immutable Raw preservation, subscription-aware migration verification, Obsidian Doctor startup tolerance, resource-link rejection, visual Bases, Feed privacy, and Windows `core.autocrlf` clone coverage. |
| Runtime plugin health | Pass | The managed runtime and installed plugin report 1.3.2 / integration 7. Obsidian reports no captured errors. The live application displays the Chinese Control Center and paper notes at template version 4; an Obsidian screenshot confirmed grouped images and collapsed captions render correctly. |

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
