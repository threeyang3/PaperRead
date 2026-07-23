from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.workspace import dump_yaml


def load_preferences(vault: Path) -> dict[str, Any]:
    path = vault / ".paperflow/data/user/community-preferences.yaml"
    if not path.exists():
        return {"blocked_creators": [], "hidden_contributions": []}
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return {
        "blocked_creators": list(value.get("blocked_creators", [])),
        "hidden_contributions": list(value.get("hidden_contributions", [])),
    }


def save_preferences(vault: Path, value: dict[str, Any]) -> Path:
    path = vault / ".paperflow/data/user/community-preferences.yaml"
    dump_yaml(path, value)
    return path
