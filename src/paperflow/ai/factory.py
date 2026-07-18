from __future__ import annotations
from pathlib import Path
from .claude_adapter import ClaudeAdapter
from .codex_adapter import CodexAdapter
from .mock_adapter import MockAdapter


def make_adapter(provider: str, root: Path, timeout: int = 1800, model: str | None = None):
    if provider == "mock":
        return MockAdapter()
    if provider == "codex":
        return CodexAdapter(root, timeout, model)
    if provider == "claude":
        return ClaudeAdapter(root, timeout, model)
    raise ValueError(f"Unknown AI provider: {provider}")
