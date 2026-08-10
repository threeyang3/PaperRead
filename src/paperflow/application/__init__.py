"""Application-level entry points shared by PaperFlow user interfaces."""

from paperflow.application.paper_service import (
    AddPaperRequest,
    OperationResult,
    PaperApplicationService,
)

__all__ = ["AddPaperRequest", "OperationResult", "PaperApplicationService"]
