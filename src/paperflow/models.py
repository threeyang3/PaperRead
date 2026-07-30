from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

from paperflow.clock import parse_aware_datetime


class PaperMetadata(BaseModel):
    paper_uid: str
    paper_source: str = "arxiv"
    paper_arxiv_id: str = ""
    paper_arxiv_version: int = 1
    paper_doi: str = ""
    paper_title: str
    paper_authors: list[str] = Field(default_factory=list)
    paper_first_author: str = ""
    paper_year: int | None = None
    paper_submitted_date: date | None = None
    paper_updated_date: date | None = None
    paper_published_venue: str = ""
    paper_primary_category: str = ""
    paper_categories: list[str] = Field(default_factory=list)
    paper_abstract: str = ""
    paper_pdf_url: str = ""
    paper_abs_url: str = ""
    paper_project_url: str = ""
    paper_code_url: str = ""
    paper_dataset_url: str = ""


class Analysis(BaseModel):
    ai_analysis_status: Literal["pending", "complete", "failed", "skipped"] = "complete"
    ai_relevance_score: float = Field(ge=0, le=5)
    ai_relevance_reason: str
    ai_topic_primary: str
    ai_topics: list[str] = Field(default_factory=list)
    ai_method_family: list[str] = Field(default_factory=list)
    ai_task_types: list[str] = Field(default_factory=list)
    ai_robot_platforms: list[str] = Field(default_factory=list)
    ai_datasets: list[str] = Field(default_factory=list)
    ai_baselines: list[str] = Field(default_factory=list)
    ai_novelty_score: int = Field(ge=1, le=5)
    ai_novelty_confidence: float = Field(ge=0, le=1)
    ai_novelty_reason: str
    ai_completeness_score: int = Field(ge=1, le=5)
    ai_completeness_confidence: float = Field(ge=0, le=1)
    ai_completeness_reason: str
    ai_reproducibility_score: int = Field(ge=1, le=5)
    ai_reproducibility_confidence: float = Field(ge=0, le=1)
    ai_reproducibility_reason: str
    ai_overall_score: float = 0
    ai_overall_confidence: float = Field(ge=0, le=1)
    ai_recommendation: str
    ai_summary_short: str
    ai_difficulty: Literal["easy", "medium", "hard"] = "medium"
    ai_math_level: Literal["low", "medium", "high"] = "medium"
    ai_code_level: Literal["low", "medium", "high"] = "medium"
    ai_estimated_reading_priority: int = Field(ge=0, le=5)
    sections: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def compute_overall(self) -> "Analysis":
        self.ai_overall_score = round(0.35 * self.ai_novelty_score + 0.30 * self.ai_completeness_score + 0.35 * self.ai_reproducibility_score, 2)
        return self


class ImportRequest(BaseModel):
    type: Literal["paper-import-request"] = "paper-import-request"
    schema_version: int = 1
    request_id: str
    paper_input: str
    topic_hint: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    add_to_reading_queue: bool = True
    favorite: bool = False
    user_tags: list[str] = Field(default_factory=list)
    run_ai: bool = True
    ui_locale: str = ""
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    created_at: str
    processed_at: str | None = None
    result_paper_uid: str | None = None
    result_note: str | None = None
    error: str | None = None

    @field_validator("paper_input", mode="before")
    @classmethod
    def normalize_yaml_paper_input(cls, value: Any) -> Any:
        """Preserve bare arXiv IDs that YAML may parse as numeric scalars."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return value

    @field_validator("created_at", "processed_at", mode="before")
    @classmethod
    def normalize_yaml_timestamp(cls, value: Any) -> Any:
        """Normalize timestamps parsed by YAML before strict string validation."""
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @field_validator("created_at", "processed_at")
    @classmethod
    def timezone_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parse_aware_datetime(value)
        return value
