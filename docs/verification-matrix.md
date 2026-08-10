# PaperFlow verification matrix

## 2026-08-10 core Golden Workflow

This verification targets the local working tree on branch
`fix/core-golden-workflow`. It does not claim a published release and does not
modify a real user Vault. Exact final suite counts are recorded after the full
gate run; the dedicated Golden Workflow currently passes 9/9 scenarios.

| Core acceptance item | Verdict | Automated evidence |
| --- | --- | --- |
| Fresh Workspace includes canonical taxonomy | PASS | Golden tests initialize an empty temporary Vault and import without copying project files manually. |
| `paper add` creates Raw, PDF, Paper Hub, and User Note | PASS | `test_import_without_unmatched_topics_completes`. |
| Explicit `--vault` works outside Vault cwd | PASS | All Golden CLI calls run from a separate temporary cwd. |
| No-AI mode omits AI JSON and AI Markdown | PASS | `test_import_without_unmatched_topics_completes`. |
| Mock-AI mode creates immutable AI JSON and projection | PASS | `test_golden_workflow_preserves_user_owned_artifacts`. |
| Known topic creates no Manual Review | PASS | No-unmatched Golden scenario asserts no Review artifact and false manual-review state. |
| Unknown explicit topic creates a pending Manual Review | PASS | `test_import_with_unmatched_topics_creates_manual_review`. |
| Form Flow text is written directly to independent User Note | PASS | Full workflow asserts User Note content and Paper Hub link. |
| Existing paper accepts a new Form Flow note before system deduplication | PASS | `test_duplicate_form_flow_request_preserves_new_user_note`. |
| Same Form Flow request retry is idempotent | PASS | `test_form_flow_request_retry_does_not_duplicate_user_note`. |
| Different requests append independently | PASS | Duplicate-paper scenario processes second and third request IDs. |
| Repeating `review create` is byte-identical and keeps review ID | PASS | Full workflow hashes the file before and after the second command. |
| Analyze preserves Review | PASS | Full workflow compares the Review hash after each write-capable operation. |
| Analyze, refresh, render, and duplicate add preserve User Note | PASS | Full workflow compares the User Note hash after every operation. |
| Annotation survives analyze, refresh, render, and duplicate add | PASS | Full workflow compares the Annotation hash after every operation. |
| Duplicate add reuses the paper and user artifacts | PASS | Full workflow re-adds the same source and verifies stable paths/hashes. |
| Render preserves business Manual Review state | PASS | Unknown-topic scenario renders again and retains the state. |
| AI failure leaves PDF/text and retryable checkpoint | PASS | `test_ai_failure_is_inspectable_and_retry_reuses_local_artifacts`. |
| Form Flow note exists before AI-failure retry | PASS | `test_form_flow_note_survives_ai_failure_and_analyze_retry`. |
| Form Flow import intent survives AI-failure retry | PASS | `test_form_flow_retry_preserves_import_intent` asserts priority 5, favorite, queued state, both tags, known topic hint, user note, a post-failure sidecar edit, local PDF/text reuse, and completed AI/job states. |
| Failed AI render creates no AI Markdown | PASS | `test_render_failed_analysis_does_not_create_ai_markdown`. |
| Analyze retry reuses local PDF/text | PASS | Failure/retry test asserts one download and one extraction total. |
| `paper inspect` reports all core artifacts and latest job | PASS | No-AI and failure/retry scenarios inspect structured output. |
| Getting Started commands use explicit Vault and are executable outside it | PASS | CLI structure is exercised by Golden tests; documentation mirrors those commands. |

Final gate results on Windows, uv 0.12.0 and Python 3.12.13:

- `uv run --extra quality pytest --cov=paperflow`: **355 passed, 1 skipped**,
  **73.99%** total coverage (70% gate and critical coverage gate passed);
- Golden Workflow: **9 passed**;
- Ruff check/format and mypy (`134` source files): **PASS**;
- scheduler, Automation lifecycle, Zotero Core client, Zotero public API, and
  Zotero UI Node integration suites: **PASS**;
- version consistency (`1.5.1`), local release build, and packaging tests:
  **PASS**;
- no tag, release, Feed publication, or real-Vault mutation was performed.

## 2026-07-28 historical environment acceptance

The following table is retained as dated evidence for the earlier real-Vault,
release-artifact, and isolated-Zotero acceptance. It is not a claim about the
current working tree's test count.

| Capability | Verdict | Evidence |
| --- | --- | --- |
| Chinese UI selection | Pass | `paperflow language` resolved `zh-CN` from Obsidian. Unit tests cover `zh`, `zh-CN`, explicit English override, and both translation branches. Original paper titles, abstracts, quotations, citations, and extracted text remain unchanged. |
| Obsidian-native scheduling | Pass | The plugin lifecycle test covers startup, Vault events, Inbox debounce, five-minute polling, daily due/catch-up rules, and disabled catch-up. Doctor reports `daily=08:00`, `inbox=5m`, and Windows scheduler independence. |
| Offline daily workflow | Pass | `paperflow daily --offline` completed with no errors and generated `40 Daily Briefs/2026-07-18.md` without arXiv requests or AI calls. |
| Agent provider and model settings | Pass | The Control Center and `ai set-profile` atomically configure profile, Codex/Claude/ChatGPT Web/Mock provider, model, timeout, fallback, reuse, and reanalysis policy. Provider probes found Claude Code 2.1.206, Playwright/Edge, and deterministic Mock. Prior real Claude runs through the configured Xiaomi endpoint persisted π0, FAST, and π0.5 analyses with explicit `mimo-v2.5` provenance. |
| Codex reasoning effort | Pass | `low`, `medium`, `high`, `xhigh`, and `max` are validated and passed to Codex as a bounded `model_reasoning_effort` config override. |
| ChatGPT Web analysis | Safe handoff verified; successful upload pending | The dedicated Edge/Playwright channel launched with explicit PDF consent and Vault-external browser state. It safely paused before upload because the strongest visible model could not be identified, recorded `user-action-required`, and did not silently downgrade or publish an analysis. A logged-in account/menu compatible with the configured strength policy is still needed for the successful-upload acceptance case. |
| Agent tool settings | Intentional fixed boundary | Arbitrary tools are not user-configurable. Codex receives staged inputs in a read-only sandbox; Claude starts with an empty tool set. Neither may write the Vault or execute paper, LaTeX, repository, or installer scripts. The Control Center explains this boundary. |
| User-focused Control Center | Pass | The lifecycle DOM contains one task shelf with seven current goals: collect, discover, library, reading, annotation, reproduction, and daily review. Analysis and Agent configuration are separate input cards. The real ArxivLearn Control Center loaded after the fixed wheel install. |
| PDF visual annotation loop | Pass | PDF++ 0.40.31 is installed and enabled. The adapter feature-detects `pdf-plus:copy-link-to-selection`, validates the clipboard link against the current versioned PDF, and otherwise opens an explicit page/text fallback. The π0.5 annotation `ann-3a5a...` validated, opened a yellow PDF++ highlight, and is listed in `60 Annotations/arxiv_2504.16054/index.md`; the old year index SHA256 stayed unchanged. |
| Zotero/Core/Obsidian π0.5 loop | Pass | In an isolated Zotero 9.0.6 Profile, `arxiv:2504.16054` created/reused the PaperFlow Collection and item `8XL74URF`, imported PDF `JV46V7IT`, verified SHA-256 `6a1029fd...34b64c`, attached AI Markdown `I7N92IGU`, refreshed mapping, and rendered `20 AI Analyses/2025/2504.16054.analysis.md`. Reader annotation `HQQVWNGR` mirrored highlight text, user comment, page, color, and position. The main Profile was not used for writes. |
| Zotero loopback authentication | Pass | A valid short-lived session establishes a local device pairing. After Core restart the plugin exchanges the pairing for a fresh session without asking the user to copy another token; protected routes still reject missing/invalid authentication. Pairing/session secrets remain local and are excluded from Git, Feed, and release artifacts. |
| Control Center i18n | Pass | Plugin integration tests render and assert both Chinese and English UI branches. The running Obsidian DOM reported language `zh`. |
| Caption-backed paper figures | Pass | 29 representative embodied-AI/tactile/VLA PDFs retain 166 checksummed Derived PNGs. New selection is adaptive by quality, semantic coverage, and duplication; 12 is only a safety ceiling. All manifests pass schema, Vault-bound path, source-PDF SHA256, and PNG SHA256 validation. |
| Visual-note preservation | Pass | Template bundle v6 prefers original arXiv HTML images, records their provenance, falls back to caption-backed PDF crops, and groups architecture/method, experiment/result, and task/hardware figures. Existing Derived embeds remain rebuildable. |
| Community GitHub round trip | Pass | Two explicit π0.5 annotation/comment snapshots passed privacy and checksum validation, were pushed to `threeyang3/ArXiv-data` at `c23cfe4`, cloned back through Feed v2, cached read-only, and rendered into one local Community note with `user_records_modified: 0`. |
| Published AI isolation | Pass | Feed AI reads only `.paperflow/data/ai`; a regression test edits rendered paper Markdown and confirms the published AI JSON remains byte-identical. Community publication likewise reads only immutable opt-in outbox snapshots. |
| Visual Base browsing | Pass | `Paper Library.base` opens with 29 image-backed Cards in “视觉浏览” plus an independent “触觉论文” Cards view; sortable table views remain available. Card labels display 第一作者、年份、主要主题、综合评分、阅读状态 and 优先级 under the Chinese Obsidian locale. Obsidian 1.12.7 reports both views as `cards`, returns all 29 paths, and captures no runtime or console errors. |
| Representative sample AI analysis | Pass | All 29 curated samples report `ai_analysis_status=complete`: 26 with Codex `gpt-5.4`, and π0/FAST/π0.5 with Claude Code `mimo-v2.5` provenance. Original titles, captions, figures, and paper text remain in the source language while the explanatory analysis renders in Chinese. |
| Local-first reanalysis | Pass | Existing-paper analysis now reuses local metadata, extracted text, PDF, and visual manifests. Real retries completed Habitat, DIGIT, RMA, ReSkin, Octo, and OpenVLA without arXiv access; Raw snapshots remained immutable and new AI/Derived records were persisted. |
| Repository separation | Pass | `PaperRead` contains the MIT-licensed application; `ArXiv-data` is an independent public CC BY 4.0 Feed repository. Software releases and data refreshes no longer share a default branch or update cadence. |
| Public Feed round trip | Pass | The independent `ArXiv-data` GitHub Feed contains 29 Raw + 29 AI records and passed schema, privacy, provenance, checksum, and Windows clone validation. Remote sync created 58 read-only cache records with 0 conflicts, 0 User writes, and no remote code execution; a second sync created 0 and reused all 58. |
| Cross-platform Feed checksums | Pass | Generated Feed text is LF-stable and includes `.gitattributes`. A regression test clones with Windows `core.autocrlf=true` and validates every checksum; the same fix was pushed and verified through a real GitHub clone. |
| Workspace v3 migration and rollback | Pass | Regression coverage includes stale `layer_paths.derived` PDF paths and visual assets. ArxivLearn `migrate verify-workspace-v3` reports `ok=true`, zero missing files, hash mismatches, note-link mismatches, Derived path mismatches, Base errors, and zero modified user-note sections. |
| Community contribution integrity | Pass | Publisher and subscriber share one canonical JSON `content_sha256` rule. Subscription ingestion rejects a revision whose body or any other hashed payload field was altered, before writing the read-only cache. Privacy/copyright gates remain fail-closed. |
| Path and Workspace validation | Pass | `paths validate`, `workspace validate`, `health`, migration verification, paper validation, and audit passed in ArxivLearn. Health found no mojibake, missing visual embeds, broken assets, pending reanalysis, or sync conflicts. |
| Release packaging | Pass | The final build creates wheel, sdist, `PaperFlow-Offline-Installer-1.5.0.zip`, `PaperFlow-Template-Vault-1.5.0.zip`, schema/template ZIPs, checksums, and migration notes. The Offline Installer contains no Python runtime and does not claim self-contained portability. Positive-whitelist audits exclude papers, PDFs, user notes, runtime state, caches, logs, databases, browser state, and arbitrary `.obsidian` state. |
| Clean installation | Pass | The fixed 1.5.0 wheel and sdist build successfully; wheel SHA256 is `e745fadac0160ab2e5c2def7ab1c8a791adff92f42c6859155ee54d36f15b8eb`. The wheel was force-reinstalled into ArxivLearn's `.paperflow/.venv`, and Workspace repair installed integration v10. |
| Automated regression | Pass | All 202 tests in the authoritative repository `tests/` tree and all Zotero JavaScript integration suites pass. Coverage includes four unique reading leaves, PDF focus, PDF++ selection success/fallback, canonical annotation indexing, Zotero pairing/session refresh, PDF staging/import, AI Markdown attachment, direct Zotero 9 annotation properties, manual annotation resync, Workspace v3 repair, rollback, Community tamper rejection, Feed privacy, lifecycle, and scheduling. |
| Doctor and product audit | Pass | ArxivLearn `doctor --no-network` and `audit` passed. Doctor reports zh-CN, PDF++ 0.40.31, Form Flow, PaperFlow Automation, Obsidian-native scheduling, no sync conflicts, and Windows scheduler independence. Audit passed all listed product, migration, privacy, and packaging gates. |
| Runtime plugin health | Pass | After installing integration v10, Obsidian reload reported no plugin errors and no captured console errors. The real command opened versioned PDF, canonical Annotation, Review, and Community leaves and focused the PDF. A final screenshot was captured at `.paperflow/runtime/pdf-annotation-index-v10.png`. |

## Portability assessment

PaperFlow's Python application is distributed as a wheel and sdist, while the
current Offline Installer Bundle and Obsidian runtime bootstrap target Windows
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

1. Install the 1.5.0 wheel or use the PaperFlow Offline Installer Bundle.
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
