from __future__ import annotations
import json
from paperflow.config import Config
from .import_paper import import_paper


def analyze_uid(cfg: Config, uid: str, provider: str | None = None):
    path = cfg.root / ".paperflow/data/papers" / f"{uid.replace(':', '_')}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    value = record.get("paper_abs_url") or record.get("paper_pdf_url")
    return import_paper(cfg, value, force=True, run_ai=True, provider=provider)

