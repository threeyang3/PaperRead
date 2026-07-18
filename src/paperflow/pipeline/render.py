from __future__ import annotations
import json
from paperflow.config import Config
from paperflow.obsidian.note_renderer import render_paper


def render_uid(cfg: Config, uid: str):
    path = cfg.root / ".paperflow/data/papers" / f"{uid.replace(':', '_')}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    note = cfg.root / record["note_path"]
    return render_paper(cfg.root, record, note, record.get("system_import_method", "manual"), cfg.ui_locale.locale)
