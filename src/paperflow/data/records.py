from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from paperflow.versioning import VERSIONS


class VersionedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    paper_uid: str
    extensions: dict[str, Any] = Field(default_factory=dict)


class RawPaperRecord(VersionedRecord):
    schema_version: int = VERSIONS.raw_data_schema_version
    source: str
    source_id: str
    source_version: int = 1
    metadata: dict[str, Any]
    source_license: str = ""
    source_response: dict[str, Any] = Field(default_factory=dict)
    pdf_sha256: str = ""
    extracted_text_sha256: str = ""


class AnalysisIdentity(BaseModel):
    provider: str
    model: str
    profile: str
    prompt_version: str
    analysis_schema_version: int = VERSIONS.ai_analysis_schema_version
    source_content_hash: str

    @property
    def analysis_id(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]


class AIAnalysisRecord(VersionedRecord):
    schema_version: int = VERSIONS.ai_analysis_schema_version
    analysis_id: str
    identity: AnalysisIdentity
    analyzed_at: str = ""
    created_at: str = ""
    publisher: str = ""
    status: str
    analysis: dict[str, Any]


class UserPaperRecord(VersionedRecord):
    schema_version: int = VERSIONS.user_data_schema_version
    user: dict[str, Any]


class DerivedRecord(VersionedRecord):
    schema_version: int = 1
    derived: dict[str, Any]


RAW_EXCLUDED = {
    "paper_pdf_path",
    "paper_has_code",
    "paper_has_project_page",
    "paper_has_dataset",
}
AI_SPECIAL = {"sections", "version_change_note"}
DERIVED_KEYS = {"extraction", "note_path", "json_path", "layer_paths"}


def split_legacy_record(
    record: dict[str, Any],
) -> tuple[RawPaperRecord, AIAnalysisRecord | None, UserPaperRecord, DerivedRecord]:
    """Split a mixed legacy record without dropping unrecognised properties."""
    uid = str(record["paper_uid"])
    raw_values = {
        key: value
        for key, value in record.items()
        if key.startswith("paper_") and key not in RAW_EXCLUDED
    }
    ai_values = {
        key: value
        for key, value in record.items()
        if key.startswith("ai_") or key in AI_SPECIAL
    }
    user_values = {
        key: value for key, value in record.items() if key.startswith("user_")
    }
    derived_values = {
        key: value
        for key, value in record.items()
        if key.startswith("system_")
        or key in DERIVED_KEYS
        or key in RAW_EXCLUDED
    }
    known = (
        {"paper_uid"}
        | set(raw_values)
        | set(ai_values)
        | set(user_values)
        | set(derived_values)
        | {"source_api_response"}
    )
    extensions = {
        key: value for key, value in record.items() if key not in known
    }

    raw = RawPaperRecord(
        paper_uid=uid,
        source=str(record.get("paper_source") or "arxiv"),
        source_id=str(record.get("paper_arxiv_id") or uid),
        source_version=int(record.get("paper_arxiv_version") or 1),
        metadata=raw_values,
        source_license=str(record.get("paper_license") or ""),
        source_response=dict(record.get("source_api_response") or {}),
        pdf_sha256=str(record.get("system_content_hash") or ""),
        extracted_text_sha256=str(
            (record.get("extraction") or {}).get("text_sha256") or ""
        ),
        extensions=extensions,
    )
    identity = AnalysisIdentity(
        provider=str(record.get("ai_analysis_provider") or "legacy"),
        model=str(record.get("ai_analysis_model") or "unknown"),
        profile=str(record.get("ai_analysis_profile") or "full_analysis"),
        prompt_version=str(record.get("ai_analysis_prompt_version") or "legacy"),
        analysis_schema_version=VERSIONS.ai_analysis_schema_version,
        source_content_hash=str(record.get("system_content_hash") or ""),
    )
    ai = None
    if str(record.get("ai_analysis_status") or "").lower() == "complete":
        ai = AIAnalysisRecord(
            paper_uid=uid,
            analysis_id=identity.analysis_id,
        identity=identity,
        analyzed_at=str(record.get("ai_analyzed_at") or ""),
        created_at=str(record.get("ai_analyzed_at") or ""),
        publisher=str(record.get("ai_analysis_publisher") or ""),
        status="complete",
            analysis=ai_values,
        )
    user = UserPaperRecord(paper_uid=uid, user=user_values)
    derived = DerivedRecord(paper_uid=uid, derived=derived_values)
    return raw, ai, user, derived
