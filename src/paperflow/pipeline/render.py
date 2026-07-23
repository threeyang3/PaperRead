from __future__ import annotations
import json
from paperflow.config import Config
from paperflow.obsidian.note_renderer import render_paper
from paperflow.data.compose import compose_record


def render_uid(cfg: Config, uid: str):
    path = cfg.root / ".paperflow/data/papers" / f"{uid.replace(':', '_')}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record = compose_record(
        cfg.root,
        {"paper_uid": record["paper_uid"], "metadata": record},
        overlay=record,
    )
    note = cfg.root / record["note_path"]
    return render_paper(cfg.root, record, note, record.get("system_import_method", "manual"), cfg.ui_locale.locale)
