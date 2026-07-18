from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from paperflow.config import Config
from paperflow.utils import atomic_write, now_beijing


def write_daily_brief(cfg: Config, run_id: str, stats: dict, papers: list[dict], errors: list[str]) -> Path:
    now = now_beijing()
    env = Environment(loader=FileSystemLoader(cfg.root / "90 System/Templates"), autoescape=False)
    defaults = {"candidates": 0, "rule_filtered": 0, "ai_filtered": 0, "imported": 0, "existing": 0, "updated": 0, "manual": 0, "failed": 0, "manual_review": 0}
    defaults.update(stats)
    template = "Daily Paper Brief Template.en.md" if cfg.ui_locale.locale == "en" else "Daily Paper Brief Template.md"
    content = env.get_template(template).render(date=now.date().isoformat(), generated_at=now.strftime("%Y-%m-%d %H:%M"), run_id=run_id, stats=defaults, papers=papers, errors=errors)
    path = cfg.path("daily_brief_folder") / f"{now.date().isoformat()}.md"
    atomic_write(path, content + "\n")
    return path
