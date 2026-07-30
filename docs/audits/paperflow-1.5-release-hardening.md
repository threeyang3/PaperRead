# PaperFlow 1.5 release-hardening audit

- Applies to PaperFlow 1.5.x
- Workspace schema: 3
- Feed schema: 2

## Baseline

- Date: 2026-07-30 (Asia/Shanghai)
- Starting branch: `agent/paperflow-1.5`
- Starting commit: `d7763f60a280d4b3298f0c00b37525d2094eca7a`
- Working branch: `fix/paperflow-1.5-release-hardening`
- Pre-existing working-tree changes: documentation reorganization; preserved
- Python: 3.13.11 (`D:\miniconda3`)
- Node.js: 22.15.0
- Application: 1.5.0
- Obsidian plugin: 1.5.0
- Zotero plugin: 1.5.0
- Baseline pytest: 202 passed
- Baseline Node integration tests: 5 requested suites passed
- Baseline release build: passed
- Baseline release artifact label: `PaperFlow-portable-1.5.0.zip`

## Scope and status

| Area | Reproduction | Remediation | Verification |
| --- | --- | --- | --- |
| Feed canonical Raw and clean staging | Confirmed: recursive capture collision and stale managed files | Explicit canonical enumeration, validated staging, managed sync, persistent recovery journal and verified rollback | Feed suite: 36 passed |
| Public Raw allowlist | Confirmed: internal extensions could reach publication | Separate strict public models/schema; legacy unknown fields quarantined locally | Public projection/quarantine tests passed |
| Versioned PDF resolver | Confirmed: ChatGPT Web assumed legacy filename | Index/record/Derived/legacy resolver with path, version, header and SHA checks | Resolver tests passed |
| Zotero Core worker lifecycle | Confirmed: stop could discard a live worker reference | Durable jobs, recovery, idempotency, cancellation and honest stopping state | Core service: 12 passed; lifecycle tests passed |
| Obsidian child-process lifecycle | Confirmed: child handle, timeout and cancellation absent | Active child state, bounded timeout, cooperative/forced tree termination, redacted full logs | Scheduler and lifecycle Node suites passed |
| Windows offline installer | Confirmed: archive called Portable but depended on global Python | Renamed bundle, root installers, console-script launcher and explicit tool checks | Packaging: 10 passed; pip/pipx/uv real installs passed |
| Workspace timezone | Confirmed: `+08:00` validation and JS hard-code | Workspace Clock, offset-aware validation, Workspace-driven Feed/daily/scheduler | 7 timezone tests and scheduler suite passed |
| Streaming IO and caches | Partial implementation existed | Bounded streamed PDF write + fsync + structural validation; visual identity cache/staging; mapping index | Relevant tests passed |
| CI, Doctor, migration, documentation | CI lacked static/coverage/install gates; Doctor was Shanghai-specific and wrote a probe | Gradual Ruff/Mypy gates, 70% coverage baseline, critical module thresholds, dependency tracks, read-only diagnostics, ordered docs | Local quality/build/migration checks passed |

## Confirmed defects and regression evidence

- Old Feed behavior failed 10 of the initial 12 new hardening tests. Captures,
  disabled categories, duplicate identities, hash mismatches and public extension
  leakage now have direct regression coverage.
- Managed Feed updates now persist a destination-bound transaction journal and
  complete backup before changing the current tree. A simulated partial update
  is automatically rolled back and inventory-verified by the next build; unsafe
  journal paths fail closed without changing the Feed.
- The old PDF resolver test could not import a shared resolver and could not locate
  Workspace v3 `vN.pdf`; seven resolver scenarios now pass.
- Seven Core lifecycle tests failed against the old stop/recovery/idempotency
  behavior; the expanded Core and lifecycle suites now pass.
- The Obsidian lifecycle test initially failed because no active child handle
  existed. Tests now start real child processes and verify timeout, cancellation,
  unload cleanup, overlap refusal, exact Windows PID handling and bounded UI logs.
- The old release artifact was named `PaperFlow-portable-1.5.0.zip` but its launcher
  used system Python. The final artifact is
  `PaperFlow-Offline-Installer-1.5.0.zip`.

## Data compatibility

- Application version remains 1.5.0; Workspace schema remains 3; Feed schema
  remains 2. A new strict `public-raw-paper.schema.json` is distributable Feed
  schema, not a mutation of internal Raw/AI/User records.
- Existing immutable Raw/AI timestamps are not rewritten.
- Unknown legacy mixed-record fields remain in internal extensions and are copied
  to `.paperflow/data/quarantine/legacy-fields/` for review; quarantine is never
  published.
- No User fields or user-authored note sections are modified. No existing PDF is
  deleted. Visual assets and mapping indexes are Derived and rebuildable.
- Feed rebuild deletes only the enumerated PaperFlow-managed paths that disappear
  from the validated candidate; `.git`, README and other unmanaged files remain.

## Final local verification

- Python 3.13.11: 255 pytest tests passed; 3 pre-existing resource warnings;
  no failures or skips.
- Coverage: 70.11% overall. Critical thresholds passed: data store 90%+, Feed
  publisher 80%+, PDF resolver 70%+, privacy scanner 85%+, Workspace v3 80%+,
  Zotero Core 65%+.
- Node.js 22.15.0: all five requested integration scripts passed.
- Ruff lint and scoped format gate: passed.
- Mypy: no issues in 127 source files under the gradual strict-module policy.
- Dependency audit: no known vulnerabilities in `constraints/release.txt`.
- Version check: application, Obsidian integration and Zotero integration all
  report 1.5.0.
- Build: wheel, sdist, Offline Installer, Template Vault, Zotero XPI, schema and
  template archives produced.
- Packaging audit: 10 passed.
- Key suites: Feed 36, migration 6, packaging 10, Zotero Core service 12,
  Workspace 5 and visual assets 15 passed.
- Clean Windows smoke: direct wheel install, `--version`, `--help`,
  non-interactive init, Workspace info and Doctor executed in a path containing
  spaces and Chinese characters. Doctor returned 1 only for intentionally absent
  external Obsidian/Zotero tools; new structural diagnostics were OK.
- Final Offline Installer root script completed with `-Method pip` from a path
  containing spaces. Separate isolated pipx and uv tool installs both reported
  PaperFlow 1.5.0.
- GitHub-hosted checks passed on release-candidate commit `9fa4c5a`: Windows,
  macOS and Linux with Python 3.11, 3.12 and 3.13; locked and latest-compatible
  dependency tracks; Quality, Build, Feed validation and Migration workflows.

## Performance result

- PDF response bodies are streamed in 1 MiB chunks to a same-directory temporary
  file with incremental size/SHA checks; a full PDF is no longer accumulated in
  a Python bytearray. No reliable peak-memory benchmark was run.
- Repeated visual extraction skips PyMuPDF when PDF SHA, extractor version,
  settings and every asset SHA match. Missing assets or changed settings trigger
  a full staged rebuild; a failed rebuild preserves the previous directory.
- Zotero item lookup changes from an O(n) mapping directory scan per request to
  an O(1) index lookup after an O(n) explicit/recovery rebuild.
- Feed wall-clock before/after was not benchmarked; final checksums still hash
  current managed content.

## Remaining limitations

- An in-place Git working tree cannot atomically replace several top-level
  managed paths in one filesystem operation. A hard process or host termination
  can therefore leave a partial tree observable until the next Feed build runs;
  the persisted journal then restores and verifies the exact previous managed
  inventory before doing any new work. Publishers that require zero observation
  window should publish a versioned directory and switch a server-side pointer
  after validation.
- Ruff formatting is deliberately gradual and scoped to new release-hardening
  files. Historical modules retain formatting debt to avoid a large unrelated
  rewrite; lint still checks release-critical runtime-error rules.

## Release recommendation

**A. The candidate can enter PaperFlow 1.5 release-candidate validation.** All
local code, data, lifecycle, install and artifact gates are green, including
recoverable hard-interruption handling for Feed publication, and the hosted
Windows/macOS/Linux CI matrix is green. Stable promotion still requires review,
merge and explicit release approval; this audit does not create or move a tag.
