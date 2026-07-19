from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from paperflow.data.records import AnalysisIdentity, split_legacy_record
from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json
from paperflow.workspace import dump_yaml
from paperflow.utils import iso_beijing
from paperflow.text_quality import validate_text_quality


def _write_immutable_json(path: Path, value: dict[str, Any]) -> bool:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if path.exists():
        existing = json.dumps(
            json.loads(path.read_text(encoding="utf-8")),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if existing != serialized:
            raise RuntimeError(f"Immutable PaperFlow record already exists: {path}")
        return False
    atomic_json(path, value)
    return True


def analysis_record_path(
    root: Path,
    *,
    paper_id: str,
    source_version: int,
    identity: AnalysisIdentity,
) -> Path:
    return (
        root
        / ".paperflow/data/ai"
        / identity.profile
        / safe_component(paper_id.replace(":", "_"))
        / f"v{source_version}"
        / f"{identity.analysis_id}.json"
    )


def load_reusable_analysis(
    root: Path,
    *,
    paper_id: str,
    source_version: int,
    identity: AnalysisIdentity,
) -> dict[str, Any] | None:
    path = analysis_record_path(
        root,
        paper_id=paper_id,
        source_version=source_version,
        identity=identity,
    )
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if (
        record.get("analysis_id") != identity.analysis_id
        or record.get("identity") != identity.model_dump(mode="json")
        or record.get("status") != "complete"
    ):
        return None
    return record


def persist_layer_records(
    root: Path,
    record: dict[str, Any],
    *,
    preserve_existing_raw: bool = False,
) -> dict[str, str]:
    """Persist all four layers while keeping Raw and AI records immutable."""
    raw, ai, user, derived = split_legacy_record(record)
    paper_id = safe_component(
        str(record.get("paper_arxiv_id") or record["paper_uid"]).replace(":", "_")
    )
    version = int(record.get("paper_arxiv_version") or 1)
    raw_path = (
        root / ".paperflow/data/raw" / raw.source / paper_id / f"v{version}.json"
    )
    user_path = root / ".paperflow/data/user" / f"{paper_id}.yaml"
    derived_path = root / ".paperflow/data/derived" / f"{paper_id}.json"
    raw_value = raw.model_dump(mode="json")
    validate_text_quality(raw_value, label="raw")
    if ai is not None:
        validate_text_quality(ai.model_dump(mode="json"), label="ai")
    selected_raw_path = raw_path
    if not raw_path.exists():
        _write_immutable_json(raw_path, raw_value)
    else:
        existing = json.loads(raw_path.read_text(encoding="utf-8"))
        if existing != raw_value:
            if not preserve_existing_raw:
                raise RuntimeError(
                    f"Immutable PaperFlow record already exists: {raw_path}"
                )
            serialized = json.dumps(
                raw_value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest = hashlib.sha256(serialized).hexdigest()[:12]
            stamp = iso_beijing().replace(":", "-")
            selected_raw_path = (
                raw_path.with_suffix("")
                / "captures"
                / f"{stamp}-{digest}.json"
            )
            _write_immutable_json(selected_raw_path, raw_value)
        elif not preserve_existing_raw:
            _write_immutable_json(raw_path, raw_value)
    derived.derived["system_selected_raw_capture"] = (
        selected_raw_path.relative_to(root).as_posix()
    )
    dump_yaml(user_path, user.model_dump(mode="json"))
    atomic_json(derived_path, derived.model_dump(mode="json"))
    result = {
        "raw": selected_raw_path.relative_to(root).as_posix(),
        "user": user_path.relative_to(root).as_posix(),
        "derived": derived_path.relative_to(root).as_posix(),
    }
    if ai is not None:
        ai_path = analysis_record_path(
            root,
            paper_id=paper_id,
            source_version=version,
            identity=ai.identity,
        )
        _write_immutable_json(ai_path, ai.model_dump(mode="json"))
        result["ai"] = ai_path.relative_to(root).as_posix()
    return result
