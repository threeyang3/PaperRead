# PaperFlow 1.5 post-audit hardening

Status: Release Candidate changes under verification; not a stable Release.

This audit keeps Workspace schema 3 and Feed schema 2 unchanged. It does not
migrate or delete user notes, PDFs, annotations, reviews, or existing Feed
records.

## Confirmed and fixed

- Remote Feed and Community identifiers previously reached path joins through
  ad-hoc `replace(":", "_")` handling. Managed storage now uses one NFKC-aware,
  fail-closed component encoder plus resolved-root containment and symlink
  checks. Dry-run validates the same boundary as a real write.
- The generated Offline Installer contained a `paperflow.cmd` that could find
  and invoke itself. The bundle now contains no same-name wrapper and verifies
  the installed console script. Windows smoke testing extracts to a path with
  spaces and Chinese characters, installs, runs `--version`/`--help`, and
  verifies uninstall leaves a Vault marker untouched.
- Vault-backed Core Community writes now use `data_root(root)` and therefore
  land below `.paperflow/data/community/outbox`; standalone Core continues to
  use `data/community/outbox`. Existing records in a historical wrong root are
  not deleted or silently merged.
- Running cancellation now persists `cancellation-requested` with a timestamp.
  A non-interruptible operation that finishes after the request is recorded as
  `completed-after-cancel-request`, not `cancelled`. Cooperative tokens are
  checked around AI, render, Feed-source, PDF-chunk, and atomic-write boundaries.
- Automation logs recursively redact structured sensitive keys and handle
  header, environment-variable, assignment, quoted and Bearer forms. Binary
  output is summarized and each task log is capped at 1 MiB; UI tails remain
  capped at 16,000 characters.
- Explicit PDF version resolution no longer accepts a `vN.pdf` for another
  version or an unversioned legacy file without the current-PDF compatibility
  policy. Duplicate index versions and ambiguous fallback candidates fail.
- Core PDF serving returns a validated file descriptor and streams chunks;
  upload validation reads only the header and hashes files incrementally.
- Core persisted timestamps and prioritized pipeline records now use UTC.
  Workspace-facing schedules and date boundaries continue to use the configured
  IANA timezone, including DST.

## Engineering gates

CI and tag-triggered Release call the same reusable quality workflow. It covers
Python 3.11-3.13 on Windows, Ubuntu, and macOS; locked and latest-compatible
dependencies; Python and Node tests; Ruff, Mypy, coverage, pip-audit, Feed and
migration contracts; release build; packaging; wheel and Offline Installer
smoke tests. Release creation is draft-first and protected by the
`production-release` GitHub Environment.

The full transitive dependency graphs are stored in
`requirements/release-py311.txt`, `release-py312.txt`, and
`release-py313.txt`, including package hashes. Regenerate them only with
`scripts/update_locks.ps1`, review the diff, run both dependency lanes, and run
pip-audit before merging.

## Known limits

- `iso_beijing()` remains as a deprecated compatibility API for older modules;
  no historical immutable timestamp is rewritten. Remaining call sites should
  migrate incrementally when their owning module changes.
- The Offline Installer is an install bundle, not a portable Python runtime.
- A GitHub Environment reviewer must be configured in repository settings;
  workflow YAML can name the environment but cannot create its protection rule.
- This audit does not create a tag, publish a Release, upload PyPI, or push a
  public Feed.
