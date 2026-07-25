"""Small, deterministic AI Raw runner for a Zotero-only Core root.

The Vault pipeline remains the full provider pipeline.  A standalone Core must
still be useful without importing Obsidian, however, so it has a local
provider boundary and an append-only AI Raw/current-pointer store.  The
default provider is intentionally ``mock``: users may change the policy only
through the Core config, and unsupported providers fail explicitly instead of
silently falling back.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ruamel.yaml import YAML

from paperflow.ai.mock_adapter import MockAdapter
from paperflow.data.records import AIAnalysisRecord, AnalysisIdentity
from paperflow.models import PaperMetadata
from paperflow.paths.templates import safe_component
from paperflow.security.artifacts import PermissionGuard
from paperflow.text_quality import validate_text_quality
from paperflow.utils import atomic_json, iso_beijing
from paperflow.zotero.store import data_root, runtime_root


PROMPT_VERSION = "paper-analysis-v3"


def _paper_id(paper_uid: str) -> str:
    value = str(paper_uid or "").strip()
    if not value or "\x00" in value:
        raise ValueError("invalid paper_uid")
    return safe_component(value.replace(":", "_").replace("/", "_"))


def _paper_path(root: Path, paper_uid: str) -> Path:
    directory = data_root(root) / "papers"
    canonical = directory / f"{safe_component(paper_uid)}.json"
    legacy = directory / f"{_paper_id(paper_uid)}.json"
    return canonical if canonical.is_file() else legacy


def _config(root: Path) -> dict[str, Any]:
    path = root / "config.yaml"
    if not path.is_file():
        return {}
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _analysis_root(root: Path, profile: str, paper_uid: str, version: int) -> Path:
    return (
        data_root(root)
        / "ai"
        / safe_component(profile)
        / _paper_id(paper_uid)
        / f"v{max(1, int(version))}"
    )


def _load_pointer(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    record_path = value.get("analysis_path")
    if not isinstance(record_path, str) or not record_path:
        return None
    candidate = (root / record_path).resolve()
    try:
        candidate.relative_to(data_root(root).resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    try:
        record = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def load_current_analysis(root: Path, paper_uid: str) -> dict[str, Any] | None:
    """Read the newest valid standalone AI Raw record, never user Markdown."""

    root = root.resolve()
    base = data_root(root) / "ai"
    paper_id = _paper_id(paper_uid)
    pointers = sorted(base.glob(f"*/{paper_id}/v*/current.json"))
    for pointer in reversed(pointers):
        record = _load_pointer(pointer, root)
        if record and record.get("paper_uid") == paper_uid:
            return record
    candidates = sorted(base.glob(f"*/{paper_id}/v/*.json"), key=lambda path: path.stat().st_mtime)
    for candidate in reversed(candidates):
        if candidate.name == "current.json":
            continue
        try:
            record = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("paper_uid") == paper_uid:
            return record
    return None


def _text_for_analysis(root: Path, record: dict[str, Any]) -> str:
    """Use staged local PDF text when available, without exposing source paths."""

    paper_id = str(record.get("paper_arxiv_id") or "").strip()
    paper_uid = safe_component(str(record.get("paper_uid") or "").strip().replace(":", "_"))
    candidates: list[Path] = []
    explicit = record.get("paper_pdf_path") or record.get("pdf_path")
    if explicit:
        candidate = Path(str(explicit)).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        candidates.append(candidate)
    if paper_id:
        documents = root / "documents/zotero"
        if documents.is_dir():
            if paper_id:
                candidates.extend(documents.rglob(f"{paper_id}.pdf"))
            if paper_uid:
                candidates.extend(documents.rglob(f"{paper_uid}.pdf"))
    for pdf in candidates:
        if not pdf.is_file():
            continue
        try:
            import fitz

            with fitz.open(pdf) as document:
                pages = [
                    f"\n\n--- PAGE {index + 1} ---\n{page.get_text('text')}"
                    for index, page in enumerate(document)
                ]
            text = "".join(pages).strip()
            if text:
                return text
        except Exception:
            # A missing/unsupported PDF must not prevent metadata-only analysis.
            break

    abstract = str(record.get("paper_abstract") or "").strip()
    return "\n\n".join(value for value in (str(record.get("paper_title") or ""), abstract) if value)


def _provider_config(policy: dict[str, Any], provider: str) -> dict[str, Any]:
    configured = policy.get("providers") or {}
    value = configured.get(provider) if isinstance(configured, dict) else {}
    if not isinstance(value, dict):
        value = {}
    # Permit a provider-specific block directly under analysis for compact configs.
    direct = policy.get(provider)
    if isinstance(direct, dict):
        merged = dict(value)
        merged.update(direct)
        value = merged
    return value


def _make_standalone_adapter(root: Path, policy: dict[str, Any], provider: str, model: str):
    from paperflow.ai.chatgpt_web_adapter import ChatGPTWebAdapter
    from paperflow.ai.claude_adapter import ClaudeAdapter
    from paperflow.ai.codex_adapter import CodexAdapter

    allowed = {"mock", "claude", "codex", "chatgpt-web"}
    if provider not in allowed:
        raise ValueError(f"unsupported standalone provider: {provider}")
    if provider == "mock":
        return MockAdapter()
    config = _provider_config(policy, provider)
    timeout = int(config.get("timeout_seconds") or policy.get("timeout_seconds") or 1800)
    extra_args = config.get("extra_args") or []
    if not isinstance(extra_args, list) or not all(isinstance(item, str) for item in extra_args):
        raise ValueError(f"analysis.providers.{provider}.extra_args must be a list of strings")
    if provider == "claude":
        return ClaudeAdapter(
            root,
            timeout=timeout,
            model=model,
            executable=str(config.get("executable") or "claude"),
            extra_args=extra_args,
        )
    if provider == "codex":
        return CodexAdapter(
            root,
            timeout=timeout,
            model=model,
            executable=str(config.get("executable") or "codex"),
            profile=str(config.get("profile") or ""),
            reasoning_effort=str(config.get("reasoning_effort") or ""),
            extra_args=extra_args,
        )
    preference = config.get("model_preference") or []
    if not isinstance(preference, list) or not all(isinstance(item, str) for item in preference):
        raise ValueError("analysis.providers.chatgpt-web.model_preference must be a list of strings")
    return ChatGPTWebAdapter(
        root,
        timeout=timeout,
        browser_executable=str(config.get("browser_executable") or ""),
        browser_profile_dir=str(config.get("browser_profile_dir") or ""),
        base_url=str(config.get("base_url") or "https://chatgpt.com/"),
        allow_pdf_upload=bool(config.get("allow_pdf_upload", False)),
        model_preference=preference or None,
    )


def analyze_standalone(root: Path, paper_uid: str, *, force: bool = False) -> dict[str, Any]:
    """Run the configured standalone provider and write one immutable AI Raw revision."""

    root = root.resolve()
    runtime_root(root).mkdir(parents=True, exist_ok=True)
    source_path = _paper_path(root, paper_uid)
    if not source_path.is_file():
        raise FileNotFoundError(f"paper record not found: {paper_uid}")
    record = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("paper record must be a JSON object")
    metadata = PaperMetadata.model_validate({key: record[key] for key in PaperMetadata.model_fields if key in record})
    policy = _config(root).get("analysis") or {}
    provider = str(policy.get("provider") or "mock").strip().lower()
    profile = str(policy.get("profile") or "full_analysis").strip() or "full_analysis"
    model = str(policy.get("model") or "deterministic-v1").strip() or "deterministic-v1"
    adapter = _make_standalone_adapter(root, policy, provider, model)
    staged_text = _text_for_analysis(root, record)
    source_hash = hashlib.sha256(
        (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            + staged_text
        ).encode("utf-8")
    ).hexdigest()
    identity = AnalysisIdentity(
        provider=provider,
        model=model,
        profile=profile,
        prompt_version=PROMPT_VERSION,
        source_content_hash=source_hash,
    )
    target_root = _analysis_root(root, profile, paper_uid, int(record.get("paper_arxiv_version") or 1))
    target = target_root / f"{identity.analysis_id}.json"
    pointer = target_root / "current.json"
    if target.is_file() and not force:
        return {
            "status": "reused",
            "paper_uid": paper_uid,
            "provider": provider,
            "model": model,
            "analysis_id": identity.analysis_id,
            "path": target.relative_to(root).as_posix(),
            "current": pointer.relative_to(root).as_posix(),
            "artifact_permission": "AI_VERSIONED",
        }
    with TemporaryDirectory(prefix=f"paperflow-{_paper_id(paper_uid)}-", dir=runtime_root(root)) as temporary:
        staged = Path(temporary) / "paper.txt"
        staged.write_text(staged_text, encoding="utf-8", newline="\n")
        analysis = adapter.analyze(metadata, staged).model_dump(mode="json")
    validate_text_quality(analysis, label="standalone-ai")
    now = iso_beijing()
    value = AIAnalysisRecord(
        paper_uid=paper_uid,
        analysis_id=identity.analysis_id,
        identity=identity,
        analyzed_at=now,
        created_at=now,
        publisher="",
        status="complete",
        analysis=analysis,
    ).model_dump(mode="json")
    guard = PermissionGuard(root)
    guard.authorize(target, "AI_VERSIONED")
    guard.authorize(pointer, "AI_VERSIONED")
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing != value:
            raise RuntimeError(f"immutable AI Raw record already exists: {target}")
    else:
        atomic_json(target, value)
    atomic_json(pointer, {
        "schema_version": 1,
        "paper_uid": paper_uid,
        "analysis_id": identity.analysis_id,
        "analysis_path": target.relative_to(root).as_posix(),
        "content_sha256": hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "artifact_permission": "SYSTEM_MANAGED",
        "updated_at": now,
    })
    return {
        "status": "written",
        "paper_uid": paper_uid,
        "provider": provider,
        "model": model,
        "analysis_id": identity.analysis_id,
        "path": target.relative_to(root).as_posix(),
        "current": pointer.relative_to(root).as_posix(),
        "artifact_permission": "AI_VERSIONED",
    }


__all__ = ["PROMPT_VERSION", "analyze_standalone", "load_current_analysis"]
