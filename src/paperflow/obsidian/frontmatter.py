from __future__ import annotations
import io
import re
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML
from paperflow.utils import atomic_write

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def read_note(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    yaml = YAML(typ="safe")
    return dict(yaml.load(match.group(1)) or {}), text[match.end():]


def dump_frontmatter(data: dict[str, Any]) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    stream = io.StringIO()
    yaml.dump(data, stream)
    return "---\n" + stream.getvalue() + "---\n"


def write_note(path: Path, data: dict[str, Any], body: str) -> None:
    atomic_write(path, dump_frontmatter(data) + "\n" + body.lstrip())


def preserve_user_fields(new: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    merged = dict(new)
    for key, value in old.items():
        if key.startswith("user_"):
            merged[key] = value
    old_tags = list(old.get("tags", []))
    merged["tags"] = list(dict.fromkeys(list(new.get("tags", [])) + old_tags))
    return merged

