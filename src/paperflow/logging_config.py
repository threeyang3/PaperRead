from __future__ import annotations
import json
import logging
from pathlib import Path
from .utils import iso_beijing, now_beijing


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": iso_beijing(), "level": record.levelname,
            "run_id": getattr(record, "run_id", ""), "request_id": getattr(record, "request_id", ""),
            "paper_uid": getattr(record, "paper_uid", ""), "stage": getattr(record, "stage", ""),
            "message": record.getMessage(), "error_type": getattr(record, "error_type", ""),
        }, ensure_ascii=False)


def configure_logging(root: Path, kind: str = "paperflow") -> logging.Logger:
    log_dir = root / ".paperflow/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"paperflow.{kind}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = JsonFormatter()
        names = ["paperflow.log"]
        if kind in {"daily", "inbox"}:
            names.append(f"{kind}-{now_beijing().date().isoformat()}.log")
        for name in names:
            handler = logging.FileHandler(log_dir / name, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
    return logger
