from __future__ import annotations
import uuid
from paperflow.config import Config
from .daily_brief import write_daily_brief
from .discover import discover
from .import_paper import import_paper
from .inbox import process_inbox
from paperflow.logging_config import configure_logging
from paperflow.database import Database
from paperflow.utils import iso_beijing
from paperflow.retention import cleanup_ai_logs
from paperflow.sync_safety import assert_no_sync_conflicts


def run_daily(cfg: Config, discover_enabled: bool = True) -> dict:
    assert_no_sync_conflicts(cfg.root)
    run_id = str(uuid.uuid4())
    logger = configure_logging(cfg.root, "daily")
    cleanup_ai_logs(cfg.root, int(cfg.section("retention").get("keep_ai_logs_days", 30)))
    db = Database(cfg.root / ".paperflow/state/paperflow.db")
    started_at = iso_beijing()
    db.record_discovery_run(run_id, "running", {}, started_at)
    logger.info("Daily run started", extra={"run_id": run_id, "stage": "daily"})
    stats = {"imported": 0, "existing": 0, "updated": 0, "failed": 0, "manual": 0, "ai_filtered": 0, "manual_review": 0}
    papers, errors = [], []
    first = process_inbox(cfg)
    stats["manual"] += first["processed"]
    stats["failed"] += first["failed"]
    try:
        candidates, discovery_stats = discover(cfg) if discover_enabled else ([], {"candidates": 0, "rule_filtered": 0, "ai_filtered": 0})
        stats.update({"candidates": discovery_stats["candidates"], "rule_filtered": discovery_stats["rule_filtered"], "ai_filtered": discovery_stats["ai_filtered"]})
        for paper in candidates:
            try:
                result = import_paper(cfg, paper.paper_abs_url, import_method="daily")
                if result["status"] == "skipped": stats["existing"] += 1
                elif result["status"] == "updated": stats["updated"] += 1
                else: stats["imported"] += 1
                record = result.get("record", {})
                papers.append({"note": result["note_path"].removesuffix(".md"), "title": record.get("paper_title", paper.paper_title), "score": record.get("ai_overall_score", 0)})
            except Exception as exc:
                stats["failed"] += 1
                errors.append(f"{paper.paper_uid}: {exc}")
    except Exception as exc:
        stats["failed"] += 1
        errors.append(f"discovery: {exc}")
    last = process_inbox(cfg)
    stats["manual"] += last["processed"]
    stats["failed"] += last["failed"]
    brief = write_daily_brief(cfg, run_id, stats, papers, errors)
    db.record_discovery_run(run_id, "completed" if not errors else "completed_with_errors", stats, started_at, iso_beijing())
    db.close()
    logger.info("Daily run finished", extra={"run_id": run_id, "stage": "daily"})
    return {"run_id": run_id, "stats": stats, "brief": str(brief), "errors": errors}
