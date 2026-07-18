from __future__ import annotations
from pathlib import Path
from typing import Protocol
from paperflow.models import Analysis, PaperMetadata


class AIAdapter(Protocol):
    provider: str
    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis: ...

