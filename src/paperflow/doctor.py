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
from paperflow.clock import WorkspaceClock
from paperflow._version import __version__
from paperflow.ai.providers import make_provider
from paperflow.sync_safety import find_sync_conflicts
from paperflow.pdf_resolver import resolve_current_pdf
from paperflow.zotero.mapping_index import diagnose_mapping_index
from paperflow.zotero.store import runtime_root, state_root


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
    writable = os.access(root, os.W_OK)
    checks.append(("Write permission", writable, str(root)))
    checks.append(("Python", sys.version_info >= (3, 11), sys.version.split()[0]))
    checks.append(("PaperFlow module", True, str(Path(__file__).resolve().parent)))
    checks.append(
        (
            "Console script",
            bool(shutil.which("paperflow")),
            shutil.which("paperflow") or "not found on PATH",
        )
    )
    checks.append(
        (
            "Virtual environment",
            sys.prefix != sys.base_prefix,
            f"prefix={sys.prefix}; base={sys.base_prefix}",
        )
    )
    private_python = next(
        (
            candidate
            for candidate in (
                root / ".paperflow/.venv/Scripts/python.exe",
                root / ".paperflow/.venv/bin/python",
            )
            if candidate.exists()
        ),
        None,
    )
    runtime = shutil.which("uv") or (str(private_python) if private_python else None)
    checks.append(
        (
            "uv or venv",
            bool(runtime or sys.prefix != sys.base_prefix),
            runtime or sys.prefix,
        )
    )
    orphan_job = None
    try:
        clock = WorkspaceClock(cfg.timezone.key)
        current_time = clock.iso_now()
        timezone_ok = True
    except Exception as exc:
        current_time = str(exc)
        timezone_ok = False
    checks.append(("Configuration", timezone_ok, f"timezone={cfg.data['vault']['timezone']}"))
    checks.append(("Workspace time", timezone_ok, current_time))
    if cfg.workspace:
        checks.append(
            (
                "Workspace schema",
                cfg.workspace.versions.workspace == 3,
                f"version={cfg.workspace.versions.workspace}",
            )
        )
    pipeline_lock = root / ".paperflow/runtime/pipeline.lock"
    checks.append(
        (
            "Pipeline lock",
            not pipeline_lock.exists(),
            str(pipeline_lock) if pipeline_lock.exists() else "not held",
        )
    )
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
        chatgpt_config = cfg.workspace.ai.providers["chatgpt-web"]
        # Browser analysis is explicitly consent-gated. A missing optional
        # browser must not make the normal local/CLI workflow unhealthy while
        # PDF upload is disabled.
        if not chatgpt_config.allow_pdf_upload:
            checks.append(
                (
                    "ChatGPT Web",
                    True,
                    "disabled until explicit PDF upload consent; browser not required",
                )
            )
        else:
            report = make_provider("chatgpt-web", root, chatgpt_config).check_available()
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
    required_bases = [
        "Paper Library.base", "Daily Intake.base", "Reading Queue.base",
        "Reproduction Queue.base", "Paper Requests.base", "Annotations.base",
        "Reviews.base", "Community Contributions.base",
        "Community Reviews.base", "Orphaned Annotations.base",
        "Publication Outbox.base",
    ]
    checks.append(("Bases", all((root / base_root / name).exists() for name in required_bases), base_root))
    if cfg.workspace:
        from paperflow.obsidian.pdf_plus import status as pdf_plus_status

        pdf_plus = pdf_plus_status(root)
        checks.append((
            "PDF++ integration",
            (not pdf_plus["installed"]) or pdf_plus["compatible"],
            (
                f"version={pdf_plus.get('version')}; selection adapter="
                f"{pdf_plus.get('selection_capture')}; direct PDF editing disabled"
                if pdf_plus["installed"] else "not installed; native page-link fallback active"
            ),
        ))
        for display, rule in [
            ("Annotation root", cfg.workspace.paths.annotation_note),
            ("Review root", cfg.workspace.paths.paper_review),
            ("Community cache", cfg.workspace.paths.community_cache),
            ("Community outbox", cfg.workspace.paths.community_outbox),
        ]:
            checks.append((display, (root / rule.root).exists(), rule.root))
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
            and automation.get("timezone", cfg.timezone.key) == cfg.timezone.key
        )
        runtime_path = root / ".paperflow/runtime/plugin-state.json"
        runtime = (
            json.loads(runtime_path.read_text(encoding="utf-8"))
            if runtime_path.exists()
            else {}
        )
        inbox_ok = runtime.get("lastInboxExitCode") == 0
        automation_detail = (
            f"daily={automation.get('dailyLocalTime')}; "
            f"timezone={automation.get('timezone')}; "
            f"inbox={automation.get('inboxIntervalMinutes')}m"
        )
        inbox_detail = f"{runtime.get('lastInboxAt')}; exit={runtime.get('lastInboxExitCode')}"
        orphan_job = runtime.get("activeJob")
    except Exception as exc:
        automation_ok = inbox_ok = False
        automation_detail = inbox_detail = str(exc)
    checks.append(("Obsidian automation schedule", automation_ok, automation_detail))
    checks.append(("Obsidian automation last Inbox", inbox_ok, inbox_detail))
    checks.append(
        (
            "Obsidian orphan job",
            not bool(orphan_job),
            json.dumps(orphan_job, ensure_ascii=False)
            if orphan_job
            else "none",
        )
    )
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
    checks.append(("JSON Schemas", all((root / ".paperflow/schemas" / name).exists() for name in [
        "raw-paper.schema.json", "ai-analysis.schema.json", "user-paper.schema.json",
        "paper-analysis.schema.json", "visual-assets.schema.json",
        "paper-note.schema.json", "paper-relationships.schema.json",
        "user-annotation.schema.json", "user-paper-review.schema.json",
        "annotation-index.schema.json", "community-contribution.schema.json",
        "community-profile.schema.json", "community-retraction.schema.json",
        "community-manifest.schema.json",
    ]), ".paperflow/schemas"))
    checks.append(("YAML template", (root / "90 System/Templates/Paper Note Template.md").exists(), "Paper Note Template.md"))
    briefs = sorted(cfg.path("daily_brief_folder").glob("*.md"), reverse=True)
    checks.append(("Latest daily status", True, briefs[0].name if briefs else "no daily run recorded"))
    inbox_logs = sorted((root / ".paperflow/logs").glob("inbox-*.log"), reverse=True)
    checks.append(("Latest inbox status", True, inbox_logs[0].name if inbox_logs else "no inbox run recorded"))
    pdf_indexes = sorted(
        (root / ".paperflow/data/derived/pdf-index").glob("*.json")
    )
    pdf_issues: list[str] = []
    for index in pdf_indexes:
        try:
            value = json.loads(index.read_text(encoding="utf-8"))
            resolve_current_pdf(root, str(value["paper_uid"]))
        except Exception as exc:
            pdf_issues.append(f"{index.name}: {exc}")
    checks.append(
        (
            "PDF indexes",
            not pdf_issues,
            f"count={len(pdf_indexes)}; issues={len(pdf_issues)}"
            + (f"; first={pdf_issues[0]}" if pdf_issues else ""),
        )
    )
    mapping_index = diagnose_mapping_index(root)
    checks.append(
        (
            "Zotero mapping index",
            bool(mapping_index.get("ok")),
            json.dumps(mapping_index, ensure_ascii=False, sort_keys=True),
        )
    )
    session_path = state_root(root) / "zotero-core-session.json"
    pairing_path = runtime_root(root) / "zotero-core-session.token"
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session_pid = int(session.get("pid") or 0)
        session_detail = f"pid={session_pid}; port={session.get('port')}"
        session_ok = session_pid > 0
    except Exception as exc:
        session_ok = False
        session_detail = f"not active: {exc}"
    checks.append(("Zotero Core session", session_ok, session_detail))
    checks.append(
        (
            "Zotero pairing token",
            pairing_path.is_file(),
            str(pairing_path) if pairing_path.is_file() else "not present",
        )
    )
    conflicts = find_sync_conflicts(root)
    checks.append(
        (
            "Sync conflict files",
            not conflicts,
            "none" if not conflicts else f"count={len(conflicts)}",
        )
    )
    return [{"name": n, "ok": ok, "detail": detail} for n, ok, detail in checks]
