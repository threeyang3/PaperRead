from __future__ import annotations
import json
from typing import Any
from paperflow.config import Config
from paperflow.models import PaperMetadata
from .import_paper import import_paper


def analyze_uid(
    cfg: Config,
    uid: str,
    provider: str | None = None,
    cancellation_token: Any | None = None,
):
    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    path = cfg.root / ".paperflow/data/papers" / f"{uid.replace(':', '_')}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    metadata = PaperMetadata.model_validate(
        {
            name: record[name]
            for name in PaperMetadata.model_fields
            if name in record
        }
    )
    value = record.get("paper_abs_url") or record.get("paper_pdf_url")
    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    return import_paper(
        cfg,
        value,
        force=True,
        run_ai=True,
        provider=provider,
        metadata_override=metadata,
        reuse_local_assets=True,
    )
