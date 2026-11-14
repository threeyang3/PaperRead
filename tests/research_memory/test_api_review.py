"""Offline regressions for actual main-branch API integration gaps."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from paperflow.ai.http_client import chat_json, api_endpoint
from paperflow.ai.factory import make_adapter
from paperflow.ai.openai_compatible_adapter import OpenAICompatibleAdapter
from paperflow.ai.mock_adapter import MockAdapter
from paperflow.models import PaperMetadata


class Opener:
    def __init__(self, value):
        self.value = value
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return io.BytesIO(json.dumps(self.value).encode())


def call(value, monkeypatch, **kwargs):
    monkeypatch.setenv("PAPERFLOW_OPENAI_API_KEY", "private-key")
    opener = Opener(value)
    params = dict(base_url="https://api.example/v1", api_key_env="PAPERFLOW_OPENAI_API_KEY",
                  model="test-model", system_prompt="s", user_prompt="q", timeout=5)
    params.update(kwargs)
    with patch("paperflow.ai.http_client.urllib.request.build_opener", return_value=opener):
        return chat_json(**params), opener


def response(content='{"ok":true}', finish="stop", message=None):
    return {"choices": [{"finish_reason": finish, "message": message or {"content": content}}]}


@pytest.mark.parametrize("value", [[], None, 1, "text", {}, {"choices": []}, {"choices": [None]},
                                   {"choices": [1]}, {"choices": [{}]}, response(finish=None),
                                   response(finish="length"), response(message={"refusal": "no", "content": '{}'}),
                                   response(message="not-object"), response(content="[]"), response(content="invalid")])
def test_bad_envelopes_fail_closed(value, monkeypatch):
    with pytest.raises((ValueError, RuntimeError)):
        call(value, monkeypatch)


def test_key_not_in_request_body(monkeypatch):
    result, opener = call(response(), monkeypatch)
    assert result == {"ok": True}
    request, timeout = opener.requests[0]
    assert timeout == 5
    assert request.get_header("Authorization") == "Bearer private-key"
    assert b"private-key" not in request.data


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"timeout": True}, {"max_tokens": 0}, {"max_tokens": True}, {"model": ""}])
def test_invalid_request_budget_rejected(kwargs, monkeypatch):
    with pytest.raises(ValueError):
        call(response(), monkeypatch, **kwargs)


def test_factory_can_reach_direct_api_without_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERFLOW_OPENAI_BASE_URL", "https://example.org/v1")
    adapter = make_adapter("openai-api", tmp_path, model="model")
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.base_url == "https://example.org/v1"


def test_actual_output_schema_is_sent_to_api(tmp_path):
    root = Path(__file__).resolve().parents[2]
    metadata = PaperMetadata(paper_uid="arxiv:2504.16054", paper_title="Example")
    text = tmp_path / "paper.txt"
    text.write_text("Only the provided text is available.", encoding="utf-8")
    output = MockAdapter().analyze(metadata, text).model_dump()
    with patch("paperflow.ai.openai_compatible_adapter.chat_json", return_value=output) as transport:
        result = OpenAICompatibleAdapter(root, model="test-model", base_url="https://api.example/v1").analyze(metadata, text)
    sent = transport.call_args.kwargs["system_prompt"]
    assert '"required"' in sent and '"ai_relevance_score"' in sent
    assert result.ai_analysis_status == "complete"


def test_single_file_obsidian_bundle_has_no_unshipped_entrypoint(tmp_path):
    import importlib.util
    import subprocess
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("bundle_research", root / "scripts/bundle_research.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "main.js"
    bundle = module.bundle_main()
    target.write_text(bundle, encoding="utf-8")
    assert '__paperflowResearchRequire("./research.js").open(this)' in bundle
    for name in ("model", "storage", "client", "panel"):
        assert f'"./research-memory/{name}.js": function' in bundle
    subprocess.run(["node", "--check", str(target)], check=True, capture_output=True)


def test_workspace_installer_includes_research_assets_and_preserves_user_edits(tmp_path, monkeypatch):
    import paperflow.workspace as workspace
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(workspace, "_distribution_resource", lambda relative: root / relative)
    settings = workspace.WorkspaceSettings.model_validate(workspace.default_workspace_dict())
    workspace._install_automation_plugin(tmp_path, settings)
    dest = tmp_path / ".obsidian/plugins/paperflow-automation/research-memory/model.js"
    assert dest.is_file()
    dest.write_text("// manually modified", encoding="utf-8")
    workspace._install_automation_plugin(tmp_path, settings)
    assert dest.read_text(encoding="utf-8") == "// manually modified"
    assert dest.with_name(dest.name + ".new").is_file()
