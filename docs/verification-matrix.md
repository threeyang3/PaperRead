# PaperFlow 1.5.0 verification matrix

Source and release-artifact verification completed on 2026-07-21 in the
`PaperRead` repository. A real `ArxivLearn` v3 apply then copied and rendered
32/32 records, but verification correctly rejected all 32 notes because the
original 1.5.0 migration left legacy PDF paths in the Derived layer. The source
fix and regression tests below are complete; that Vault must install the fixed
wheel and run schema-3 repair/verify before Doctor and audit are considered
complete.

| Capability | Verdict | Evidence |
| --- | --- | --- |
| Chinese UI selection | Pass | `paperflow language` resolved `zh-CN` from Obsidian. Unit tests cover `zh`, `zh-CN`, explicit English override, and both translation branches. Original paper titles, abstracts, quotations, citations, and extracted text remain unchanged. |
| Obsidian-native scheduling | Pass | The plugin lifecycle test covers startup, Vault events, Inbox debounce, five-minute polling, daily due/catch-up rules, and disabled catch-up. Doctor reports `daily=08:00`, `inbox=5m`, and Windows scheduler independence. |
| Offline daily workflow | Pass | `paperflow daily --offline` completed with no errors and generated `40 Daily Briefs/2026-07-18.md` without arXiv requests or AI calls. |
| Agent provider and model settings | Pass | The Control Center and `ai set-profile` atomically configure profile, Codex/Claude/ChatGPT Web/Mock provider, model, timeout, fallback, reuse, and reanalysis policy. Provider probes found Claude Code 2.1.206, Playwright/Edge, and deterministic Mock. Prior real Claude runs through the configured Xiaomi endpoint persisted π0, FAST, and π0.5 analyses with explicit `mimo-v2.5` provenance. |
| Codex reasoning effort | Pass | `low`, `medium`, `high`, `xhigh`, and `max` are validated and passed to Codex as a bounded `model_reasoning_effort` config override. |
| ChatGPT Web analysis | Safe handoff verified; successful upload pending | The dedicated Edge/Playwright channel launched with explicit PDF consent and Vault-external browser state. It safely paused before upload because the strongest visible model could not be identified, recorded `user-action-required`, and did not silently downgrade or publish an analysis. A logged-in account/menu compatible with the configured strength policy is still needed for the successful-upload acceptance case. |
| Agent tool settings | Intentional fixed boundary | Arbitrary tools are not user-configurable. Codex receives staged inputs in a read-only sandbox; Claude starts with an empty tool set. Neither may write the Vault or execute paper, LaTeX, repository, or installer scripts. The Control Center explains this boundary. |
| User-focused Control Center | Pass | The running Obsidian DOM contains one task shelf with six current goals: collect, discover, library, reading, reproduction, and daily review. Analysis and Agent configuration are separate input cards. Inbox, daily brief, import requests, and runtime status remain one-click actions. The structure is extensible and does not imply a linear workflow. |
| Control Center i18n | Pass | Plugin integration tests render and assert both Chinese and English UI branches. The running Obsidian DOM reported language `zh`. |
| Caption-backed paper figures | Pass | 29 representative embodied-AI/tactile/VLA PDFs retain 166 checksummed Derived PNGs. New selection is adaptive by quality, semantic coverage, and duplication; 12 is only a safety ceiling. All manifests pass schema, Vault-bound path, source-PDF SHA256, and PNG SHA256 validation. |
| Visual-note preservation | Pass | Template bundle v5 groups architecture/method, experiment/result, and task/hardware figures. The formal v2 migration composed all four data layers and rerendered 29/29 notes with 0 failures; π0.5 retained all six embeds and no broken paths. |
| Visual Base browsing | Pass | `Paper Library.base` opens with 29 image-backed Cards in “视觉浏览” plus an independent “触觉论文” Cards view; sortable table views remain available. Card labels display 第一作者、年份、主要主题、综合评分、阅读状态 and 优先级 under the Chinese Obsidian locale. Obsidian 1.12.7 reports both views as `cards`, returns all 29 paths, and captures no runtime or console errors. |
| Representative sample AI analysis | Pass | All 29 curated samples report `ai_analysis_status=complete`: 26 with Codex `gpt-5.4`, and π0/FAST/π0.5 with Claude Code `mimo-v2.5` provenance. Original titles, captions, figures, and paper text remain in the source language while the explanatory analysis renders in Chinese. |
| Local-first reanalysis | Pass | Existing-paper analysis now reuses local metadata, extracted text, PDF, and visual manifests. Real retries completed Habitat, DIGIT, RMA, ReSkin, Octo, and OpenVLA without arXiv access; Raw snapshots remained immutable and new AI/Derived records were persisted. |
| Repository separation | Pass | `PaperRead` contains the MIT-licensed application; `ArXiv-data` is an independent public CC BY 4.0 Feed repository. Software releases and data refreshes no longer share a default branch or update cadence. |
| Public Feed round trip | Pass | The independent `ArXiv-data` GitHub Feed contains 29 Raw + 29 AI records and passed schema, privacy, provenance, checksum, and Windows clone validation. Remote sync created 58 read-only cache records with 0 conflicts, 0 User writes, and no remote code execution; a second sync created 0 and reused all 58. |
| Cross-platform Feed checksums | Pass | Generated Feed text is LF-stable and includes `.gitattributes`. A regression test clones with Windows `core.autocrlf=true` and validates every checksum; the same fix was pushed and verified through a real GitHub clone. |
| Workspace v3 migration and rollback | Source repair pass; real Vault repair pending | Regression coverage now includes a realistic `layer_paths.derived` record with a stale `paper_pdf_path`, extraction PDF source path, visual asset and page link. Apply atomically repairs Derived before compose/render, preserves visual PNG paths and all User content, and verifies aggregate/Derived/note links. Re-running apply on schema 3 uses the existing formal backup and reports `repaired`; verification failure reports `verification-failed` with a non-zero CLI exit. The real 32-paper Vault still needs this repair run. |
| Community contribution integrity | Pass | Publisher and subscriber share one canonical JSON `content_sha256` rule. Subscription ingestion rejects a revision whose body or any other hashed payload field was altered, before writing the read-only cache. Privacy/copyright gates remain fail-closed. |
| Path and Workspace validation | Pass | `paths validate`, `workspace validate`, `health`, migration verification, paper validation, and audit passed. Doctor's static/data checks passed; its two live-Obsidian checks remain in the runtime handoff item below. |
| Release packaging | Pass | The final build creates wheel, sdist, curated `PaperFlow-portable-1.5.0.zip`, `PaperFlow-Template-Vault-1.5.0.zip`, schema/template ZIPs, checksums, and migration notes. Positive-whitelist audits and four packaging tests exclude papers, PDFs, user notes, runtime state, caches, logs, databases, browser state, and arbitrary `.obsidian` state. |
| Clean installation | Source package pass; real Vault reinstall pending | The fixed 1.5.0 wheel and sdist build successfully and expose one `_version.py` source. Reinstalling that wheel and its bundled plugin resources into ArxivLearn remains a Vault-project step. |
| Automated regression | Pass | All 111 tests in the authoritative repository `tests/` tree and both Node plugin suites (2/2) pass. The lifecycle suite loads the real plugin-directory `main.js` from an unrelated cwd while an Electron-like loader rejects every relative module request; startup succeeds with zero such requests. Coverage also includes Derived-path Workspace v3 repair, safe rollback, Community tamper rejection, immutable Raw captures, Feed privacy, lifecycle, and scheduling. |
| Doctor and product audit | Source checks pass; real Vault pending | Doctor and audit were run against an isolated initialized Workspace. Application 1.5.0, the ten independent version contracts, config, paths, SQLite, schemas, templates, Automation plugin and archive/privacy checks passed. Empty-workspace data counts, Form Flow, first Inbox runtime and ChatGPT Web availability remain expected environment checks; they require the real ArxivLearn Vault and interactive desktop environment. |
| Runtime plugin health | Source repair pass; real Vault reload pending | Real Vault reload exposed Electron resolving the former `require("./reading-workspace")` outside the plugin directory and rejecting it with `MODULE_NOT_FOUND`. The entry is now self-contained and the Electron-like lifecycle regression passes; the fixed wheel must reinstall plugin resources in ArxivLearn before live reload, console, DOM, screenshot, and first Inbox checks. |

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

1. Install the 1.5.0 wheel or use the PaperFlow portable archive.
2. Initialize or import a PaperFlow Workspace and open it in Obsidian Desktop.
3. Install/enable the versioned Form Flow and PaperFlow Automation resources.
4. Run `paperflow migrate workspace-v3 --dry-run`, review and apply it, then run
   `paperflow migrate verify-workspace-v3`, `paperflow doctor`, `paperflow
   audit`, `paperflow paths validate`, and `paperflow workspace validate`.
5. Run the default pytest suite and the two Node integration suites when
   developing from source.

No Windows Task Scheduler registration or user `PATH` mutation is required for
normal automation. Scheduled work runs only while Obsidian Desktop is open and
catches up after the next launch when configured.
