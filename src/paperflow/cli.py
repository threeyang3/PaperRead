from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import signal
import urllib.error
import urllib.request
from pathlib import Path
import typer
from ruamel.yaml import YAML

from paperflow.application import PaperApplicationService
from paperflow.config import ensure_layout, load_config
from paperflow.database import Database
from paperflow.doctor import run_doctor
from paperflow.locking import FileLock
from paperflow.obsidian.bases import rebuild_bases
from paperflow.obsidian.frontmatter import read_note
from paperflow.pipeline.analyze import analyze_uid
from paperflow.pipeline.daily import run_daily
from paperflow.pipeline.discover import discover as discover_papers
from paperflow.pipeline.import_paper import import_paper
from paperflow.pipeline.inbox import process_inbox
from paperflow.pipeline.render import render_uid
from paperflow.pipeline.visuals import refresh_record_visuals
from paperflow.data.records import split_legacy_record
from paperflow.paths.templates import safe_component
from paperflow.scheduler import windows
from paperflow.validation import validate_all
from paperflow.utils import atomic_json, atomic_write, iso_beijing, now_beijing
from paperflow.migrations import migrate_v2
from paperflow.acceptance import audit as acceptance_audit
from paperflow.i18n import tr
from paperflow.migration_engine import (
    apply as apply_migration,
    build_plan as build_migration_plan,
    migration_history,
    rollback as rollback_migration,
    status as migration_status,
    verify as verify_migration,
)
from paperflow.paths.service import (
    preview_all,
    preview_record_paths,
    validate_path_settings,
    variables_documentation,
)
from paperflow.paths.migrate import migrate_paths
from paperflow.paths.redirects import plan_redirect_labels, apply_redirect_labels
from paperflow.workspace import (
    backup_workspace_config,
    init_workspace,
    load_workspace_settings,
    resolve_vault_root,
    dump_yaml,
    export_example,
    install_workspace_resources,
)
from paperflow.ai.providers import (
    capability_summary,
    explain_profile,
    make_provider,
)
from paperflow.health import scan_workspace_health
from paperflow.template_sets import TemplateSetManager
from paperflow.obsidian.artifacts import apply_user_note_migration, plan_user_note_migration, ensure_user_note, artifact_path
from paperflow.obsidian.view_model import build_paper_view_model
from paperflow.zotero import environment as zotero_environment
from paperflow.zotero.environment import redact_environment
from paperflow.zotero.core_service import PaperFlowCoreService, read_pairing_token, read_session
from paperflow.zotero.mapping import apply_links, load_items, plan_links
from paperflow.zotero.store import runtime_root, state_root
from paperflow.zotero.cli_commands import attach_zotero_commands


def _configure_console_stream(stream) -> None:
    """Keep Windows legacy consoles from turning successful jobs into errors."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        return


_configure_console_stream(sys.stdout)
_configure_console_stream(sys.stderr)
from paperflow.obsidian.form_flow import (
    install_or_upgrade as install_form_flow,
    integration_status as form_flow_status,
    try_install_official_plugin,
)
from paperflow.feed import (
    auto_publish_feed,
    build_feed,
    create_snapshot,
    feed_diff,
    feed_git_status,
    inspect_feed,
    init_feed_repository,
    publish_plan,
    scan_feed,
    sync_feed,
    validate_feed,
)
from paperflow.versioning import APPLICATION_VERSION, VERSIONS
from paperflow.update_manager import (
    apply_staged_update,
    check_for_update,
    stage_update,
)
from paperflow.workspace_ops import (
    create_workspace_backup,
    export_user_data,
    import_user_data,
)
from paperflow.workspace_v2 import (
    apply_workspace_v2,
    plan_workspace_v2,
    verify_workspace_v2,
)

app = typer.Typer(
    help="PaperFlow：本地优先的 AI 论文采集、分析与 Obsidian 学习工作流。",
    no_args_is_help=True,
    invoke_without_command=True,
)
schedule_app = typer.Typer(
    help="仅检查或移除旧版 Windows 计划任务；自动化由 Obsidian 插件负责。",
    no_args_is_help=True,
)
migrate_app = typer.Typer(help="规划、执行、验证和回滚正式数据迁移。", no_args_is_help=True)
config_app = typer.Typer(help="查看和验证分层 Workspace 配置。", no_args_is_help=True)
paths_app = typer.Typer(help="预览并验证安全路径模板。", no_args_is_help=True)
workspace_app = typer.Typer(help="检查、备份和维护 Workspace。", no_args_is_help=True)
ai_app = typer.Typer(help="检查并解释 AI Provider、模型和分析 profile。", no_args_is_help=True)
integration_app = typer.Typer(help="安装和维护版本化 Obsidian 集成。", no_args_is_help=True)
publish_app = typer.Typer(help="构建、验证和检查本地公共 Feed。", no_args_is_help=True)
source_app = typer.Typer(help="管理并同步只读公共 Feed 数据源。", no_args_is_help=True)
update_app = typer.Typer(help="检查版本信息并迁移 Workspace；不修改程序安装。", no_args_is_help=True)
paper_app = typer.Typer(help="导入、分析、渲染和验证论文。", no_args_is_help=True)
templates_app = typer.Typer(help="管理 Paper Workspace 模板集。", no_args_is_help=True)
zotero_app = typer.Typer(
    help="检测并维护 PaperFlow 与 Zotero 的安全集成。真实 Zotero 写入必须经插件 API。",
    no_args_is_help=True,
)
zotero_service_app = typer.Typer(help="管理 loopback-only PaperFlow Core 服务。", no_args_is_help=True)
app.add_typer(schedule_app, name="schedule")
app.add_typer(migrate_app, name="migrate")
app.add_typer(config_app, name="config")
app.add_typer(paths_app, name="paths")
app.add_typer(workspace_app, name="workspace")
app.add_typer(ai_app, name="ai")
app.add_typer(integration_app, name="integration")
app.add_typer(publish_app, name="publish")
app.add_typer(source_app, name="source")
app.add_typer(update_app, name="update")
app.add_typer(paper_app, name="paper")
app.add_typer(templates_app, name="templates")
app.add_typer(zotero_app, name="zotero")
zotero_app.add_typer(zotero_service_app, name="service")
attach_zotero_commands(zotero_app)

from paperflow.cli_features import attach_feature_apps

attach_feature_apps(app, integration_app, migrate_app, workspace_app)


@app.callback()
def application_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="显示 PaperFlow 应用版本。",
        is_eager=True,
    ),
):
    if version:
        typer.echo(APPLICATION_VERSION)
        raise typer.Exit()

def cfg(vault: Path | None = None):
    value = load_config(vault); ensure_layout(value); return value


def _root(vault: Path | None) -> Path:
    return resolve_vault_root(vault)


def _service_root(vault: Path | None, core_root: Path | None) -> Path:
    """Resolve a Vault or a standalone Core data root without guessing.

    A standalone root is deliberately explicit: it must not look like an
    Obsidian Vault and PaperFlow never creates or migrates Zotero files from
    this option.  This keeps Zotero-only mode usable when Obsidian is absent.
    """
    if vault is not None and core_root is not None:
        raise typer.BadParameter("--vault and --data-root are mutually exclusive")
    if core_root is not None:
        resolved = core_root.expanduser().resolve()
        if (resolved / ".paperflow").exists():
            raise typer.BadParameter("--data-root must be a standalone Core directory, not a Vault")
        if not (resolved / "data").is_dir():
            raise typer.BadParameter("--data-root is not initialized; run `zotero data-root --apply` first")
        return resolved
    if vault is not None:
        return _root(vault)
    raise typer.BadParameter("provide either --vault or --data-root")


def _persist_zotero_environment(root: Path, report: dict[str, object]) -> str:
    target = root / ".paperflow/state/zotero-environment.json"
    atomic_json(target, report)
    return target.relative_to(root).as_posix()


def _echo_json(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@zotero_app.command("detect")
def zotero_detect(
    vault: Path | None = typer.Option(None, "--vault", help="可选的 PaperFlow Vault。"),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="将本地检测结果写入被 Git 忽略的状态目录。"),
    redacted: bool = typer.Option(False, "--redacted", help="隐藏本机路径，适合复制到公共审计报告。"),
):
    """只读检测 Zotero 安装、活动 Profile、自定义数据目录和 Local API。"""
    report = zotero_environment.detect_environment()
    persisted = ""
    if persist and vault is not None:
        persisted = _persist_zotero_environment(_root(vault), report)
    output = redact_environment(report) if redacted else report
    if persisted:
        output["persisted_state"] = persisted
    _echo_json(output)


@zotero_app.command("status")
def zotero_status(
    vault: Path | None = typer.Option(None, "--vault"),
    redacted: bool = typer.Option(False, "--redacted"),
):
    """显示当前 Zotero 连接状态；Zotero 未启动不被误报为数据库故障。"""
    report = zotero_environment.detect_environment()
    output = redact_environment(report) if redacted else report
    output["ready_for_read_only_integration"] = bool(
        report["zotero"]["installed"]
        and any(item["data_dir"]["sqlite"] for item in report["profiles"])
    )
    plugins = [item.get("paperflow_plugin", {}) for item in report.get("profiles", [])]
    output["paperflow_plugin"] = {
        "installed": any(bool(item.get("installed")) for item in plugins),
        "active": any(bool(item.get("active")) for item in plugins),
        "profile_count": sum(1 for item in plugins if item.get("installed")),
    }
    output["ready_for_plugin_integration"] = bool(
        report.get("local_api", {}).get("reachable")
        and output["paperflow_plugin"]["active"]
    )
    output["note"] = (
        "Local API is reachable; PaperFlow does not start or stop Zotero."
        if report.get("local_api", {}).get("reachable")
        else "Local API will become reachable after Zotero is started; PaperFlow does not start or stop Zotero."
    )
    _echo_json(output)


@zotero_app.command("doctor")
def zotero_doctor(
    vault: Path | None = typer.Option(None, "--vault"),
    redacted: bool = typer.Option(False, "--redacted"),
):
    """对 Zotero 集成前置条件做只读诊断，不写入 Zotero。"""
    report = zotero_environment.detect_environment()
    checks = {
        "installed": bool(report["zotero"]["installed"]),
        "profile_detected": bool(report["profiles"]),
        "data_directory_resolved": any(
            item["data_dir"]["exists"] and item["data_dir"]["sqlite"] and item["data_dir"]["storage"]
            for item in report["profiles"]
        ),
        "single_active_profile": report["active_profile_count"] == 1,
        "api_loopback_only": report["safety"]["network_scope"] == "loopback-only",
        "database_untouched": not report["safety"]["database_modified"] and not report["safety"]["database_read"],
    }
    output = redact_environment(report) if redacted else report
    output["checks"] = checks
    plugins = [item.get("paperflow_plugin", {}) for item in report.get("profiles", [])]
    output["paperflow_plugin"] = {
        "installed": any(bool(item.get("installed")) for item in plugins),
        "active": any(bool(item.get("active")) for item in plugins),
        "profile_count": sum(1 for item in plugins if item.get("installed")),
    }
    output["ready_for_plugin_integration"] = bool(
        report.get("local_api", {}).get("reachable")
        and output["paperflow_plugin"]["active"]
    )
    output["ok"] = all(checks.values())
    _echo_json(output)
    if not output["ok"]:
        raise typer.Exit(1)


def _pid_alive(pid: object) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _is_core_service_pid(pid: object, root: Path) -> bool:
    """Verify a session PID command line before sending it a stop signal."""
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name != "nt":
        return _pid_alive(value)
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={value}\").CommandLine",
            ],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    command_line = completed.stdout.decode("utf-8", errors="replace")
    return (
        "paperflow.cli zotero service serve" in command_line
        and str(root) in command_line
    )


@zotero_service_app.command("serve")
def zotero_service_serve(
    vault: Path | None = typer.Option(None, "--vault"),
    core_root: Path | None = typer.Option(None, "--data-root"),
    port: int | None = typer.Option(None, "--port", min=1024, max=65535),
):
    """在前台运行 loopback-only Core 服务；供 `service start` 使用。"""
    root = _service_root(vault, core_root)
    if port is None and (root / ".paperflow/workspace.yaml").is_file():
        _, settings = load_workspace_settings(root)
        port = settings.zotero.environment.core_service_port
    port = port or 23140
    service = PaperFlowCoreService(root, port=port)
    service.start(background=False)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        service.stop()


@zotero_service_app.command("start")
def zotero_service_start(
    vault: Path | None = typer.Option(None, "--vault"),
    core_root: Path | None = typer.Option(None, "--data-root"),
    port: int | None = typer.Option(None, "--port", min=1024, max=65535),
):
    """启动后台 Core 服务；只创建随机会话令牌，不接受命令执行。"""
    root = _service_root(vault, core_root)
    if port is None and (root / ".paperflow/workspace.yaml").is_file():
        _, settings = load_workspace_settings(root)
        port = settings.zotero.environment.core_service_port
    port = port or 23140
    session_path = state_root(root) / "zotero-core-session.json"
    existing = read_session(root)
    if existing and _pid_alive(existing.get("pid")):
        _echo_json({"status": "already-running", "session_state": session_path.relative_to(root).as_posix()})
        return
    if existing:
        session_path.unlink(missing_ok=True)
    flag = "--data-root" if core_root is not None else "--vault"
    command = [
        sys.executable,
        "-m",
        "paperflow.cli",
        "zotero",
        "service",
        "serve",
        flag,
        str(root),
        "--port",
        str(port),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    runtime = runtime_root(root)
    runtime.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=(runtime / "zotero-core-service.out.log").open("ab"),
        stderr=(runtime / "zotero-core-service.err.log").open("ab"),
        creationflags=creationflags,
        close_fds=os.name != "nt",
    )
    session = None
    for _ in range(50):
        time.sleep(0.1)
        session = read_session(root)
        if not session or not session.get("base_url"):
            continue
        try:
            with urllib.request.urlopen(session["base_url"] + "/health", timeout=0.25):
                break
        except (OSError, urllib.error.URLError):
            continue
    if not session:
        if process.poll() is None:
            process.terminate()
        raise typer.BadParameter(
            f"Core service did not publish a live session; inspect {runtime.relative_to(root).as_posix()}/zotero-core-service.err.log"
        )
    _echo_json({"status": "started", "pid": session.get("pid"), "base_url": session.get("base_url"), "session_state": session_path.relative_to(root).as_posix(), "root_mode": "standalone" if core_root is not None else "vault"})


@zotero_service_app.command("status")
def zotero_service_status(
    vault: Path | None = typer.Option(None, "--vault"),
    core_root: Path | None = typer.Option(None, "--data-root"),
):
    root = _service_root(vault, core_root)
    session = read_session(root)
    if not session:
        _echo_json({"status": "stopped", "session_state": (state_root(root) / "zotero-core-session.json").relative_to(root).as_posix()})
        return
    verified = _is_core_service_pid(session.get("pid"), root)
    running = _pid_alive(session.get("pid"))
    state = "running" if verified else ("manual-review" if running else "stale")
    _echo_json({"status": state, "pid": session.get("pid"), "base_url": session.get("base_url"), "network_scope": "loopback-only"})


@zotero_service_app.command("token")
def zotero_service_token(
    vault: Path | None = typer.Option(None, "--vault"),
    core_root: Path | None = typer.Option(None, "--data-root"),
):
    """显示当前 Core 会话令牌，供用户手动粘贴到 Zotero 插件。

    令牌仅存在于被忽略的 runtime 文件；本命令不会写入日志或 Vault 文档。
    """
    root = _service_root(vault, core_root)
    session = read_session(root)
    token = read_pairing_token(root)
    if not session or not token or not _is_core_service_pid(session.get("pid"), root):
        _echo_json({"status": "unavailable", "reason": "Core is not running"})
        raise typer.Exit(1)
    _echo_json({
        "status": "available",
        "base_url": session.get("base_url"),
        "token": token,
        "warning": "只粘贴到 Zotero 本机偏好设置，不要提交或同步此令牌。",
    })


@zotero_service_app.command("stop")
def zotero_service_stop(
    vault: Path | None = typer.Option(None, "--vault"),
    core_root: Path | None = typer.Option(None, "--data-root"),
):
    root = _service_root(vault, core_root)
    session = read_session(root)
    if not session:
        _echo_json({"status": "already-stopped"})
        return
    if not _is_core_service_pid(session.get("pid"), root):
        if not _pid_alive(session.get("pid")):
            (state_root(root) / "zotero-core-session.json").unlink(missing_ok=True)
            _echo_json({"status": "stale-session-removed"})
            return
        _echo_json({"status": "manual-review-required", "reason": "session PID command line was not verified as PaperFlow Core; no process was stopped"})
        raise typer.Exit(2)
    try:
        os.kill(int(session["pid"]), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        (state_root(root) / "zotero-core-session.json").unlink(missing_ok=True)
        _echo_json({"status": "stale-session-removed"})
        return
    stopped = False
    for _ in range(30):
        time.sleep(0.1)
        if not _is_core_service_pid(session.get("pid"), root):
            stopped = True
            break
    if stopped:
        (state_root(root) / "zotero-core-session.json").unlink(missing_ok=True)
        (runtime_root(root) / "zotero-core-session.token").unlink(missing_ok=True)
        _echo_json({"status": "stopped", "pid": session["pid"]})
        return
    _echo_json({"status": "stop-requested", "pid": session["pid"]})


@zotero_app.command("collections")
def zotero_collections(vault: Path = typer.Option(..., "--vault")):
    """显示配置的 PaperFlow Collection；不访问 Zotero 数据库。"""
    _, settings = load_workspace_settings(vault)
    primary = settings.zotero.collections.primary
    _echo_json({
        "enabled": settings.zotero.enabled and settings.integrations.zotero.enabled,
        "primary": primary.model_dump(mode="json"),
        "source": "workspace configuration",
        "zotero_write": "plugin-api-only",
    })


@zotero_app.command("ensure-collection")
def zotero_ensure_collection(
    vault: Path = typer.Option(..., "--vault"),
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
):
    """生成 Collection 计划；实际创建必须由 Zotero 插件公开 API 执行。"""
    _, settings = load_workspace_settings(vault)
    primary = settings.zotero.collections.primary
    result = {
        "dry_run": not apply_changes,
        "status": "plugin-required",
        "collection": primary.model_dump(mode="json"),
        "database_access": False,
        "reason": "PaperFlow Core never writes zotero.sqlite; the Zotero plugin must create/reuse the Collection.",
    }
    _echo_json(result)
    if apply_changes:
        raise typer.Exit(2)


@zotero_app.command("link")
def zotero_link(
    items_json: Path = typer.Option(..., "--items-json", exists=True, readable=True),
    vault: Path = typer.Option(..., "--vault"),
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
):
    """用 Zotero 插件/API 导出的 JSON 规划论文身份映射，不直接读数据库。"""
    items = load_items(items_json)
    plan = plan_links(_root(vault), items)
    _echo_json(apply_links(_root(vault), plan) if apply_changes else plan)


@zotero_app.command("unlink")
def zotero_unlink(
    paper_uid: str,
    vault: Path = typer.Option(..., "--vault"),
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
):
    root = _root(vault)
    from paperflow.paths.templates import safe_component

    path = root / ".paperflow/data/connectors/zotero/mappings" / f"{safe_component(paper_uid.replace(':', '_'))}.json"
    result = {"paper_uid": paper_uid, "path": path.relative_to(root).as_posix(), "dry_run": not apply_changes, "exists": path.exists()}
    if apply_changes and path.exists():
        path.unlink()
        result["status"] = "unlinked"
    else:
        result["status"] = "would-unlink" if path.exists() else "already-unlinked"
    _echo_json(result)


@app.command("init")
def init_command(
    vault: Path | None = typer.Option(None, "--vault", help="目标 Obsidian Vault。"),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
    config_file: Path | None = typer.Option(None, "--config", help="初始化配置覆盖文件。"),
):
    """在任意 Vault 中创建独立 PaperFlow Workspace；不会读取 AI 凭证。"""
    target = vault
    if target is None and not non_interactive:
        target = Path(typer.prompt("Obsidian Vault path"))
    if target is None:
        raise typer.BadParameter("--vault is required with --non-interactive")
    overrides = None
    if not non_interactive and config_file is None:
        timezone = typer.prompt("Timezone", default="Asia/Shanghai")
        language = typer.prompt("Language (auto/zh-CN/en)", default="auto")
        research = typer.prompt(
            "Research profile", default="embodied-intelligence"
        )
        provider = typer.prompt(
            "AI provider (codex/claude/mock)", default="codex"
        )
        model = typer.prompt(
            "AI model (blank uses the CLI default)", default="", show_default=False
        )
        layout = typer.prompt(
            "Path layout (default/topic)", default="default"
        )
        install_form = typer.confirm("Install Form Flow integration files?", default=True)
        create_bases = typer.confirm("Create Obsidian Bases?", default=True)
        daily_automation = typer.confirm(
            "Enable Obsidian daily automation?", default=True
        )
        feed_url = typer.prompt(
            "Public Feed URL (blank to skip)", default="", show_default=False
        )
        download_pdf = typer.confirm("Download missing PDFs?", default=True)
        allow_fallback = typer.confirm(
            "Allow local AI fallback profile?", default=True
        )
        note_template = (
            "{{year}}/{{primary_topic|slug}}/{{paper_id}}.md"
            if layout == "topic"
            else "{{year}}/{{paper_id}}.md"
        )
        overrides = {
            "timezone": timezone,
            "language": language,
            "research_profile": research,
            "paths": {"note": {"template": note_template}},
            "ai": {
                "profiles": {
                    "full_analysis": {
                        "provider": provider,
                        "model": model,
                        "fallback_profile": (
                            "fallback_analysis" if allow_fallback else ""
                        ),
                    }
                }
            },
            "obsidian": {
                "install_form_flow": install_form,
                "create_bases": create_bases,
                "enable_daily_automation": daily_automation,
            },
            "downloads": {"enabled": download_pdf},
            "subscriptions": {
                "sources": (
                    [
                        {
                            "name": "community-feed",
                            "url": feed_url,
                            "branch": "main",
                            "enabled": True,
                            "trust": "metadata-and-ai",
                            "priority": 50,
                            "auto_download_pdf": download_pdf,
                            "auto_render_notes": True,
                        }
                    ]
                    if feed_url
                    else []
                )
            },
        }
    path = init_workspace(
        target, config_file=config_file, overrides=overrides
    )
    root, settings = load_workspace_settings(target)
    resources = install_workspace_resources(root, settings)
    form_flow = {"status": "not-requested"}
    if settings.obsidian.install_form_flow:
        plugin = form_flow_status(root)["plugin"]
        attempted = None
        if not plugin["installed"]:
            attempted = try_install_official_plugin(root)
            plugin = form_flow_status(root)["plugin"]
        form_flow = (
            install_form_flow(root, mode="install")
            if plugin["installed"] and plugin["compatible"]
            else {
                "status": "plugin-required",
                "plugin_id": "form-flow",
                "minimum_version": "0.0.8",
                "automatic_install": attempted,
            }
        )
    typer.echo(
        json.dumps(
            {
                "workspace": str(path),
                "resources": resources,
                "form_flow": form_flow,
                "credentials_read": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


@config_app.command("show")
def config_show(
    vault: Path | None = typer.Option(None, "--vault"),
    resolved: bool = typer.Option(False, "--resolved"),
):
    """显示配置；resolved 模式应用 local、环境变量和 CLI 分层。"""
    root, settings = load_workspace_settings(vault)
    if not resolved:
        workspace_file = root / ".paperflow/workspace.yaml"
        local_file = root / ".paperflow/workspace.local.yaml"
        value = {
            "workspace": YAML(typ="safe").load(
                workspace_file.read_text(encoding="utf-8")
            ),
            "local": (
                YAML(typ="safe").load(local_file.read_text(encoding="utf-8"))
                if local_file.exists()
                else {}
            ),
        }
    else:
        value = settings.model_dump(mode="json")
    typer.echo(
        json.dumps(
            {
                "vault": str(root),
                "resolved": resolved,
                "config": value,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@config_app.command("validate")
def config_validate(vault: Path | None = typer.Option(None, "--vault")):
    """验证全部配置字段并给出定位明确的错误。"""
    root, settings = load_workspace_settings(vault)
    errors = validate_path_settings(root, settings)
    if errors:
        for error in errors:
            typer.echo(f"ERROR {error}")
        raise typer.Exit(1)
    typer.echo("OK")


def _local_config(root: Path) -> tuple[Path, dict]:
    path = root / ".paperflow/workspace.local.yaml"
    value = (
        YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
        if path.exists()
        else {}
    )
    return path, value


def _config_parts(key: str) -> list[str]:
    parts = [part for part in key.split(".") if part]
    if not parts:
        raise typer.BadParameter("Configuration key cannot be empty")
    if any(
        fragment in part.casefold()
        for part in parts
        for fragment in ["token", "password", "cookie", "secret", "api_key"]
    ):
        raise typer.BadParameter(
            "Plaintext credentials are forbidden in PaperFlow config."
        )
    return parts


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    path, local = _local_config(root)
    cursor = local
    parts = _config_parts(key)
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
        if not isinstance(cursor, dict):
            raise typer.BadParameter(f"{key}: parent is not a mapping")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    cursor[parts[-1]] = parsed
    dump_yaml(path, local)
    try:
        load_workspace_settings(root)
    except Exception:
        cursor.pop(parts[-1], None)
        dump_yaml(path, local)
        raise
    typer.echo(key)


@config_app.command("unset")
def config_unset(
    key: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    path, local = _local_config(root)
    cursor = local
    parts = _config_parts(key)
    for part in parts[:-1]:
        value = cursor.get(part)
        if not isinstance(value, dict):
            typer.echo(key)
            return
        cursor = value
    cursor.pop(parts[-1], None)
    dump_yaml(path, local)
    load_workspace_settings(root)
    typer.echo(key)


@config_app.command("export-example")
def config_export_example(output: Path):
    typer.echo(str(export_example(output)))


@config_app.command("edit")
def config_edit(vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    path = root / ".paperflow/workspace.local.yaml"
    editor = os.environ.get("EDITOR")
    if not editor:
        typer.echo(str(path))
        return
    result = subprocess.run([editor, str(path)])
    if result.returncode:
        raise typer.Exit(result.returncode)
    load_workspace_settings(root)


@config_app.command("doctor")
def config_doctor(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    errors = validate_path_settings(root, settings)
    typer.echo(
        json.dumps(
            {
                "valid": not errors,
                "errors": errors,
                "providers": capability_summary(root, settings.ai.providers),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise typer.Exit(1)


@paths_app.command("variables")
def paths_variables():
    """列出路径模板允许使用的变量。"""
    typer.echo(json.dumps(variables_documentation(), ensure_ascii=False, indent=2))


@paths_app.command("preview")
def paths_preview(
    paper_uid: str | None = typer.Argument(None),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """预览旧路径、新路径、冲突和 AI 字段依赖。"""
    root, settings = load_workspace_settings(vault)
    records = preview_all(root, settings)
    if paper_uid:
        records = [item for item in records if item["paper_uid"] == paper_uid]
        if not records:
            raise typer.BadParameter(f"Unknown paper_uid: {paper_uid}")
    typer.echo(json.dumps(records, ensure_ascii=False, indent=2))


@paths_app.command("validate")
def paths_validate(vault: Path | None = typer.Option(None, "--vault")):
    """验证所有路径根和模板都保持在 Vault 内。"""
    root, settings = load_workspace_settings(vault)
    errors = validate_path_settings(root, settings)
    if errors:
        typer.echo("\n".join(errors))
        raise typer.Exit(1)
    typer.echo("OK")


@paths_app.command("migrate")
def paths_migrate(
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """通过正式迁移引擎预览或应用路径/数据布局变更。"""
    root, settings = load_workspace_settings(vault)
    result = migrate_paths(root, settings, dry_run=dry_run)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@migrate_app.command("status")
def migrate_status_command(vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(migration_status(_root(vault)), ensure_ascii=False, indent=2))


@migrate_app.command("plan")
def migrate_plan_command(
    to_version: int | None = typer.Option(None, "--to"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(
        json.dumps(
            build_migration_plan(_root(vault), to_version),
            ensure_ascii=False,
            indent=2,
        )
    )


@migrate_app.command("apply")
def migrate_apply_command(
    to_version: int | None = typer.Option(None, "--to"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(
        json.dumps(
            apply_migration(_root(vault), to_version),
            ensure_ascii=False,
            indent=2,
        )
    )


@migrate_app.command("verify")
def migrate_verify_command(vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(verify_migration(_root(vault)), ensure_ascii=False, indent=2))


@migrate_app.command("rollback")
def migrate_rollback_command(
    migration_id: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(
        json.dumps(
            rollback_migration(_root(vault), migration_id),
            ensure_ascii=False,
            indent=2,
        )
    )


@migrate_app.command("history")
def migrate_history_command(vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(migration_history(_root(vault)), ensure_ascii=False, indent=2))


@migrate_app.command("user-notes")
def migrate_user_notes_command(
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """迁移主论文中的 USER_NOTES 到独立 User Note（默认只预览）。"""
    root, settings = load_workspace_settings(vault)
    result = apply_user_note_migration(root, settings) if apply_changes else plan_user_note_migration(root, settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@migrate_app.command("redirect-labels")
def migrate_redirect_labels_command(
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """为旧论文路径兼容桩补充可读标题；不会覆盖用户改写的桩。"""
    root = _root(vault)
    result = apply_redirect_labels(root) if apply_changes else plan_redirect_labels(root)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@templates_app.command("list")
def templates_list(vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    typer.echo(json.dumps(TemplateSetManager(root).list(), ensure_ascii=False, indent=2))


@templates_app.command("show")
def templates_show(set_id: str, vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    manager = TemplateSetManager(root)
    items = [item for item in manager.list() if item.get("id") == set_id]
    if not items:
        raise typer.BadParameter(f"Unknown template set: {set_id}")
    typer.echo(json.dumps(items[0], ensure_ascii=False, indent=2))


@templates_app.command("use")
def templates_use(set_id: str, vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(TemplateSetManager(_root(vault)).use(set_id), ensure_ascii=False, indent=2))


@templates_app.command("copy")
def templates_copy(set_id: str, destination: str = typer.Option("", "--destination"), vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(TemplateSetManager(_root(vault)).copy(set_id, destination or None), ensure_ascii=False, indent=2))


@templates_app.command("validate")
def templates_validate(set_id: str | None = typer.Argument(None), vault: Path | None = typer.Option(None, "--vault")):
    result = TemplateSetManager(_root(vault)).validate(set_id)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise typer.Exit(1)


@templates_app.command("export")
def templates_export(set_id: str, output: Path, vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(str(TemplateSetManager(_root(vault)).export(set_id, output)))


@templates_app.command("import")
def templates_import(archive: Path, name: str = typer.Option("", "--name"), vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(TemplateSetManager(_root(vault)).import_zip(archive, name or None), ensure_ascii=False, indent=2))


@templates_app.command("doctor")
def templates_doctor(vault: Path | None = typer.Option(None, "--vault")):
    result = TemplateSetManager(_root(vault)).doctor()
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise typer.Exit(1)


@templates_app.command("diff")
def templates_diff(left: str, right: str, vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(json.dumps(TemplateSetManager(_root(vault)).diff(left, right), ensure_ascii=False, indent=2))


@templates_app.command("preview")
def templates_preview(
    set_id: str,
    template_name: str = typer.Option("Paper Hub.md", "--template"),
    paper_uid: str = typer.Option("", "--paper-uid"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    candidates = list((root / ".paperflow/data/papers").glob(f"{paper_uid.replace(':', '_')}.json")) if paper_uid else []
    if not candidates:
        raise typer.BadParameter("--paper-uid must reference a local paper")
    record = json.loads(candidates[0].read_text(encoding="utf-8"))
    record["_settings"] = settings
    typer.echo(TemplateSetManager(root).preview(set_id, template_name, record))


@migrate_app.command("workspace-v2")
def migrate_workspace_v2_command(
    apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """升级到 PaperFlow 1.4 Workspace schema 2，并安全重渲染生成笔记。"""
    root = _root(vault)
    result = (
        apply_workspace_v2(root)
        if apply_changes
        else plan_workspace_v2(root)
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@migrate_app.command("verify-workspace-v2")
def verify_workspace_v2_command(
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(
        json.dumps(
            verify_workspace_v2(_root(vault)),
            ensure_ascii=False,
            indent=2,
        )
    )


@workspace_app.command("info")
def workspace_info(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            {
                "vault": str(root),
                "workspace_name": settings.workspace_name,
                "versions": settings.versions.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@workspace_app.command("validate")
def workspace_validate(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    errors = validate_path_settings(root, settings)
    if errors:
        typer.echo("\n".join(errors))
        raise typer.Exit(1)
    typer.echo("OK")


@workspace_app.command("backup")
def workspace_backup(vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    destination = create_workspace_backup(root)
    typer.echo(str(destination))


@workspace_app.command("repair")
def workspace_repair(
    dry_run: bool = typer.Option(False, "--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "dry_run": True,
                    "configured_roots": [
                        value["root"]
                        for value in settings.paths.model_dump(mode="json").values()
                    ],
                    "form_flow": form_flow_status(root),
                    "automation_enabled": settings.obsidian.enable_daily_automation,
                    "changes_applied": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    ensure_layout(load_config(root))
    result = install_workspace_resources(root, settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@workspace_app.command("rebuild-index")
def workspace_rebuild_index():
    rebuild_index()


@workspace_app.command("export-user-data")
def workspace_export_user_data(
    output: Path,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    typer.echo(str(export_user_data(root, settings, output)))


@workspace_app.command("import-user-data")
def workspace_import_user_data(
    source: Path,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    backup = create_workspace_backup(root, label="pre-user-import")
    result = import_user_data(root, settings, source)
    result["backup"] = str(backup)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@ai_app.command("providers")
def ai_providers(vault: Path | None = typer.Option(None, "--vault")):
    """探测真实 CLI 版本和分析子命令能力，不读取任何凭证文件。"""
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            capability_summary(root, settings.ai.providers),
            ensure_ascii=False,
            indent=2,
        )
    )


@ai_app.command("profiles")
def ai_profiles(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    del root
    typer.echo(
        json.dumps(
            {
                name: explain_profile(
                    name, settings.ai.profiles, settings.ai.providers
                )
                for name in settings.ai.profiles
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@ai_app.command("test")
def ai_test(
    profile: str = typer.Option("full_analysis", "--profile"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """只做 Provider 可用性和配置检查，不发送论文内容。"""
    root, settings = load_workspace_settings(vault)
    if profile not in settings.ai.profiles:
        raise typer.BadParameter(f"Unknown AI profile: {profile}")
    selected = settings.ai.profiles[profile]
    provider = make_provider(
        selected.provider, root, settings.ai.providers[selected.provider]
    )
    provider.validate_config()
    typer.echo(
        json.dumps(
            {
                "selection": explain_profile(
                    profile, settings.ai.profiles, settings.ai.providers
                ),
                "capability": provider.check_available().__dict__,
                "credentials_read": False,
                "paper_content_sent": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@ai_app.command("configure")
def ai_configure(
    provider: str | None = typer.Argument(None),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """交互配置本机 provider/model/profile；不询问或保存凭证。"""
    root, settings = load_workspace_settings(vault)
    selected = provider or typer.prompt(
        "Provider (codex/claude/mock)",
        default=settings.ai.profiles[settings.ai.full_analysis_profile].provider,
    )
    if selected not in settings.ai.providers:
        raise typer.BadParameter(f"Unknown provider: {selected}")
    current = settings.ai.providers[selected]
    model = typer.prompt(
        "Model (blank uses CLI default)",
        default=current.model,
        show_default=bool(current.model),
    )
    timeout = typer.prompt(
        "Full-analysis timeout seconds",
        default=settings.ai.profiles[
            settings.ai.full_analysis_profile
        ].timeout_seconds,
        type=int,
    )
    allow_fallback = typer.confirm("Allow fallback profile?", default=True)
    path, local = _local_config(root)
    ai = local.setdefault("ai", {})
    ai.setdefault("providers", {}).setdefault(selected, {})["model"] = model
    full = ai.setdefault("profiles", {}).setdefault(
        settings.ai.full_analysis_profile, {}
    )
    full.update(
        {
            "provider": selected,
            "model": model,
            "timeout_seconds": timeout,
            "fallback_profile": (
                "fallback_analysis" if allow_fallback else ""
            ),
        }
    )
    dump_yaml(path, local)
    load_workspace_settings(root)
    typer.echo(
        json.dumps(
            {
                "provider": selected,
                "model": model or "<cli-default>",
                "credentials_read": False,
            },
            ensure_ascii=False,
        )
    )
@ai_app.command("explain-selection")
def ai_explain_selection(
    paper_uid: str,
    profile: str = typer.Option("full_analysis", "--profile"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    del root
    result = explain_profile(profile, settings.ai.profiles, settings.ai.providers)
    result["paper_uid"] = paper_uid
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@ai_app.command("set-profile")
def ai_set_profile(
    profile: str,
    provider: str = typer.Option(..., "--provider"),
    model: str = typer.Option("", "--model"),
    timeout_seconds: int = typer.Option(
        1800, "--timeout", min=1, max=14400
    ),
    reasoning_effort: str = typer.Option("", "--reasoning-effort"),
    fallback: bool = typer.Option(False, "--fallback/--no-fallback"),
    reuse_feed_analysis: bool = typer.Option(
        True, "--reuse-feed/--no-reuse-feed"
    ),
    reanalyze_when: str = typer.Option(
        "identity-changed", "--reanalyze-when"
    ),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """原子更新一个 AI profile，供 Obsidian 等非交互界面调用。"""
    root, settings = load_workspace_settings(vault)
    if profile not in settings.ai.profiles:
        raise typer.BadParameter(f"Unknown AI profile: {profile}")
    if provider not in settings.ai.providers:
        raise typer.BadParameter(f"Unknown AI provider: {provider}")
    if reanalyze_when not in {"identity-changed", "never", "always"}:
        raise typer.BadParameter(
            "reanalyze_when must be identity-changed, never, or always"
        )
    if reasoning_effort not in {"", "low", "medium", "high", "xhigh", "max"}:
        raise typer.BadParameter(
            "reasoning_effort must be low, medium, high, xhigh, max, or empty"
        )
    path, local = _local_config(root)
    existed = path.exists()
    previous = path.read_bytes() if existed else b""
    selected = (
        local.setdefault("ai", {})
        .setdefault("profiles", {})
        .setdefault(profile, {})
    )
    selected.update(
        {
            "provider": provider,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "reasoning_effort": reasoning_effort,
            "fallback_profile": (
                "fallback_analysis"
                if fallback and profile != "fallback_analysis"
                else ""
            ),
            "reuse_feed_analysis": reuse_feed_analysis,
            "reanalyze_when": reanalyze_when,
        }
    )
    dump_yaml(path, local)
    try:
        _, resolved = load_workspace_settings(root)
    except Exception:
        if existed:
            path.write_bytes(previous)
        else:
            path.unlink(missing_ok=True)
        raise
    typer.echo(
        json.dumps(
            {
                "profile": profile,
                "config": resolved.ai.profiles[profile].model_dump(
                    mode="json"
                ),
                "credentials_read": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@ai_app.command("web-consent")
def ai_web_consent(
    allow_pdf_upload: bool = typer.Option(
        ..., "--allow-pdf-upload/--deny-pdf-upload"
    ),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """保存 ChatGPT 网页 PDF 外部上传许可，不保存账号或凭证。"""
    root, _ = load_workspace_settings(vault)
    path, local = _local_config(root)
    provider = (
        local.setdefault("ai", {})
        .setdefault("providers", {})
        .setdefault("chatgpt-web", {})
    )
    provider["allow_pdf_upload"] = allow_pdf_upload
    dump_yaml(path, local)
    _, resolved = load_workspace_settings(root)
    typer.echo(
        json.dumps(
            {
                "provider": "chatgpt-web",
                "allow_pdf_upload": resolved.ai.providers[
                    "chatgpt-web"
                ].allow_pdf_upload,
                "credentials_saved": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@integration_app.command("list")
def integration_list(vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    typer.echo(
        json.dumps(
            [{"name": "form-flow", "status": form_flow_status(root)}],
            ensure_ascii=False,
            indent=2,
        )
    )


def _require_form_flow(name: str) -> None:
    if name not in {"form-flow", "form_flow"}:
        raise typer.BadParameter(f"Unknown integration: {name}")


@integration_app.command("status")
def integration_status_command(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _require_form_flow(name)
    typer.echo(json.dumps(form_flow_status(_root(vault)), ensure_ascii=False, indent=2))


@integration_app.command("install")
def integration_install(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _require_form_flow(name)
    root = _root(vault)
    attempted = None
    if not form_flow_status(root)["plugin"]["installed"]:
        attempted = try_install_official_plugin(root)
    if not form_flow_status(root)["plugin"]["installed"]:
        typer.echo(
            json.dumps(
                {
                    "status": "plugin-required",
                    "automatic_install": attempted,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(1)
    typer.echo(
        json.dumps(
            install_form_flow(root, mode="install"),
            ensure_ascii=False,
            indent=2,
        )
    )


@integration_app.command("repair")
def integration_repair(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _require_form_flow(name)
    typer.echo(
        json.dumps(
            install_form_flow(_root(vault), mode="repair"),
            ensure_ascii=False,
            indent=2,
        )
    )


@integration_app.command("upgrade")
def integration_upgrade(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _require_form_flow(name)
    typer.echo(
        json.dumps(
            install_form_flow(_root(vault), mode="upgrade"),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("plan")
def publish_plan_command(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    typer.echo(json.dumps(publish_plan(root, settings), ensure_ascii=False, indent=2))


@publish_app.command("build")
def publish_build(
    output: Path | None = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """只生成本地 Feed；不执行 git commit 或 push。"""
    root, settings = load_workspace_settings(vault)
    if dry_run:
        typer.echo(
            json.dumps(publish_plan(root, settings), ensure_ascii=False, indent=2)
        )
        return
    typer.echo(
        json.dumps(
            build_feed(root, settings, output),
            ensure_ascii=False,
            indent=2,
        )
    )


def _feed_output(root: Path, output: Path | None) -> Path:
    return output or root / ".paperflow/publish/feed"


@publish_app.command("validate")
def publish_validate(
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    typer.echo(
        json.dumps(
            validate_feed(_feed_output(root, output)),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("scan")
def publish_scan(
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    findings = scan_feed(_feed_output(_root(vault), output))
    typer.echo(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    if findings:
        raise typer.Exit(1)


@publish_app.command("diff")
def publish_diff(
    candidate: Path,
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(
        json.dumps(
            feed_diff(_feed_output(_root(vault), output), candidate),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("status")
def publish_status(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    result = publish_plan(root, settings)
    output = _feed_output(root, None)
    result["built"] = (output / "feed.yaml").exists()
    if result["built"]:
        result["privacy_findings"] = scan_feed(output)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@publish_app.command("init")
def publish_init(vault: Path | None = typer.Option(None, "--vault")):
    root = _root(vault)
    output = root / ".paperflow/publish/feed"
    output.mkdir(parents=True, exist_ok=True)
    typer.echo(
        "Local Feed directory initialized. Configure publishing.feed_id, "
        "publishing.name, and publishing.data_license before build."
    )


@publish_app.command("git-init")
def publish_git_init(
    remote: str = typer.Option(
        ...,
        "--remote",
        help="目标 GitHub HTTPS 仓库；只写入本地 origin，不访问网络。",
    ),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            init_feed_repository(
                _feed_output(root, None),
                remote_url=remote,
                branch=settings.publishing.branch,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("configure")
def publish_configure(
    feed_id: str = typer.Option(..., "--feed-id"),
    name: str = typer.Option(..., "--name"),
    publisher_name: str = typer.Option(..., "--publisher-name"),
    data_license: str = typer.Option(..., "--data-license"),
    repository_url: str = typer.Option("", "--repository-url"),
    publisher_url: str = typer.Option("", "--publisher-url"),
    branch: str = typer.Option("main", "--branch"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """原子保存公共 Feed 元数据；不建远程仓库、不 commit、不 push。"""
    from urllib.parse import urlparse

    from paperflow.feed.git_ops import normalize_github_repository_url

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_."
    )
    if not feed_id or any(character not in allowed for character in feed_id):
        raise typer.BadParameter(
            "feed_id may contain only letters, numbers, dot, underscore, hyphen"
        )
    values = {
        "name": name,
        "publisher_name": publisher_name,
        "data_license": data_license,
        "branch": branch,
    }
    for label, value in values.items():
        if (
            not value.strip()
            or len(value) > 300
            or any(ord(character) < 32 for character in value)
        ):
            raise typer.BadParameter(f"Invalid {label}")
    normalized_repository = (
        normalize_github_repository_url(repository_url)
        if repository_url
        else ""
    )
    if publisher_url:
        parsed = urlparse(publisher_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise typer.BadParameter(
                "publisher_url must be a plain HTTPS URL without credentials, "
                "query, or fragment"
            )
    root, _ = load_workspace_settings(vault)
    path, local = _local_config(root)
    existed = path.exists()
    previous = path.read_bytes() if existed else b""
    local["publishing"] = {
        **local.get("publishing", {}),
        "enabled": True,
        "feed_id": feed_id,
        "name": name,
        "publisher_name": publisher_name,
        "publisher_url": publisher_url,
        "repository_url": normalized_repository,
        "branch": branch,
        "data_license": data_license,
        "pdf_policy": "link-only",
        "include_pdf_files": False,
    }
    dump_yaml(path, local)
    try:
        _, resolved = load_workspace_settings(root)
    except Exception:
        if existed:
            path.write_bytes(previous)
        else:
            path.unlink(missing_ok=True)
        raise
    typer.echo(
        json.dumps(
            {
                "publishing": resolved.publishing.model_dump(mode="json"),
                "remote_repository_created": False,
                "network_contacted": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("git-status")
def publish_git_status(
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    typer.echo(
        json.dumps(
            feed_git_status(_feed_output(root, None)),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("commit")
def publish_commit(
    message: str = typer.Option("Update PaperFlow Feed", "--message"),
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _feed_output(_root(vault), output)
    validate_feed(root)
    findings = scan_feed(root)
    if findings:
        raise typer.BadParameter(f"Privacy scan failed: {findings}")
    if not (root / ".git").exists():
        raise typer.BadParameter(
            "Feed output is not a Git repository. Keep it separate from the "
            "PaperFlow program repository."
        )
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    result = subprocess.run(
        ["git", "-C", str(root), "commit", "-m", message],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    typer.echo(result.stdout or result.stderr)
    if result.returncode:
        raise typer.Exit(result.returncode)


@publish_app.command("push")
def publish_push(
    confirm: bool = typer.Option(
        False, "--confirm", help="确认向已配置的远程仓库 push。"
    ),
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    if not confirm:
        raise typer.BadParameter(
            "Use --confirm after reviewing publish validate and publish scan."
        )
    root, settings = load_workspace_settings(vault)
    feed_root = _feed_output(root, output)
    validate_feed(feed_root)
    findings = scan_feed(feed_root)
    if findings:
        raise typer.BadParameter(f"Privacy scan failed: {findings}")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(feed_root),
            "push",
            "origin",
            settings.publishing.branch,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    typer.echo(result.stdout or result.stderr)
    if result.returncode:
        raise typer.Exit(result.returncode)


@publish_app.command("snapshot")
def publish_snapshot(
    output: Path | None = typer.Option(None, "--output"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    _, settings = load_workspace_settings(root)
    typer.echo(
        json.dumps(
            create_snapshot(
                _feed_output(root, output),
                timezone_name=settings.timezone,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@publish_app.command("auto")
def publish_auto(
    push: bool = typer.Option(False, "--push/--no-push"),
    confirm_automation: bool = typer.Option(False, "--confirm-automation"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    """构建、验证、隐私扫描，并在持久授权后提交/推送固定 Feed。"""
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            auto_publish_feed(
                root,
                settings,
                push=push,
                confirmed_automation=confirm_automation,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def _subscription_by_name(settings, name: str):
    for source in settings.subscriptions.sources:
        if source.name == name:
            return source
    raise typer.BadParameter(f"Unknown source: {name}")


@source_app.command("list")
def source_list(vault: Path | None = typer.Option(None, "--vault")):
    _, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            settings.subscriptions.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


def _write_local_subscriptions(root: Path, sources: list[dict]) -> None:
    local_path = root / ".paperflow/workspace.local.yaml"
    local = {}
    if local_path.exists():
        local = YAML(typ="safe").load(local_path.read_text(encoding="utf-8")) or {}
    local["subscriptions"] = {"sources": sources}
    dump_yaml(local_path, local)
    load_workspace_settings(root)


@source_app.command("add")
def source_add(
    url: str,
    name: str = typer.Option("", "--name"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    source_name = name or Path(url.rstrip("/")).stem or "community-feed"
    if any(item.name == source_name for item in settings.subscriptions.sources):
        raise typer.BadParameter(f"Source already exists: {source_name}")
    sources = [
        item.model_dump(mode="json") for item in settings.subscriptions.sources
    ]
    sources.append(
        {
            "name": source_name,
            "url": url,
            "branch": "main",
            "enabled": True,
            "trust": "metadata-and-ai",
            "priority": 50,
            "auto_download_pdf": True,
            "auto_render_notes": True,
        }
    )
    _write_local_subscriptions(root, sources)
    typer.echo(source_name)


def _mutate_source(root: Path, settings, name: str, operation: str) -> None:
    sources = [
        item.model_dump(mode="json") for item in settings.subscriptions.sources
    ]
    found = False
    result = []
    for item in sources:
        if item["name"] != name:
            result.append(item)
            continue
        found = True
        if operation == "remove":
            continue
        if operation == "disable":
            item["enabled"] = False
            item["trust"] = "disabled"
        elif operation in {"metadata-only", "metadata-and-ai", "disabled"}:
            item["trust"] = operation
            item["enabled"] = operation != "disabled"
        result.append(item)
    if not found:
        raise typer.BadParameter(f"Unknown source: {name}")
    _write_local_subscriptions(root, result)


@source_app.command("disable")
def source_disable(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    _mutate_source(root, settings, name, "disable")
    typer.echo(name)


@source_app.command("remove")
def source_remove(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    _mutate_source(root, settings, name, "remove")
    typer.echo(name)


@source_app.command("trust")
def source_trust(
    name: str,
    mode: str = typer.Argument("metadata-and-ai"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    _mutate_source(root, settings, name, mode)
    typer.echo(json.dumps({"name": name, "trust": mode}, ensure_ascii=False))


@source_app.command("inspect")
def source_inspect(
    name: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _, settings = load_workspace_settings(vault)
    source = _subscription_by_name(settings, name)
    typer.echo(
        json.dumps(
            inspect_feed(source.url, source.branch),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@source_app.command("sync")
def source_sync(
    name: str | None = typer.Argument(None),
    all_sources: bool = typer.Option(False, "--all"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = load_workspace_settings(vault)
    selected = (
        [item for item in settings.subscriptions.sources if item.enabled]
        if all_sources
        else [_subscription_by_name(settings, name or "")]
    )
    results = [
        sync_feed(
            root,
            url=item.url,
            name=item.name,
            branch=item.branch,
            trust=item.trust,
            dry_run=dry_run,
            auto_download_pdf=item.auto_download_pdf,
            auto_render_notes=item.auto_render_notes,
            capabilities=item.capabilities,
            community_note_root=settings.paths.community_note.root,
        )
        for item in selected
    ]
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))


@source_app.command("status")
def source_status(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            {
                "sources": len(settings.subscriptions.sources),
                "enabled": sum(item.enabled for item in settings.subscriptions.sources),
                "cached_records": len(
                    list((root / ".paperflow/data/raw/subscriptions").rglob("*.json"))
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@paper_app.command("view-model")
def paper_view_model(paper_uid: str, vault: Path | None = typer.Option(None, "--vault")):
    """输出稳定 Paper View Model，供模板调试和维护者验收。"""
    root, settings = load_workspace_settings(vault)
    safe_id = paper_uid.replace(":", "_")
    candidates = list((root / ".paperflow/data/papers").glob(f"{safe_id}.json"))
    if not candidates:
        candidates = list((root / ".paperflow/data/papers").glob(f"*{safe_id}*.json"))
    if not candidates:
        raise typer.BadParameter(f"Unknown paper_uid: {paper_uid}")
    record = json.loads(candidates[0].read_text(encoding="utf-8"))
    record["paper_uid"] = record.get("paper_uid") or paper_uid
    typer.echo(json.dumps(build_paper_view_model(root, settings, record), ensure_ascii=False, indent=2, default=str))


def _paper_add_impl(
    value: str,
    priority: int,
    topic: str,
    ai: bool,
    force_refresh: bool,
    provider: str | None,
    vault: Path | None,
) -> dict[str, Any]:
    return PaperApplicationService(vault).add_paper(
        value,
        priority=priority,
        topic=topic,
        run_ai=ai,
        force_refresh=force_refresh,
        provider=provider,
    )


def _paper_analyze_impl(
    paper_uid: str,
    provider: str | None,
    vault: Path | None,
) -> dict[str, Any]:
    return PaperApplicationService(vault).analyze_paper(
        paper_uid,
        provider=provider,
    )


def _paper_refresh_impl(paper_uid: str, vault: Path | None) -> dict[str, Any]:
    return PaperApplicationService(vault).refresh_paper(paper_uid)


def _paper_render_impl(paper_uid: str, vault: Path | None) -> Path:
    return PaperApplicationService(vault).render_paper(paper_uid)


def _paper_inspect_impl(paper_uid: str, vault: Path | None) -> dict[str, Any]:
    return PaperApplicationService(vault).inspect_paper(paper_uid)


@paper_app.command("add")
def paper_add(
    value: str,
    priority: int = typer.Option(3, min=1, max=5),
    topic: str = typer.Option(""),
    ai: bool = typer.Option(True, "--ai/--no-ai"),
    force_refresh: bool = typer.Option(False, "--force-refresh"),
    provider: str | None = typer.Option(None, "--provider"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    _echo_json(_paper_add_impl(value, priority, topic, ai, force_refresh, provider, vault))


@paper_app.command("analyze")
def paper_analyze(
    paper_uid: str,
    provider: str | None = typer.Option(None, "--provider"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    _echo_json(_paper_analyze_impl(paper_uid, provider, vault))


@paper_app.command("render")
def paper_render(
    paper_uid: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    typer.echo(str(_paper_render_impl(paper_uid, vault)))


@paper_app.command("refresh")
def paper_refresh(
    paper_uid: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    _echo_json(_paper_refresh_impl(paper_uid, vault))


@paper_app.command("inspect")
def paper_inspect(
    paper_uid: str,
    vault: Path | None = typer.Option(None, "--vault"),
):
    """Report the current local state of every core paper artifact."""
    _echo_json(_paper_inspect_impl(paper_uid, vault))


@paper_app.command("validate")
def paper_validate():
    validate()


@paper_app.command("render-all")
def paper_render_all(
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    c = cfg()
    records = sorted((c.root / ".paperflow/data/papers").glob("*.json"))
    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "dry_run": True,
                    "papers": [
                        json.loads(path.read_text(encoding="utf-8"))["paper_uid"]
                        for path in records
                    ],
                    "changes_applied": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    results = []
    for path in records:
        record = json.loads(path.read_text(encoding="utf-8"))
        results.append(str(render_uid(c, record["paper_uid"])))
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))


@paper_app.command("visuals")
def paper_visuals(
    paper_uid: str = typer.Argument(""),
    all_papers: bool = typer.Option(False, "--all"),
    max_assets: int = typer.Option(12, "--max-assets", min=0, max=12),
):
    """从本地 PDF 提取图注可追溯的关键图片，并安全重渲染论文笔记。"""
    c = cfg()
    records_dir = c.root / ".paperflow/data/papers"
    if all_papers:
        paths = sorted(records_dir.glob("*.json"))
    elif paper_uid:
        paths = [records_dir / f"{paper_uid.replace(':', '_')}.json"]
    else:
        raise typer.BadParameter("Provide PAPER_UID or use --all")
    results = _refresh_visual_records(c, paths, max_assets=max_assets)
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    if any(item["status"] == "failed" for item in results):
        raise typer.Exit(1)


def _refresh_visual_records(
    c,
    paths: list[Path],
    *,
    max_assets: int,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            results.append(
                {
                    "paper_uid": path.stem.replace("_", ":", 1),
                    "status": "failed",
                    "error": f"Paper record not found: {path.name}",
                }
            )
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        try:
            refresh_record_visuals(
                c.root,
                record,
                max_assets=max_assets,
            )
            if c.workspace:
                paper_id = safe_component(
                    str(
                        record.get("paper_arxiv_id")
                        or record["paper_uid"]
                    ).replace(":", "_")
                )
                derived_path = (
                    c.root / ".paperflow/data/derived" / f"{paper_id}.json"
                )
                layer_paths = dict(record.get("layer_paths") or {})
                layer_paths["derived"] = derived_path.relative_to(c.root).as_posix()
                record["layer_paths"] = layer_paths
                _, _, _, derived = split_legacy_record(record)
                if derived_path.exists():
                    existing_derived = json.loads(
                        derived_path.read_text(encoding="utf-8")
                    )
                    derived.extensions = dict(
                        existing_derived.get("extensions") or {}
                    )
                atomic_json(derived_path, derived.model_dump(mode="json"))
            atomic_json(path, record)
            render_uid(c, str(record["paper_uid"]))
            results.append(
                {
                    "paper_uid": record["paper_uid"],
                    "status": record["extraction"][
                        "visual_extraction_status"
                    ],
                    "assets": len(
                        record["extraction"].get("visual_assets", [])
                    ),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "paper_uid": record.get("paper_uid", path.stem),
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return results


@migrate_app.command("visual-assets")
def migrate_visual_assets(
    max_assets: int = typer.Option(12, "--max-assets", min=0, max=12),
):
    """为已有论文重建自适应、可追溯的 Derived 视觉资产。"""
    c = cfg()
    with FileLock(c.root / ".paperflow/state/workspace.lock"):
        payload = _apply_visual_assets_migration(c, max_assets=max_assets)
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if any(item["status"] == "failed" for item in payload["papers"]):
        raise typer.Exit(1)


def _apply_visual_assets_migration(c, *, max_assets: int) -> dict[str, object]:
    from paperflow.workspace import _distribution_resource

    if c.workspace and c.workspace.versions.templates > VERSIONS.template_bundle_version:
        raise typer.BadParameter("Workspace template bundle is newer than PaperFlow")
    backup = create_workspace_backup(c.root, label="pre-visual-assets")
    workspace_path = c.root / ".paperflow/workspace.yaml"
    template_names = ["Paper Note Template.md", "Paper Note Template.en.md"]
    official_previous_hashes = {
        "Paper Note Template.md": {
            "4a6ebd51a9226b2f4abe9e39813e03f15d06b6afd883ca610e7e2d9ee4cf0ddf",
            "e7ff700ed43bb0f2dd72e3eae8cfa002cd1f0ee07f7a1a1821dd257ac6b36e73",
        },
        "Paper Note Template.en.md": {
            "34f4fee88ceda1d41c414beabd2892a5af5a339fcf72f1e5a6069b2b4cebeaac",
            "72726400b1ead5da93100a245d2fe3ff29814fcaef5b371900c411943e3f356a",
        },
    }
    template_source = _distribution_resource("templates")
    for name in template_names:
        source = template_source / name
        target = c.root / "90 System/Templates" / name
        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8") if target.exists() else ""
        target_hash = (
            hashlib.sha256(target.read_bytes()).hexdigest()
            if target.exists()
            else ""
        )
        is_official_previous = target_hash in official_previous_hashes[name]
        if target_text and target_text != source_text and not is_official_previous:
            candidate = target.with_name(target.name + ".new")
            atomic_write(candidate, source_text)
            raise RuntimeError(
                f"Customized template requires merge review: "
                f"{candidate.relative_to(c.root).as_posix()}"
            )
        if target_text != source_text and (not target_text or is_official_previous):
            atomic_write(target, source_text)
    workspace_data = YAML(typ="safe").load(
        workspace_path.read_text(encoding="utf-8")
    )
    workspace_data.setdefault("versions", {})["templates"] = (
        VERSIONS.template_bundle_version
    )
    dump_yaml(workspace_path, workspace_data)
    records = sorted((c.root / ".paperflow/data/papers").glob("*.json"))
    results = _refresh_visual_records(c, records, max_assets=max_assets)
    return {
        "migration_id": "derived-visual-assets-v2",
        "template_bundle_version": VERSIONS.template_bundle_version,
        "backup": backup.relative_to(c.root).as_posix(),
        "papers": results,
    }


@update_app.command("check")
def update_check(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    result = check_for_update(settings.updates.repository_url)
    result["repository_url"] = settings.updates.repository_url
    result["self_modified"] = False
    state = root / ".paperflow/state/update-check.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    temporary = state.with_name(state.name + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(state)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@update_app.command("info")
def update_info(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            {
                "application_version": APPLICATION_VERSION,
                "versions": VERSIONS.model_dump(),
                "migration_required": bool(migration_status(root)["pending"]),
                "updates": settings.updates.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@update_app.command("configure")
def update_configure(
    repository_url: str = typer.Option(..., "--repository-url"),
    auto_check: bool = typer.Option(True, "--auto-check/--no-auto-check"),
    auto_stage: bool = typer.Option(True, "--auto-stage/--no-auto-stage"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    from paperflow.feed.git_ops import normalize_github_repository_url

    root, settings = load_workspace_settings(vault)
    normalized = normalize_github_repository_url(repository_url).removesuffix(".git")
    local_path = root / ".paperflow/workspace.local.yaml"
    local = (
        YAML(typ="safe").load(local_path.read_text(encoding="utf-8")) or {}
        if local_path.exists()
        else {}
    )
    updates = settings.updates.model_dump(mode="json")
    updates.update(
        {
            "repository_url": normalized,
            "auto_check": auto_check,
            "auto_stage": auto_stage,
        }
    )
    local["updates"] = updates
    dump_yaml(local_path, local)
    load_workspace_settings(root)
    typer.echo(json.dumps(updates, ensure_ascii=False, indent=2))


@update_app.command("stage")
def update_stage(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    typer.echo(
        json.dumps(
            stage_update(root, settings.updates.repository_url),
            ensure_ascii=False,
            indent=2,
        )
    )


def _latest_staged_version(root: Path) -> str:
    from packaging.version import Version

    candidates = [
        path.name
        for path in (root / ".paperflow/updates").glob("*")
        if path.is_dir() and (path / "stage.json").exists()
    ]
    if not candidates:
        raise typer.BadParameter("No staged PaperFlow update is available")
    return max(candidates, key=Version)


@update_app.command("apply")
def update_apply(
    version: str = typer.Option("", "--version"),
    confirm: bool = typer.Option(False, "--confirm"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root = _root(vault)
    selected = version or _latest_staged_version(root)
    try:
        result = apply_staged_update(root, selected, confirm=confirm)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@update_app.command("auto")
def update_auto(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    result = check_for_update(settings.updates.repository_url)
    if result.get("update_available") and settings.updates.auto_stage:
        result["stage"] = stage_update(root, settings.updates.repository_url)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@update_app.command("finalize", hidden=True)
def update_finalize(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = load_workspace_settings(vault)
    migration = apply_migration(root)
    resources = install_workspace_resources(root, settings)
    verification = verify_migration(root)
    typer.echo(
        json.dumps(
            {
                "migration": migration,
                "resources": resources,
                "verification": verification,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@update_app.command("workspace")
def update_workspace(vault: Path | None = typer.Option(None, "--vault")):
    typer.echo(
        json.dumps(
            apply_migration(_root(vault)),
            ensure_ascii=False,
            indent=2,
        )
    )

@app.command()
def doctor(
    network: bool = typer.Option(False, help="同时测试 arXiv 网络连接。"),
    vault: Path | None = typer.Option(
        None,
        "--vault",
        help="要检查的 Obsidian Vault；未提供时使用 PAPERFLOW_VAULT 或当前目录向上查找。",
    ),
):
    """检查 Vault、运行时、AI CLI、插件、Bases、PDF 工具和调度器。"""
    value = load_config(vault)
    ensure_layout(value)
    checks = run_doctor(value, network)
    for item in checks: typer.echo(f"{'OK' if item['ok'] else 'FAIL':4} {item['name']}: {item['detail']}")
    if not all(i["ok"] for i in checks): raise typer.Exit(1)

@app.command("add", hidden=True)
def add_paper(value: str, priority: int = typer.Option(3, min=1, max=5), topic: str = typer.Option(""), ai: bool = typer.Option(True, "--ai/--no-ai"), force_refresh: bool = typer.Option(False, "--force-refresh"), provider: str | None = typer.Option(None), vault: Path | None = typer.Option(None, "--vault")):
    """导入 arXiv ID/URL、DOI、PDF URL 或论文网页。"""
    _echo_json(_paper_add_impl(value, priority, topic, ai, force_refresh, provider, vault))

@app.command()
def daily(discovery: bool = typer.Option(True, "--discover/--offline", help="使用 --offline 仅处理 Inbox 并生成简报，不访问 arXiv 或 AI。")):
    """处理 Inbox、发现近期 arXiv 论文、分层筛选、导入并生成每日简报。"""
    c = cfg()
    with FileLock(c.root / ".paperflow/runtime/pipeline.lock"): typer.echo(json.dumps(run_daily(c, discovery), ensure_ascii=False, default=str))

@app.command()
def discover():
    """只运行 arXiv 发现与规则初筛，不下载或完整分析。"""
    c = cfg(); run_id = str(uuid.uuid4()); started = iso_beijing()
    db = Database(c.root / ".paperflow/state/paperflow.db"); db.record_discovery_run(run_id, "running", {}, started)
    try:
        papers, stats = discover_papers(c)
        db.record_discovery_run(run_id, "completed", stats, started, iso_beijing())
    except Exception:
        db.record_discovery_run(run_id, "failed", {}, started, iso_beijing()); raise
    finally: db.close()
    typer.echo(json.dumps({"run_id": run_id, "papers": [p.model_dump(mode="json") for p in papers], "stats": stats}, ensure_ascii=False))

@app.command()
def inbox(request: str | None = typer.Option(None, help="仅处理固定 Inbox 中的 request ID 或文件名。")):
    """处理 Form Flow 创建的安全请求队列。"""
    c = cfg()
    with FileLock(c.root / ".paperflow/runtime/pipeline.lock"): typer.echo(json.dumps(process_inbox(c, request), ensure_ascii=False))

@app.command(hidden=True)
def analyze(paper_uid: str, provider: str | None = typer.Option(None), vault: Path | None = typer.Option(None, "--vault")):
    """重新分析已导入论文并保留全部用户内容。"""
    _echo_json(_paper_analyze_impl(paper_uid, provider, vault))

@app.command(hidden=True)
def refresh(paper_uid: str, vault: Path | None = typer.Option(None, "--vault")):
    """获取论文当前版本并强制刷新分析与渲染。"""
    _echo_json(_paper_refresh_impl(paper_uid, vault))

@app.command(hidden=True)
def render(paper_uid: str, vault: Path | None = typer.Option(None, "--vault")):
    """从已验证 JSON 重建 Markdown，保留用户字段与用户笔记。"""
    typer.echo(str(_paper_render_impl(paper_uid, vault)))

@app.command()
def validate():
    """验证配置、Schema、Bases、论文 YAML 和用户笔记标记。"""
    errors = validate_all(cfg().root)
    if errors:
        for error in errors: typer.echo(f"ERROR {error}")
        raise typer.Exit(1)
    typer.echo(tr(cfg().ui_locale.locale, "validation.passed"))

@app.command()
def status():
    """显示数据库、Inbox 与最近简报状态。"""
    c = cfg(); db = Database(c.root / ".paperflow/state/paperflow.db")
    try: data = db.stats()
    finally: db.close()
    data["pending_requests"] = len(list(c.path("request_folder").glob("*.md")))
    data["daily_briefs"] = len(list(c.path("daily_brief_folder").glob("*.md")))
    data["ui_locale"] = c.ui_locale.locale
    data["ui_locale_source"] = c.ui_locale.source
    automation_path = c.root / ".obsidian/plugins/paperflow-automation/data.json"
    if automation_path.exists():
        automation = json.loads(automation_path.read_text(encoding="utf-8"))
        data["obsidian_automation"] = {
            "enabled": automation.get("enabled", False),
            "daily_local_time": automation.get("dailyLocalTime"),
            "inbox_interval_minutes": automation.get("inboxIntervalMinutes"),
            "last_daily_at": automation.get("runtime", {}).get("lastDailyAt"),
            "last_inbox_at": automation.get("runtime", {}).get("lastInboxAt"),
            "last_inbox_exit_code": automation.get("runtime", {}).get("lastInboxExitCode"),
        }
    typer.echo(json.dumps(data, ensure_ascii=False))

@app.command()
def language():
    """显示 PaperFlow 当前界面语言及检测来源。"""
    locale = cfg().ui_locale
    typer.echo(json.dumps({"locale": locale.locale, "source": locale.source, "paper_originals_translated": False}, ensure_ascii=False))


@app.command("health")
def health():
    """扫描乱码、缺图、断裂附件、待重分析和同步冲突。"""
    result = scan_workspace_health(cfg().root)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise typer.Exit(1)

@app.command()
def audit(
    vault: Path | None = typer.Option(
        None,
        "--vault",
        help="要审计的 Obsidian Vault；未提供时使用 PAPERFLOW_VAULT 或当前目录向上查找。",
    ),
):
    """逐项核对开发计划的本地验收证据，并明确列出仍受阻的系统/UI 项。"""
    value = load_config(vault)
    ensure_layout(value)
    results = acceptance_audit(value)
    for item in results:
        typer.echo(f"{'PASS' if item['ok'] else 'BLOCKED' if item['blocker'] else 'FAIL':7} {item['requirement']}: {item['evidence']}")
    if not all(item["ok"] for item in results):
        raise typer.Exit(1)

@app.command("retry-failed")
def retry_failed():
    """把失败请求复制回待处理队列并重新执行（保留失败原件）。"""
    c = cfg(); count = 0
    for source in c.path("failed_folder").glob("*.md"):
        target = c.path("request_folder") / source.name
        if not target.exists(): target.write_bytes(source.read_bytes()); count += 1
    typer.echo(json.dumps({"requeued": count, "result": process_inbox(c)}))

@app.command("rebuild-index")
def rebuild_index():
    """从论文 JSON 重建 SQLite 索引。"""
    c = cfg(); db = Database(c.root / ".paperflow/state/paperflow.db"); count = 0
    indexed_uids: set[str] = set()
    try:
        for path in (c.root / ".paperflow/data/papers").glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8")); record["json_path"] = path.relative_to(c.root).as_posix(); db.upsert_paper(record); indexed_uids.add(record["paper_uid"]); count += 1
        for note in c.path("paper_folder").rglob("*.md"):
            frontmatter, _ = read_note(note)
            uid = frontmatter.get("paper_uid")
            if not uid or uid in indexed_uids:
                continue
            frontmatter["note_path"] = note.relative_to(c.root).as_posix()
            frontmatter["json_path"] = ""
            db.upsert_paper(frontmatter)
            indexed_uids.add(uid)
            count += 1
    finally: db.close()
    typer.echo(f"Indexed {count} papers")


@app.command("rebuild-relationships")
def rebuild_relationships_cmd(
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """重建关系派生层、实体链接和论文笔记中的图谱属性。"""
    from paperflow.sync_safety import assert_no_sync_conflicts

    c = cfg()
    records = sorted((c.root / ".paperflow/data/papers").glob("*.json"))
    planned: list[str] = []
    for path in records:
        try:
            planned.append(
                str(json.loads(path.read_text(encoding="utf-8"))["paper_uid"])
            )
        except (OSError, KeyError, json.JSONDecodeError):
            planned.append(path.stem.replace("_", ":", 1))
    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "dry_run": True,
                    "papers": planned,
                    "changes_applied": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    assert_no_sync_conflicts(c.root)
    results: list[dict[str, str]] = []
    with FileLock(c.root / ".paperflow/runtime/pipeline.lock"):
        for paper_uid in planned:
            try:
                note = render_uid(c, paper_uid)
                results.append(
                    {
                        "paper_uid": paper_uid,
                        "status": "rebuilt",
                        "note": str(note),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "paper_uid": paper_uid,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    if any(item["status"] == "failed" for item in results):
        raise typer.Exit(1)


@app.command("rebuild-bases")
def rebuild_bases_cmd():
    """从版本化定义重建全部 Obsidian Bases。"""
    c = cfg()
    for path in rebuild_bases(c.root, c.ui_locale.locale): typer.echo(str(path))

@app.command("migrate-v2")
def migrate_v2_legacy(dry_run: bool = typer.Option(True, "--dry-run/--apply", help="默认只预览；使用 --apply 执行旧版非破坏迁移。")):
    """运行带备份的数据库/数据迁移。当前 Schema 版本为 1。"""
    typer.echo(json.dumps(migrate_v2(cfg(), dry_run), ensure_ascii=False, default=str))

@schedule_app.command("status")
def schedule_status():
    """检查旧版 PaperFlow Windows 计划任务是否仍存在。"""
    result = windows.status(cfg().root); typer.echo(result.stdout or result.stderr); raise typer.Exit(result.returncode)


@schedule_app.command("install", hidden=True, deprecated=True)
def schedule_install_compatibility():
    """兼容旧脚本；PaperFlow 不再创建 Windows 计划任务。"""
    typer.echo(
        "Windows 计划任务安装已停用。请启用 Obsidian 的 "
        "PaperFlow Automation 插件。",
        err=True,
    )
    raise typer.Exit(2)


@schedule_app.command("run-now", hidden=True, deprecated=True)
def schedule_run_now_compatibility():
    """兼容旧脚本；直接运行每日流程，不调用 Windows 调度器。"""
    c = cfg()
    with FileLock(c.root / ".paperflow/runtime/pipeline.lock"):
        typer.echo(
            json.dumps(
                run_daily(c, True),
                ensure_ascii=False,
                default=str,
            )
        )


@schedule_app.command("uninstall")
def schedule_uninstall():
    """移除旧版 PaperFlow Windows 计划任务。"""
    result = windows.uninstall(cfg().root); typer.echo(result.stdout or result.stderr); raise typer.Exit(result.returncode)

if __name__ == "__main__": app()
