from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AnnotationKind = Literal[
    "highlight", "passage-comment", "question", "critique", "figure-comment",
    "section-comment", "paper-review", "rating",
]
Motivation = Literal[
    "highlighting", "commenting", "questioning", "assessing", "tagging", "replying",
]
ReanchorStatus = Literal[
    "exact-hash-match", "exact-selection-match", "exact-text-match",
    "quote-reanchored", "page-only", "manual-review", "orphaned",
]


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class FragmentSelector(ExtensibleModel):
    type: Literal["FragmentSelector"] = "FragmentSelector"
    page: int = Field(ge=1)
    rect: list[float] | None = None


class TextQuoteSelector(ExtensibleModel):
    type: Literal["TextQuoteSelector"] = "TextQuoteSelector"
    exact: str
    prefix: str = ""
    suffix: str = ""


class TextPositionSelector(ExtensibleModel):
    type: Literal["TextPositionSelector"] = "TextPositionSelector"
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class AnnotationAnchor(ExtensibleModel):
    pdf_version: int = Field(ge=1)
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pdf_path: str
    page: int = Field(ge=1)
    fragment_selector: FragmentSelector
    text_quote_selector: TextQuoteSelector | None = None
    text_position_selector: TextPositionSelector | None = None
    selected_text_sha256: str = ""

    @model_validator(mode="after")
    def page_consistent(self) -> "AnnotationAnchor":
        if self.fragment_selector.page != self.page:
            raise ValueError("fragment selector page must match anchor page")
        return self


class AnnotationRevision(ExtensibleModel):
    revision: int = Field(ge=1)
    anchor: AnnotationAnchor
    preferred: bool = True
    reanchor_method: str = "created"
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: ReanchorStatus = "exact-hash-match"
    created_at: str


class Annotation(ExtensibleModel):
    type: Literal["paperflow-user-annotation"] = "paperflow-user-annotation"
    schema_version: int = 1
    annotation_id: str
    paper_uid: str
    kind: AnnotationKind
    motivation: Motivation
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    revisions: list[AnnotationRevision]
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def one_preferred_revision(self) -> "Annotation":
        if len([item for item in self.revisions if item.preferred]) != 1:
            raise ValueError("exactly one annotation revision must be preferred")
        return self

    @property
    def preferred_revision(self) -> AnnotationRevision:
        return next(item for item in self.revisions if item.preferred)


class PaperReview(ExtensibleModel):
    type: Literal["paperflow-user-paper-review"] = "paperflow-user-paper-review"
    schema_version: int = 1
    review_id: str
    paper_uid: str
    rating: int | None = Field(default=None, ge=1, le=5)
    summary: str = ""
    strengths: str = ""
    weaknesses: str = ""
    questions: str = ""
    reproduction_notes: str = ""
    verdict: str = ""
    created_at: str
    updated_at: str
    extensions: dict[str, Any] = Field(default_factory=dict)
