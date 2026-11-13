from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.obsidian.onboarding import initialize, setup_plan, prepare_form, check_core
from paperflow.workspace import load_workspace_settings


def hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_first_run_preview_is_readonly_and_initialize_preserves_existing_notes(tmp_path: Path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian/user-settings.json").write_text('{"keep":true}')
    note = tmp_path / "my-notes.md"
    note.write_text("我的笔记与 [[现有链接]]", encoding="utf-8")
    before = hashes(tmp_path)
    plan = setup_plan(tmp_path)
    assert plan["status"] == "new" and plan["network_changes"] == 0
    assert hashes(tmp_path) == before
    result = initialize(tmp_path, plan["digest"])
    assert result["initialized"] and result["errors"] == []
    assert hashes(tmp_path)["my-notes.md"] == before["my-notes.md"]
    assert (Path(result["backup"]) / "files/.obsidian/user-settings.json").exists()
    _, settings = load_workspace_settings(tmp_path)
    assert not settings.obsidian.enable_daily_automation
    assert not settings.ai.profiles["full_analysis"].fallback_profile
    snapshot = hashes(tmp_path)
    assert setup_plan(tmp_path)["status"] == "ready"
    assert not initialize(tmp_path, "")["initialized"]
    assert hashes(tmp_path) == snapshot


@pytest.mark.parametrize("target", ["00 Dashboard/Bases/Paper Library.base", "90 System/Templates/Paper Note Template.md"])
def test_first_run_refuses_existing_generated_targets(tmp_path: Path, target: str):
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("personal customization")
    plan = setup_plan(tmp_path)
    assert plan["status"] == "conflict"
    with pytest.raises(ValueError, match="conflicts"):
        initialize(tmp_path, plan["digest"])
    assert path.read_text() == "personal customization"
    assert not (tmp_path / ".paperflow/workspace.yaml").exists()


def test_first_run_rejects_stale_preview_before_writes(tmp_path: Path):
    plan = setup_plan(tmp_path)
    path = tmp_path / "00 Dashboard/PaperFlow Start.md"
    path.parent.mkdir(parents=True)
    path.write_text("new user content")
    with pytest.raises(ValueError):
        initialize(tmp_path, plan["digest"])
    assert not (tmp_path / ".paperflow/workspace.yaml").exists()


def test_first_run_cli_requires_preview_digest(tmp_path: Path):
    result = CliRunner().invoke(app, ["workspace", "onboard", "--vault", str(tmp_path), "--apply"])
    assert result.exit_code == 1 and "preview" in result.stdout.lower()
    assert not (tmp_path / ".paperflow").exists()


def test_form_preparation_without_dependency_is_readonly(tmp_path: Path):
    plan = setup_plan(tmp_path)
    initialize(tmp_path, plan["digest"])
    before = hashes(tmp_path)
    assert prepare_form(tmp_path)["status"] == "plugin-required"
    assert hashes(tmp_path) == before


def test_failed_staging_leaves_no_partial_workspace_and_can_retry(tmp_path: Path, monkeypatch):
    import paperflow.obsidian.onboarding as onboarding
    original = onboarding.install_workspace_resources
    note = tmp_path / "personal.md"
    note.write_text("user notes")
    plan = setup_plan(tmp_path)
    def fail(stage, settings):
        original(stage, settings)
        raise OSError("simulated disk failure")
    monkeypatch.setattr(onboarding, "install_workspace_resources", fail)
    with pytest.raises(RuntimeError, match="disk failure"):
        initialize(tmp_path, plan["digest"])
    assert not (tmp_path / ".paperflow/workspace.yaml").exists()
    assert not (tmp_path / "90 System/Templates/Paper Note Template.md").exists()
    assert note.read_text() == "user notes"
    assert setup_plan(tmp_path)["status"] == "new"
    monkeypatch.setattr(onboarding, "install_workspace_resources", original)
    assert initialize(tmp_path, plan["digest"])["initialized"]


@pytest.mark.parametrize("edit_generated", [False, True])
def test_failed_commit_rolls_back_generated_files_but_preserves_user_edits(tmp_path: Path, monkeypatch, edit_generated):
    original_open = Path.open
    marker = tmp_path / ".paperflow/workspace.yaml"
    template = tmp_path / "90 System/Templates/Paper Note Template.md"
    plan = setup_plan(tmp_path)
    def interrupted(path, mode="r", *args, **kwargs):
        if path == marker and mode == "xb":
            if edit_generated:
                with original_open(template, "a", encoding="utf-8") as stream:
                    stream.write("\nuser-added personal text\n")
            raise OSError("commit interrupted")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", interrupted)
    with pytest.raises(RuntimeError, match="commit interrupted"):
        initialize(tmp_path, plan["digest"])
    assert not marker.exists()
    assert not (tmp_path / "00 Dashboard/Bases/Paper Library.base").exists()
    if edit_generated:
        assert "user-added personal text" in template.read_text(encoding="utf-8")
        assert setup_plan(tmp_path)["status"] == "conflict"
    else:
        assert not template.exists()
        assert setup_plan(tmp_path)["status"] == "new"


def test_core_check_uses_actual_port_and_rejects_wrong_session_token(tmp_path: Path):
    from paperflow.zotero.core_service import PaperFlowCoreService
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    try:
        result = check_core(tmp_path)
        assert result["base_url"] == service.url and result["authenticated"]
        token = tmp_path / ".paperflow/runtime/zotero-core-session.token"
        token.write_text("wrong-session-token", encoding="utf-8")
        with pytest.raises(ValueError, match="verified"):
            check_core(tmp_path)
    finally:
        service.stop()


def test_duplicate_core_cannot_bind_or_replace_live_session(tmp_path: Path):
    from paperflow.zotero.core_service import PaperFlowCoreService
    first = PaperFlowCoreService(tmp_path, port=0)
    first.start()
    session = tmp_path / ".paperflow/state/zotero-core-session.json"
    before = session.read_bytes()
    second = PaperFlowCoreService(tmp_path, port=first.httpd.server_port)
    try:
        with pytest.raises(OSError):
            second.start()
        assert session.read_bytes() == before
        assert check_core(tmp_path)["authenticated"]
    finally:
        first.stop()


def test_form_conflicts_are_reported_without_overwriting_custom_form(tmp_path: Path):
    from paperflow.obsidian.form_flow import _metadata
    initialize(tmp_path, setup_plan(tmp_path)["digest"])
    plugin = tmp_path / ".obsidian/plugins/form-flow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text('{"version":"0.0.8"}')
    enabled = tmp_path / ".obsidian/community-plugins.json"
    enabled.write_text('["form-flow"]')
    _, metadata = _metadata()
    relative = next(iter(metadata["files"].values()))
    custom = tmp_path / relative
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text("personal form customization")
    result = prepare_form(tmp_path)
    assert result["status"] == "needs-attention" and relative in result["conflicts"]
    assert custom.read_text() == "personal form customization"
    state_path = tmp_path / ".paperflow/state/integrations/form-flow.json"
    legacy = json.loads(state_path.read_text(encoding="utf-8"))
    legacy["installed_hashes"][relative] = hashlib.sha256(custom.read_bytes()).hexdigest()
    state_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert prepare_form(tmp_path)["status"] == "needs-attention"
    assert custom.read_text() == "personal form customization"


@pytest.mark.skipif(os.name != "nt", reason="Windows inherited pipe regression")
def test_core_launch_returns_with_captured_pipes_while_service_stays_running(tmp_path: Path):
    (tmp_path / "data").mkdir()
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    command = [sys.executable, "-m", "paperflow.cli", "zotero", "service"]
    try:
        result = subprocess.run(command + ["start", "--data-root", str(tmp_path), "--port", str(port)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15,
                                env={**os.environ, "PYTHONUTF8": "1"})
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "started"
        assert (tmp_path / "state/zotero-core-session.json").exists()
    finally:
        subprocess.run(command + ["stop", "--data-root", str(tmp_path)],
                       capture_output=True, timeout=15)


@pytest.mark.skipif(os.name != "nt", reason="Windows process query regression")
def test_process_probe_does_not_terminate_a_live_windows_process():
    from paperflow.cli import _pid_alive
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.2)
        assert child.poll() is None
        assert _pid_alive(child.pid)
        assert _pid_alive(child.pid)
        time.sleep(0.1)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows command-line identity")
@pytest.mark.parametrize("suffix,expected", [("", True), ("-other", False)])
def test_core_process_identity_matches_exact_root(tmp_path: Path, monkeypatch, suffix: str, expected: bool):
    from paperflow.cli import _is_core_service_pid
    target = tmp_path / ("中文 library" + suffix)
    command = subprocess.list2cmdline(["python.exe", "-m", "paperflow.cli", "zotero", "service", "serve", "--vault", str(target)])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, command.encode("utf-8"), b""))
    assert _is_core_service_pid(1234, tmp_path / "中文 library") is expected
