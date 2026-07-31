from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PublicAnchor(ExtensibleModel):
    pdf_version: int = Field(ge=1)
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page: int = Field(ge=1)
    exact_quote: str = Field(default="", max_length=500)
    prefix: str = Field(default="", max_length=120)
    suffix: str = Field(default="", max_length=120)


class CommunityContribution(ExtensibleModel):
    type: Literal["paperflow-community-contribution"] = "paperflow-community-contribution"
    community_data_schema_version: int = 1
    contribution_id: str
    revision: int = Field(ge=1)
    supersedes: str = ""
    paper_uid: str
    creator: str = Field(pattern=r"^[A-Za-z0-9-]{1,39}$")
    kind: Literal[
        "highlight", "passage-comment", "question", "critique",
        "figure-comment", "section-comment", "paper-review", "rating", "reply",
    ]
    body: str = Field(default="", max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    rating: int | None = Field(default=None, ge=1, le=5)
    anchor: PublicAnchor | None = None
    license: str
    created_at: str
    content_sha256: str
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def revision_contract(self) -> "CommunityContribution":
        if self.revision > 1 and not self.supersedes:
            raise ValueError("revision > 1 requires supersedes")
        if self.kind == "rating" and self.rating is None:
            raise ValueError("rating contributions require a rating")
        return self


class CommunityProfile(ExtensibleModel):
    type: Literal["paperflow-community-profile"] = "paperflow-community-profile"
    community_data_schema_version: int = 1
    github: str = Field(pattern=r"^[A-Za-z0-9-]{1,39}$")
    display_name: str = ""
    bio: str = ""
    updated_at: str


class CommunityRetraction(ExtensibleModel):
    type: Literal["paperflow-community-retraction"] = "paperflow-community-retraction"
    community_data_schema_version: int = 1
    contribution_id: str
    creator: str
    retracted_revision: int = Field(ge=1)
    reason: str = Field(max_length=1000)
    created_at: str
