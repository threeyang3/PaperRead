from __future__ import annotations
import shutil
from pathlib import Path
from paperflow.config import Config
from paperflow.database import Database
from paperflow.obsidian.form_flow import parse_request, request_path_is_safe
from paperflow.obsidian.frontmatter import read_note, write_note
from paperflow.utils import iso_beijing
from paperflow.logging_config import configure_logging
from paperflow.i18n import normalize_locale
from paperflow.utils import atomic_json
from .import_paper import import_paper
from paperflow.sync_safety import assert_no_sync_conflicts


def _resolve(cfg: Config, request: str | None) -> list[Path]:
    folder = cfg.path("request_folder")
    if request is None:
        return sorted(folder.glob("*.md"))
    candidates = [folder / request, folder / f"{request}.md"]
    for path in candidates:
        if path.exists() and request_path_is_safe(cfg.root, path):
            return [path]
    raise FileNotFoundError(f"Request not found in safe inbox: {request}")


def process_inbox(cfg: Config, request: str | None = None) -> dict[str, int]:
    assert_no_sync_conflicts(cfg.root)
    stats = {"processed": 0, "failed": 0, "skipped": 0}
    logger = configure_logging(cfg.root, "inbox")
    db = Database(cfg.root / ".paperflow/state/paperflow.db")
    try:
        for path in _resolve(cfg, request):
            if not request_path_is_safe(cfg.root, path):
                raise ValueError(f"Unsafe request path: {path}")
            try:
                item, note = parse_request(path)
                if item.ui_locale:
                    atomic_json(
                        cfg.root / ".paperflow/state/obsidian-locale.json",
                        {
                            "locale": normalize_locale(item.ui_locale),
                            "source": "form-flow-request",
                            "updated_at": iso_beijing(),
                        },
                    )
                if item.status not in {"pending", "failed"}:
                    stats["skipped"] += 1
                    continue
                frontmatter, body = read_note(path)
                frontmatter["status"] = "processing"
                write_note(path, frontmatter, body)
                db.record_request(item.request_id, str(path), "processing")
                result = import_paper(cfg, item.paper_input, priority=item.priority, topic=item.topic_hint, run_ai=item.run_ai, favorite=item.favorite, queued=item.add_to_reading_queue, user_tags=item.user_tags, user_note=note, import_method="form-flow")
                frontmatter["status"] = "completed"
                frontmatter["processed_at"] = iso_beijing()
                frontmatter["result_paper_uid"] = result["paper_uid"]
                frontmatter["result_note"] = f"[[{result['note_path'].removesuffix('.md')}]]"
                frontmatter["error"] = ""
                destination = cfg.path("processed_request_folder") / path.name
                write_note(path, frontmatter, body)
                shutil.move(path, destination)
                db.record_request(item.request_id, str(destination), "completed", result["paper_uid"])
                stats["processed"] += 1
                logger.info("Manual request completed", extra={"request_id": item.request_id, "paper_uid": result["paper_uid"], "stage": "inbox"})
            except Exception as exc:
                frontmatter, body = read_note(path)
                frontmatter["status"] = "failed"
                frontmatter["processed_at"] = iso_beijing()
                frontmatter["error"] = str(exc)
                write_note(path, frontmatter, body)
                destination = cfg.path("failed_folder") / path.name
                shutil.move(path, destination)
                request_id = str(frontmatter.get("request_id", path.stem))
                db.record_request(request_id, str(destination), "failed", error=str(exc))
                db.add_failed(request_id, {"request": request_id}, str(exc))
                stats["failed"] += 1
                logger.error(str(exc), extra={"request_id": request_id, "stage": "inbox", "error_type": type(exc).__name__})
        return stats
    finally:
        db.close()
