from __future__ import annotations

from pathlib import Path
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


def test_doctor_reports_historical_vault_community_outbox_read_only(
    tmp_path: Path,
) -> None:
    record = tmp_path / "data/community/outbox/reader/contribution.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}", encoding="utf-8")

    ok, detail = doctor._legacy_community_outbox_status(tmp_path)

    assert ok is False
    assert "manual review" in detail
    assert "nothing was moved or deleted" in detail
    assert record.read_text(encoding="utf-8") == "{}"
