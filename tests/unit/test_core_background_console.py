from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import paperflow.cli as cli


@pytest.mark.skipif(os.name != "nt", reason="Windows console process flags")
def test_background_core_and_venv_child_have_no_console(tmp_path: Path, monkeypatch) -> None:
    """Exercise the launcher through a real Windows Python subprocess.

    The venv launcher redirects to the base interpreter. DETACHED_PROCESS can
    make that child open its own console, even when NO_WINDOW is also set.
    """
    popen = subprocess.Popen
    consoles: list[int] = []
    (tmp_path / "data").mkdir()

    def capture_launch(command, **kwargs):
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert not kwargs["creationflags"] & subprocess.DETACHED_PROCESS
        probe = popen(
            [sys.executable, "-c", "import ctypes,json; print(json.dumps(ctypes.windll.kernel32.GetConsoleWindow()))"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=kwargs["creationflags"],
        )
        stdout, stderr = probe.communicate(timeout=15)
        assert probe.returncode == 0, stderr.decode(errors="replace")
        consoles.append(json.loads(stdout))
        class Launched:
            def poll(self):
                return 0
        return Launched()

    session = {"pid": 12345, "base_url": "http://127.0.0.1:23140"}
    sessions = iter([None, session])
    monkeypatch.setattr(cli, "read_session", lambda _root: next(sessions))
    monkeypatch.setattr(cli.subprocess, "Popen", capture_launch)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    class Healthy:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *_args, **_kwargs: Healthy())
    result = CliRunner().invoke(cli.app, ["zotero", "service", "start", "--data-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert consoles == [0]
