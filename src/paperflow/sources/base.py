from __future__ import annotations
from typing import Protocol
from paperflow.models import PaperMetadata


class Source(Protocol):
    def fetch(self, value: str) -> PaperMetadata: ...

