from __future__ import annotations

from types import SimpleNamespace

from paperflow import doctor


def test_command_supports_a_longer_obsidian_startup_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: "obsidian")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["timeout"] = kwargs["timeout"]
        return SimpleNamespace(
            returncode=0,
            stdout="1.12.7\n",
            stderr="",
        )

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    ok, detail = doctor._command("obsidian", ["version"], timeout=45)

    assert ok
    assert detail == "1.12.7"
    assert captured == {
        "command": ["obsidian", "version"],
        "timeout": 45,
    }
