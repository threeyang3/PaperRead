from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.paths.templates import safe_component
from paperflow.text_quality import display_title, short_title, user_display_title


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def compose_record(
    root: Path,
    raw: dict[str, Any],
    *,
    analysis: dict[str, Any] | None = None,
    overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose Raw, AI, User and Derived layers for every render path."""
    uid = str(raw.get("paper_uid") or raw.get("metadata", {}).get("paper_uid") or "")
    metadata = dict(raw.get("metadata") or raw)
    paper_id = safe_component(
        str(metadata.get("paper_arxiv_id") or uid).replace(":", "_")
    )
    user_record = _yaml(root / ".paperflow/data/user" / f"{paper_id}.yaml")
    derived_record = _json(root / ".paperflow/data/derived" / f"{paper_id}.json")
    user = dict(user_record.get("user") or {})
    derived = dict(derived_record.get("derived") or {})
    record: dict[str, Any] = {**metadata, **(overlay or {})}
    if analysis:
        record.update(dict(analysis.get("analysis") or analysis))
    record.update(derived)
    record.update(user)
    record["paper_uid"] = uid or str(record.get("paper_uid") or "")
    record["paper_title_display"] = display_title(
        str(record.get("paper_title") or paper_id)
    )
    record["paper_short_title"] = short_title(
        str(record.get("paper_title") or paper_id)
    )
    override = user_display_title(record)
    record["paper_display_title"] = override or record["paper_title_display"]
    record["display_title"] = record["paper_display_title"]
    record["file_name"] = f"{safe_component(paper_id)}.md"
    return record
