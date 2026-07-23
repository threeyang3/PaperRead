"""Optional Zotero CLI commands attached by the main PaperFlow CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from paperflow.workspace import load_workspace_settings, resolve_vault_root
from paperflow.zotero.local_api import ZoteroLocalApi
from paperflow.zotero.mapping import load_items
from paperflow.zotero.migration import ingest_plugin_results, plan_migration, verify_migration
from paperflow.zotero.store import data_root as store_data_root, ensure_layout, layout
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
    _, settings = load_workspace_settings(root)
    client = ZoteroLocalApi(settings.zotero.environment.local_api_url)
    return client.items(limit=limit, q=q)


def attach_zotero_commands(zotero_app: typer.Typer) -> None:
    """Attach read-only scan and migration-plan commands to ``zotero``."""

    @zotero_app.command("items")
    def zotero_items(
        items_json: Path | None = typer.Option(None, "--items-json", exists=True, readable=True),
        limit: int = typer.Option(100, "--limit", min=0, max=1000),
        q: str = typer.Option("", "--query"),
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """从 Local API 或脱敏 fixture 读取 Zotero 条目；只读。"""
        root = _root(vault)
        value = _items_from_input(root, items_json, limit=limit, q=q)
        typer.echo(json.dumps({"ok": True, "count": len(value), "items": value}, ensure_ascii=False, indent=2))

    @zotero_app.command("scan")
    def zotero_scan(
        items_json: Path | None = typer.Option(None, "--items-json", exists=True, readable=True),
        limit: int = typer.Option(100, "--limit", min=0, max=1000),
        q: str = typer.Option("", "--query"),
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """扫描 Zotero 条目，作为身份匹配和迁移计划输入。"""
        root = _root(vault)
        value = _items_from_input(root, items_json, limit=limit, q=q)
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
                config.write_text("schema_version: 1\nstore: paperflow-core\n", encoding="utf-8")
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
        vault: Path | None = typer.Option(None, "--vault"),
    ) -> None:
        """生成论文、Collection、PDF 和哈希迁移计划，不写 Zotero。"""
        if not dry_run:
            raise typer.BadParameter("migrate plan 只支持 dry-run；真实写入必须由 Zotero 插件执行")
        root = _root(vault)
        items = _items_from_input(root, items_json, limit=limit, q=q)
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
