# AI providers

PaperFlow supports `codex`, `claude`, `chatgpt-web`, and deterministic `mock` providers behind
one interface: availability, model listing, config validation, analysis, and
provenance.

Profiles independently select provider, model, timeout, reasoning effort,
fallback, Feed reuse, and reanalysis policy for triage, full analysis, fallback
analysis, and reanalysis. An empty model means the user's CLI default.

For Codex, PaperFlow passes a bounded `model_reasoning_effort` override using
the CLI `--config key=value` interface. Supported values are `low`, `medium`,
`high`, `xhigh`, and `max`; an empty value preserves the CLI default. Claude does not
use this Codex-specific setting.

PaperFlow probes `--version` and analysis help before use, filters extra
arguments through an allowlist, forces restricted/read-only operation, and
never opens, copies, or rewrites Codex/Claude credential files or global
configuration. Only staged metadata and selected paper text are given to an AI
process.

`chatgpt-web` is a separate, consent-gated browser Provider. It drives a
Vault-external dedicated Edge profile with Playwright, uploads only a staged
PDF copy, selects the strongest recognizable visible model, validates
`paper-analysis-v3`, and pauses for user takeover rather than guessing when
login, CAPTCHA, or the model menu is incompatible.

Tool access is a fixed safety contract rather than an arbitrary user setting:
Codex runs with `--sandbox read-only`, while Claude runs with `--tools ""`.

Claude receives a structured-output schema without the declarative Draft
`$schema` URI because Claude Code 2.1.206 rejects that metadata key. PaperFlow
does not weaken validation: the returned value is still checked against the
complete on-disk Draft 2020-12 schema before it can be persisted.

The real-provider acceptance test used the locally configured Xiaomi endpoint
and explicit `mimo-v2.5` model to import and analyze π0 (`2410.24164`), FAST
(`2501.09747`), and π0.5 (`2504.16054`). Every persisted analysis records
`provider=claude`, `model=mimo-v2.5`, prompt version, source hash, and profile.
