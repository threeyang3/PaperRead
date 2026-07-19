from __future__ import annotations
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from paperflow.config import Config
from paperflow.utils import iso_beijing
from paperflow.ai.providers import make_provider
from paperflow.sync_safety import find_sync_conflicts


def _command(
    name: str,
    args: list[str] | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    executable = shutil.which(name)
    if not executable: return False, "not found"
    try:
        result = subprocess.run(
            [executable, *(args or ["--version"])],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or result.stderr).strip()
        detail = output.splitlines()[0][:160] if output else executable
        return result.returncode == 0, detail
    except Exception as exc: return False, str(exc)


def run_doctor(cfg: Config, network: bool = False) -> list[dict]:
    root = cfg.root
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Vault path", root.exists(), str(root)))
    checks.append(
        (
            "Workspace configuration",
            (root / ".paperflow/workspace.yaml").exists(),
            ".paperflow/workspace.yaml",
        )
    )
    try:
        probe = root / ".paperflow/runtime/.doctor-write"; probe.parent.mkdir(parents=True, exist_ok=True); probe.write_text("ok"); probe.unlink(); writable = True
    except Exception: writable = False
    checks.append(("Write permission", writable, str(root)))
    checks.append(("Python", sys.version_info >= (3, 11), sys.version.split()[0]))
    checks.append(("uv or venv", bool(shutil.which("uv") or sys.prefix != sys.base_prefix), shutil.which("uv") or sys.prefix))
    checks.append(("Configuration", cfg.data["vault"]["timezone"] == "Asia/Shanghai", f"timezone={cfg.data['vault']['timezone']}"))
    checks.append(("UI locale", cfg.ui_locale.locale in {"zh-CN", "en"}, f"{cfg.ui_locale.locale} ({cfg.ui_locale.source})"))
    try: sqlite3.connect(root / ".paperflow/state/paperflow.db").execute("select 1"); sqlite_ok = True
    except Exception: sqlite_ok = False
    checks.append(("SQLite", sqlite_ok, sqlite3.sqlite_version))
    for display, command in [("Codex CLI", "codex"), ("Claude Code", "claude")]:
        ok, detail = _command(command)
        if command == "codex" and not ok:
            try:
                completed = sqlite3.connect(root / ".paperflow/state/paperflow.db").execute("SELECT model,created_at FROM analysis_runs WHERE provider='codex' AND status='complete' ORDER BY created_at DESC LIMIT 1").fetchone()
                if completed:
                    ok, detail = True, f"verified by completed analysis: model={completed[0]}, at={completed[1]}"
            except Exception:
                pass
        checks.append((display, ok, detail))
    if cfg.workspace and "chatgpt-web" in cfg.workspace.ai.providers:
        report = make_provider(
            "chatgpt-web",
            root,
            cfg.workspace.ai.providers["chatgpt-web"],
        ).check_available()
        checks.append(
            (
                "ChatGPT Web",
                report.available,
                f"{report.executable}; {report.detail}",
            )
        )
    obsidian = shutil.which("obsidian") or ("D:/Obsidian/Obsidian.exe" if Path("D:/Obsidian/Obsidian.exe").exists() else None)
    checks.append(("Obsidian", bool(obsidian), str(obsidian or "not found")))
    cli_ok, cli_detail = _command("obsidian", ["version"], timeout=45)
    checks.append(("Obsidian CLI", cli_ok, cli_detail))
    base_root = (
        cfg.workspace.obsidian.bases.root
        if cfg.workspace
        else "00 Dashboard/Bases"
    )
    checks.append(("Bases", all((root / base_root / name).exists() for name in ["Paper Library.base", "Daily Intake.base", "Reading Queue.base", "Reproduction Queue.base", "Paper Requests.base"]), base_root))
    manifest = root / ".obsidian/plugins/form-flow/manifest.json"
    checks.append(("Form Flow installed", manifest.exists(), str(manifest)))
    enabled = False
    try: enabled = "form-flow" in json.loads((root / ".obsidian/community-plugins.json").read_text())
    except Exception: pass
    checks.append(("Form Flow enabled", enabled and manifest.exists(), "form-flow"))
    checks.append(("Form Flow form", (root / "90 System/Forms/添加论文.cform").exists(), "添加论文.cform"))
    checks.append(("Request folder", cfg.path("request_folder").exists(), str(cfg.path("request_folder"))))
    checks.append(("PDF extraction", importlib.util.find_spec("fitz") is not None or bool(shutil.which("pdftotext")), "PyMuPDF/pdftotext"))
    automation_manifest = root / ".obsidian/plugins/paperflow-automation/manifest.json"
    automation_data = root / ".obsidian/plugins/paperflow-automation/data.json"
    checks.append(("PaperFlow Automation installed", automation_manifest.exists(), str(automation_manifest)))
    automation_enabled = False
    try:
        automation_enabled = "paperflow-automation" in json.loads((root / ".obsidian/community-plugins.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    checks.append(("PaperFlow Automation enabled", automation_enabled, "paperflow-automation"))
    try:
        automation = json.loads(automation_data.read_text(encoding="utf-8"))
        expected_daily = (
            cfg.workspace.obsidian.daily_local_time
            if cfg.workspace
            else "08:00"
        )
        expected_interval = (
            cfg.workspace.obsidian.inbox_interval_minutes
            if cfg.workspace
            else 5
        )
        automation_ok = (
            automation.get("enabled") is True
            and automation.get("dailyLocalTime") == expected_daily
            and automation.get("inboxIntervalMinutes") == expected_interval
        )
        runtime_path = root / ".paperflow/runtime/plugin-state.json"
        runtime = (
            json.loads(runtime_path.read_text(encoding="utf-8"))
            if runtime_path.exists()
            else {}
        )
        inbox_ok = runtime.get("lastInboxExitCode") == 0
        automation_detail = f"daily={automation.get('dailyLocalTime')}; inbox={automation.get('inboxIntervalMinutes')}m"
        inbox_detail = f"{runtime.get('lastInboxAt')}; exit={runtime.get('lastInboxExitCode')}"
    except Exception as exc:
        automation_ok = inbox_ok = False
        automation_detail = inbox_detail = str(exc)
    checks.append(("Obsidian automation schedule", automation_ok, automation_detail))
    checks.append(("Obsidian automation last Inbox", inbox_ok, inbox_detail))
    checks.append(
        (
            "Windows scheduler independence",
            not bool(cfg.section("scheduler").get("enabled", False)),
            "Obsidian plugin lifecycle is the configured scheduler",
        )
    )
    if network:
        try: socket.create_connection(("export.arxiv.org", 443), 10).close(); arxiv_ok = True
        except Exception: arxiv_ok = False
        checks.append(("arXiv network", arxiv_ok, "export.arxiv.org:443"))
    else: checks.append(("arXiv network", True, "skipped (use --network)"))
    checks.append(("JSON Schemas", all((root / ".paperflow/schemas" / name).exists() for name in ["raw-paper.schema.json", "ai-analysis.schema.json", "user-paper.schema.json", "paper-analysis.schema.json", "visual-assets.schema.json", "paper-note.schema.json", "paper-relationships.schema.json"]), ".paperflow/schemas"))
    checks.append(("YAML template", (root / "90 System/Templates/Paper Note Template.md").exists(), "Paper Note Template.md"))
    briefs = sorted(cfg.path("daily_brief_folder").glob("*.md"), reverse=True)
    checks.append(("Latest daily status", True, briefs[0].name if briefs else "no daily run recorded"))
    inbox_logs = sorted((root / ".paperflow/logs").glob("inbox-*.log"), reverse=True)
    checks.append(("Latest inbox status", True, inbox_logs[0].name if inbox_logs else "no inbox run recorded"))
    checks.append(("Current Beijing time", iso_beijing().endswith("+08:00"), iso_beijing()))
    conflicts = find_sync_conflicts(root)
    checks.append(
        (
            "Sync conflict files",
            not conflicts,
            "none" if not conflicts else f"count={len(conflicts)}",
        )
    )
    return [{"name": n, "ok": ok, "detail": detail} for n, ok, detail in checks]
