"""Optional Zotero CLI commands attached by the main PaperFlow CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from paperflow.workspace import load_workspace_settings, resolve_vault_root
from paperflow.zotero.local_api import ZoteroLocalApi, ZoteroLocalApiError
from paperflow.zotero.mapping import load_items
from paperflow.zotero.migration import ingest_plugin_results, plan_migration, verify_migration
from paperflow.zotero.store import data_root as store_data_root, ensure_layout, layout, state_root, runtime_root, standalone
from paperflow.sync_safety import find_sync_conflicts
from paperflow.zotero.markdown import render_ai_projection
from paperflow.zotero.feynman import ensure_questions, load_answers, save_answer


def _root(vault: Path | None) -> Path:
    return resolve_vault_root(vault)


def _command_root(vault: Path | None, core_root: Path | None) -> Path:
    if vault is not None and core_root is not None:
        raise typer.BadParameter("--vault and --data-root are mutually exclusive")
    if core_root is not None:
        resolved = core_root.expanduser().resolve()
        if (resolved / ".paperflow").exists():
            raise typer.BadParameter("--data-root must be standalone, not a Vault")
        if not (resolved / "data").is_dir():
            raise typer.BadParameter("--data-root is not initialized; run `zotero data-root --apply` first")
        return resolved
    return _root(vault)


def _items_from_input(
    root: Path,
    items_json: Path | None,
    *,
    limit: int,
    q: str,
) -> list[dict[str, Any]]:
    if items_json is not None:
        return load_items(items_json)
    if standalone(root):
        # Standalone Core has no Workspace model.  Read only the explicit
        # loopback URL from config.yaml; never guess a Zotero data directory.
        api_url = "http://127.0.0.1:23119/api/"
        config_path = root / "config.yaml"
        if config_path.is_file():
            from ruamel.yaml import YAML

            loaded = YAML(typ="safe").load(config_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                zotero = loaded.get("zotero") or {}
                environment = zotero.get("environment") if isinstance(zotero, dict) else {}
                if isinstance(environment, dict) and environment.get("local_api_url"):
                    api_url = str(environment["local_api_url"])
                # Keep the compact standalone config contract working too.
                api_url = str((loaded.get("zotero_local_api_url") or api_url))
        client = ZoteroLocalApi(api_url)
    else:
        _, settings = load_workspace_settings(root)
        client = ZoteroLocalApi(settings.zotero.environment.local_api_url)
    return client.items(limit=limit, q=q)


def _emit_local_api_required(error: ZoteroLocalApiError) -> None:
    """Report an unavailable Zotero process without a traceback."""
    typer.echo(json.dumps({
        "ok": False,
        "status": "zotero-required",
        "reason": "local-api-unavailable",
        "message": str(error),
        "next": "启动 Zotero，并确认 PaperFlow 插件已连接 Local API；本命令不会写入 zotero.sqlite。",
    }, ensure_ascii=False, indent=2))
    raise typer.Exit(2)


def attach_zotero_commands(zotero_app: typer.Typer) -> None:
    """Attach read-only scan and migration-plan commands to ``zotero``."""

    @zotero_app.command("items")
    def zotero_items(
        items_json: Path | None = typer.Option(None, "--items-json", exists=True, readable=True),
        limit: int = typer.Option(100, "--limit", min=0, max=1000),
        q: str = typer.Option("", "--query"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """从 Local API 或脱敏 fixture 读取 Zotero 条目；只读。"""
        root = _command_root(vault, core_root)
        try:
            value = _items_from_input(root, items_json, limit=limit, q=q)
        except ZoteroLocalApiError as error:
            _emit_local_api_required(error)
        typer.echo(json.dumps({"ok": True, "count": len(value), "items": value}, ensure_ascii=False, indent=2))

    @zotero_app.command("scan")
    def zotero_scan(
        items_json: Path | None = typer.Option(None, "--items-json", exists=True, readable=True),
        limit: int = typer.Option(100, "--limit", min=0, max=1000),
        q: str = typer.Option("", "--query"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """扫描 Zotero 条目，作为身份匹配和迁移计划输入。"""
        root = _command_root(vault, core_root)
        try:
            value = _items_from_input(root, items_json, limit=limit, q=q)
        except ZoteroLocalApiError as error:
            _emit_local_api_required(error)
        typer.echo(json.dumps({"ok": True, "count": len(value), "items": value}, ensure_ascii=False, indent=2))

    @zotero_app.command("data-root")
    def zotero_data_root(
        data_root: Path = typer.Option(..., "--data-root"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    ) -> None:
        """规划或初始化不依赖 Obsidian Vault 的 PaperFlow Core 数据根。"""
        root = data_root.expanduser().resolve()
        if (root / ".paperflow").exists():
            raise typer.BadParameter("data-root must be a standalone directory, not an existing Vault")
        paths = layout(root, force_standalone=True)
        result: dict[str, Any] = {
            "dry_run": not apply_changes,
            "root": root.as_posix(),
            "paths": {name: path.as_posix() for name, path in paths.items()},
            "policy": "creates only Core directories; never moves or deletes Vault/Zotero data",
        }
        if apply_changes:
            result["created"] = ensure_layout(root, force_standalone=True)
            config = root / "config.yaml"
            if not config.exists():
                config.write_text(
                    "schema_version: 1\n"
                    "store: paperflow-core\n"
                    "timezone: Asia/Shanghai\n"
                    "analysis:\n"
                    "  provider: mock\n"
                    "  profile: full_analysis\n"
                    "  model: deterministic-v1\n"
                    "  prompt_version: paper-analysis-v3\n"
                    "  providers:\n"
                    "    claude:\n"
                    "      executable: claude\n"
                    "      timeout_seconds: 1800\n"
                    "    codex:\n"
                    "      executable: codex\n"
                    "      timeout_seconds: 1800\n"
                    "      reasoning_effort: high\n"
                    "    chatgpt-web:\n"
                    "      browser_executable: ''\n"
                    "      browser_profile_dir: '%LOCALAPPDATA%/PaperFlow/ChatGPTWeb'\n"
                    "      base_url: https://chatgpt.com/\n"
                    "      allow_pdf_upload: false\n"
                    "      model_preference: [Pro, Thinking, GPT-5.6, GPT-5]\n"
                    "subscriptions:\n"
                    "  sources: []\n",
                    encoding="utf-8",
                )
                result["config"] = "config.yaml"
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    @zotero_app.command("render-ai")
    def zotero_render_ai(
        paper_uid: str = typer.Option(..., "--paper"),
        zotero_item_key: str = typer.Option("", "--zotero-item-key"),
        output: Path | None = typer.Option(None, "--output"),
        target: str = typer.Option("zotero", "--target", help="zotero、obsidian 或 both"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """渲染系统管理的 Zotero AI Markdown 投影，不覆盖用户编辑的现有文件。"""
        result = render_ai_projection(_command_root(vault, core_root), paper_uid, zotero_item_key=zotero_item_key, output=output, apply_changes=apply_changes, target=target)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "manual-review-required":
            raise typer.Exit(2)

    @zotero_app.command("analyze")
    def zotero_analyze(
        paper_uid: str = typer.Option(..., "--paper"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """在 standalone Core 中运行配置的 AI Provider 并写入 AI Raw。"""
        root = _command_root(vault, core_root)
        if not (root / "data").is_dir() or (root / ".paperflow").exists():
            raise typer.BadParameter("zotero analyze currently requires --data-root standalone mode")
        if not apply_changes:
            typer.echo(json.dumps({
                "paper_uid": paper_uid,
                "dry_run": True,
                "status": "would-analyze",
                "provider": "configured-in-config.yaml",
                "artifact_permission": "AI_VERSIONED",
            }, ensure_ascii=False, indent=2))
            return
        from paperflow.zotero.standalone_ai import analyze_standalone

        typer.echo(json.dumps(analyze_standalone(root, paper_uid), ensure_ascii=False, indent=2))

    @zotero_app.command("sync-subscriptions")
    def zotero_sync_subscriptions(
        source: list[str] = typer.Option([], "--source", help="只同步指定 source name；可重复传入"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """在 standalone Core 中同步 config.yaml 已配置的订阅源。"""
        root = _command_root(None, core_root)
        if not (root / "data").is_dir() or (root / ".paperflow").exists():
            raise typer.BadParameter("zotero sync-subscriptions requires --data-root standalone mode")
        from ruamel.yaml import YAML

        config_path = root / "config.yaml"
        loaded = YAML(typ="safe").load(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        config = loaded if isinstance(loaded, dict) else {}
        configured = (config.get("subscriptions") or {}).get("sources") or []
        requested = {str(value).strip() for value in source if str(value).strip()}
        selected = [
            value for value in configured
            if isinstance(value, dict) and value.get("url")
            and (not requested or str(value.get("name") or value["url"]) in requested)
        ]
        if not apply_changes:
            typer.echo(json.dumps({
                "dry_run": True,
                "source_count": len(selected),
                "sources": [str(value.get("name") or value["url"]) for value in selected],
                "network_changes": 0,
            }, ensure_ascii=False, indent=2))
            return
        from paperflow.zotero.standalone_sync import sync_core_feed

        results = [
            sync_core_feed(
                root,
                url=str(value["url"]),
                name=str(value.get("name") or value["url"]),
                branch=str(value.get("branch") or "main"),
                trust=str(value.get("trust") or "metadata-and-ai"),
                auto_download_pdf=bool(value.get("auto_download_pdf", False)),
                auto_render_notes=bool(value.get("auto_render_notes", False)),
                capabilities=list(value.get("capabilities") or ["raw", "ai"]),
            )
            for value in selected
        ]
        typer.echo(json.dumps({"dry_run": False, "source_count": len(results), "results": results}, ensure_ascii=False, indent=2))

    @zotero_app.command("create-collection")
    def zotero_create_collection(
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    ) -> None:
        """兼容别名：生成 Collection 创建/复用计划；实际写入只由 Zotero 插件完成。"""
        if core_root is not None:
            root = _command_root(vault, core_root)
            config_path = root / "config.yaml"
            collection = "PaperFlow"
            if config_path.is_file():
                from ruamel.yaml import YAML

                loaded = YAML(typ="safe").load(config_path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    collection = str(((loaded.get("zotero") or {}).get("collection") or collection))
        else:
            root = _root(vault)
            _, settings = load_workspace_settings(root)
            collection = settings.zotero.collections.primary.name
        result = {
            "dry_run": not apply_changes,
            "status": "plugin-required",
            "collection": {"name": collection},
            "database_access": False,
            "reason": "PaperFlow Core never writes zotero.sqlite; the Zotero plugin must create/reuse the Collection.",
        }
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        if apply_changes:
            raise typer.Exit(2)

    @zotero_app.command("analyze-pending")
    def zotero_analyze_pending(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """列出尚无有效 AI Raw 的论文；可选地排队分析，但不修改 Zotero。"""
        root = _command_root(vault, core_root)
        papers_dir = store_data_root(root) / "papers"
        pending: list[str] = []
        for source in sorted(papers_dir.glob("*.json")) if papers_dir.is_dir() else []:
            try:
                value = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or not value.get("paper_uid"):
                continue
            uid = str(value["paper_uid"])
            from paperflow.zotero.standalone_ai import load_current_analysis

            if load_current_analysis(root, uid) is None:
                pending.append(uid)
        result: dict[str, Any] = {
            "dry_run": not apply_changes,
            "status": "would-analyze" if pending and not apply_changes else ("queued" if pending else "none"),
            "pending": pending,
            "count": len(pending),
            "provider": "configured-in-config.yaml" if standalone(root) else "workspace-profile",
        }
        if apply_changes and pending:
            from paperflow.zotero.standalone_ai import analyze_standalone

            if not standalone(root):
                result.update({"status": "manual-review-required", "reason": "standalone Core is required for direct batch analysis"})
            else:
                result["results"] = [analyze_standalone(root, uid) for uid in pending]
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    @zotero_app.command("sync-status")
    def zotero_sync_status(
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """报告订阅、作业和本地映射状态；只读。"""
        root = _command_root(vault, core_root)
        # Durable job records are stored under state/jobs for both Vault and
        # standalone layouts; runtime is reserved for ephemeral staging.
        jobs = state_root(root) / "jobs"
        state = state_root(root)
        job_files = sorted(jobs.glob("*.json")) if jobs.is_dir() else []
        statuses: dict[str, int] = {}
        for path in job_files:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            status = str(value.get("status") or "unknown") if isinstance(value, dict) else "unknown"
            statuses[status] = statuses.get(status, 0) + 1
        typer.echo(json.dumps({
            "ok": True,
            "root_mode": "standalone" if standalone(root) else "vault",
            "jobs": {"count": len(job_files), "by_status": statuses},
            "session": (state / "zotero-core-session.json").is_file(),
            "network_changes": 0,
        }, ensure_ascii=False, indent=2))

    @zotero_app.command("sync-annotations")
    def zotero_sync_annotations(
        paper_uid: str = typer.Option("", "--paper"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
    ) -> None:
        """生成标注镜像同步计划；真实 Zotero 读取由插件公共 API 执行。"""
        root = _command_root(vault, core_root)
        annotation_root = store_data_root(root) / "annotations" / "zotero"
        existing = sorted(annotation_root.glob("**/*.json")) if annotation_root.is_dir() else []
        result = {
            "dry_run": not apply_changes,
            "status": "plugin-required",
            "paper_uid": paper_uid,
            "existing_mirrors": len(existing),
            "database_access": False,
            "write_target": "SYSTEM_MANAGED annotation mirror",
        }
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        if apply_changes:
            raise typer.Exit(2)

    @zotero_app.command("conflicts")
    def zotero_conflicts(
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """列出同步冲突文件；不删除、不覆盖任何一方。"""
        root = _command_root(vault, core_root)
        conflicts = find_sync_conflicts(root) if not standalone(root) else [
            path for folder in ("data", "documents", "state", "runtime")
            for path in (root / folder).rglob("*") if (root / folder).is_dir()
            if path.is_file() and any(marker in path.name for marker in ("-冲突", "-NSConflict"))
        ]
        typer.echo(json.dumps({
            "ok": not conflicts,
            "count": len(conflicts),
            "conflicts": [path.relative_to(root).as_posix() for path in conflicts],
            "action": "manual-review-required" if conflicts else "none",
        }, ensure_ascii=False, indent=2))

    @zotero_app.command("community")
    def zotero_community(
        paper_uid: str = typer.Option("", "--paper"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """查看社区 outbox/订阅记录；只读，不执行 Git 或网络操作。"""
        root = _command_root(vault, core_root)
        base = store_data_root(root) / "community"
        files: list[Path] = []
        if base.is_dir():
            # Feed caches and the local outbox use different directory depths.
            for pattern in (
                "**/papers/*/community/*/*/r*.json",
                "papers/*/community/*/*/r*.json",
            ):
                files.extend(base.glob(pattern))
        records: list[dict[str, Any]] = []
        for path in files:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or (paper_uid and value.get("paper_uid") != paper_uid):
                continue
            records.append({
                key: value.get(key)
                for key in ("paper_uid", "contribution_id", "revision", "creator", "kind", "created_at", "license")
                if key in value
            })
        unique = {
            (str(item.get("creator") or ""), str(item.get("contribution_id") or ""), int(item.get("revision") or 0)): item
            for item in records
        }
        records = sorted(unique.values(), key=lambda item: (str(item.get("created_at") or ""), str(item.get("contribution_id") or "")), reverse=True)
        typer.echo(json.dumps({
            "ok": True,
            "paper_uid": paper_uid,
            "count": len(records),
            "records": records,
            "network_changes": 0,
            "git_actions": [],
        }, ensure_ascii=False, indent=2))

    @zotero_app.command("attach-ai-markdown")
    def zotero_attach_ai_markdown(
        paper_uid: str = typer.Option(..., "--paper"),
        zotero_item_key: str = typer.Option("", "--zotero-item-key"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """生成由 Zotero 插件执行附件导入的计划；Core 不直接写 Zotero。"""
        result = render_ai_projection(_command_root(vault, core_root), paper_uid, zotero_item_key=zotero_item_key, apply_changes=False)
        result.update({"status": "plugin-required", "write_target": "Zotero Attachments API", "requires_user_confirmation": True})
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    feynman_app = typer.Typer(help="管理 AI 生成的问题与用户独立答案。", no_args_is_help=True)
    zotero_app.add_typer(feynman_app, name="feynman")

    @feynman_app.command("init")
    def zotero_feynman_init(
        paper_uid: str = typer.Option(..., "--paper"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """把 AI Raw 中的问题投影到用户答案文件；不覆盖已有答案。"""
        root = _command_root(vault, core_root)
        record_path = store_data_root(root) / "papers" / f"{paper_uid.replace(':', '_')}.json"
        if not record_path.is_file():
            raise typer.BadParameter(f"paper record not found: {paper_uid}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        questions = record.get("ai_feynman_questions") or record.get("feynman_questions") or []
        result = ensure_questions(root, paper_uid, questions, apply_changes=apply_changes)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    @feynman_app.command("answer")
    def zotero_feynman_answer(
        paper_uid: str = typer.Option(..., "--paper"),
        question_id: str = typer.Option(..., "--question-id"),
        answer: str = typer.Option(..., "--answer"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        """写入用户答案；AI Raw 和系统 Markdown 永远不被改写。"""
        result = save_answer(_command_root(vault, core_root), paper_uid, question_id, answer)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    @feynman_app.command("show")
    def zotero_feynman_show(
        paper_uid: str = typer.Option(..., "--paper"),
        vault: Path | None = typer.Option(None, "--vault"),
        core_root: Path | None = typer.Option(None, "--data-root"),
    ) -> None:
        typer.echo(json.dumps(load_answers(_command_root(vault, core_root), paper_uid), ensure_ascii=False, indent=2))

    migrate_app = typer.Typer(help="规划和验证 Zotero 迁移；真实写入必须由 Zotero 插件完成。", no_args_is_help=True)
    zotero_app.add_typer(migrate_app, name="migrate")

    @migrate_app.command("plan")
    def zotero_migrate_plan(
        items_json: Path | None = typer.Option(None, "--items-json", exists=True, readable=True),
        paper_uid: str = typer.Option("", "--paper"),
        collection: str = typer.Option("PaperFlow", "--collection"),
        attachment_mode: str = typer.Option("stored", "--attachment-mode"),
        dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="计划命令始终不写 Zotero。"),
        limit: int = typer.Option(1000, "--limit", min=0, max=1000),
        q: str = typer.Option("", "--query"),
        all_papers: bool = typer.Option(False, "--all", help="显式规划全部本地论文；与 --paper 互斥。"),
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """生成论文、Collection、PDF 和哈希迁移计划，不写 Zotero。"""
        if not dry_run:
            raise typer.BadParameter("migrate plan 只支持 dry-run；真实写入必须由 Zotero 插件执行")
        if all_papers and paper_uid:
            raise typer.BadParameter("--all cannot be combined with --paper")
        root = _root(vault)
        try:
            items = _items_from_input(root, items_json, limit=limit, q=q)
        except ZoteroLocalApiError as error:
            _emit_local_api_required(error)
        value = plan_migration(
            root,
            items,
            collection_name=collection,
            paper_uid=paper_uid,
            attachment_mode=attachment_mode,
        )
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))

    @migrate_app.command("apply")
    def zotero_migrate_apply(
        results_json: Path = typer.Option(..., "--results-json", exists=True, readable=True),
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """接收 Zotero 插件已完成的结果并写入本地 mapping，不直接写 Zotero。"""
        root = _root(vault)
        value = json.loads(results_json.read_text(encoding="utf-8"))
        result = ingest_plugin_results(root, value)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result.get("status") == "partial":
            raise typer.Exit(2)

    @migrate_app.command("verify")
    def zotero_migrate_verify(vault: Path | None = typer.Option(None, "--vault")) -> None:
        """验证本地 Zotero mapping 的完整性和可回溯性。"""
        result = verify_migration(_root(vault))
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise typer.Exit(1)

    @migrate_app.command("rollback")
    def zotero_migrate_rollback(
        plan_json: Path = typer.Option(..., "--plan", exists=True, readable=True),
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """生成回滚清单；只报告插件应撤销的本轮动作，不直接改 Zotero。"""
        value = json.loads(plan_json.read_text(encoding="utf-8"))
        papers = value.get("papers") if isinstance(value, dict) else []
        rollback = [
            {
                "paper_uid": item.get("paper_uid"),
                "action": "remove-membership-created-by-this-run",
                "delete_item": False,
                "delete_pdf": False,
            }
            for item in papers
            if isinstance(item, dict)
        ]
        typer.echo(json.dumps({"dry_run": True, "items": rollback, "vault": str(_root(vault))}, ensure_ascii=False, indent=2))
