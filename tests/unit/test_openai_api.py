"""API provider tests use fake HTTP transport; no account/network required."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from paperflow.ai.http_client import api_endpoint, chat_json
from paperflow.ai.providers import make_provider
from paperflow.ai.mock_adapter import MockAdapter
from paperflow.models import PaperMetadata
from paperflow.workspace import AIProfile, ProviderConfig


class FakeResponse(io.BytesIO):
    status = 200


def test_https_and_redirect_guard() -> None:
    assert api_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/chat/completions"
    with pytest.raises(ValueError, match="HTTPS"):
        api_endpoint("http://example.org/v1")
    with pytest.raises(ValueError, match="credentials"):
        api_endpoint("https://token@example.org/v1")


def test_json_client_uses_environment_only_and_rejects_truncation(monkeypatch):
    monkeypatch.setenv("PAPERFLOW_OPENAI_API_KEY", "secret-test-key")
    requests = []

    class Opener:
        def open(self, req, timeout):
            requests.append((req, timeout))
            return FakeResponse(json.dumps({
                "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"ok"}'}}]
            }).encode("utf-8"))

    with patch("paperflow.ai.http_client.urllib.request.build_opener", return_value=Opener()):
        value = chat_json(
            base_url="https://example.org/v1",
            api_key_env="PAPERFLOW_OPENAI_API_KEY",
            model="model-test", system_prompt="Test", user_prompt="Return JSON",
            timeout=4,
        )
    assert value == {"answer": "ok"}
    assert requests[0][0].get_header("Authorization") == "Bearer secret-test-key"
    assert b"secret-test-key" not in requests[0][0].data
    assert requests[0][1] == 4

    monkeypatch.delenv("PAPERFLOW_OPENAI_API_KEY")
    with pytest.raises(RuntimeError, match="credential"):
        chat_json(base_url="https://example.org/v1", api_key_env="PAPERFLOW_OPENAI_API_KEY",
                  model="test", system_prompt="Test", user_prompt="Return JSON", timeout=4)


def test_optional_api_provider_validates_analysis_without_cli(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PAPERFLOW_OPENAI_API_KEY", "test-secret")
    config = ProviderConfig(model="model-test", base_url="https://example.org/v1")
    provider = make_provider("openai-api", tmp_path, config)
    assert provider.check_available().available
    metadata = PaperMetadata(paper_uid="arxiv:2504.16054", paper_title="Example paper")
    staged = tmp_path / "paper.txt"
    staged.write_text("Study the method.", encoding="utf-8")
    fake = MockAdapter().analyze(metadata, staged).model_dump()
    with patch("paperflow.ai.openai_compatible_adapter.chat_json", return_value=fake):
        actual = provider.analyze(metadata, staged, AIProfile(provider="openai-api", model="model-test"))
    assert actual.ai_analysis_status == "complete"
    assert actual.ai_summary_short
