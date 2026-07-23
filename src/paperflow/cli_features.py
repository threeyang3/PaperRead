"""Modular CLI surface for annotations, reviews, community and PDF++."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import typer
from jsonschema import Draft202012Validator

from paperflow.annotations.markdown_parser import parse_annotation
from paperflow.annotations.markdown_renderer import render_review
from paperflow.annotations.models import PaperReview
from paperflow.annotations.service import AnnotationService
from paperflow.annotations.store import AnnotationStore
from paperflow.community.models import CommunityContribution
from paperflow.community.publisher import (
    build_outbox,
    build_pr_tree,
    immutable_snapshot,
    normalize_private_contribution,
)
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.subscriber import ingest_community
from paperflow.obsidian.pdf_plus import (
    configure as configure_pdf_plus,
    install as install_pdf_plus,
    status as pdf_plus_status,
)
from paperflow.utils import atomic_write, iso_beijing
from paperflow.workspace import load_workspace_settings, resolve_vault_root
from paperflow.workspace_v3 import (
    apply_workspace_v3,
    plan_workspace_v3,
    plan_workspace_v3_rollback,
    rollback_workspace_v3,
    verify_workspace_v3,
)
from paperflow.entity_migration import (
    apply_entity_normalization,
    plan_entity_normalization,
)
from paperflow.entity_labels import (
    apply_entity_display_labels,
    plan_entity_display_labels,
)
from paperflow.entity_indexes import rebuild_entity_indexes
from paperflow.paths.readable import (
    apply_readable_paper_paths,
    plan_readable_paper_paths,
)


annotation_app = typer.Typer(help="管理本地私有 PDF 标注。", no_args_is_help=True)
review_app = typer.Typer(help="管理本地私有论文评审。", no_args_is_help=True)
community_app = typer.Typer(help="预览、发布与订阅社区贡献。", no_args_is_help=True)
community_publish_app = typer.Typer(help="构建隐私安全的贡献 PR。", no_args_is_help=True)
integration_pdf_app = typer.Typer(help="维护官方 PDF++ 集成。", no_args_is_help=True)


def _root(vault: Path | None) -> tuple[Path, object]:
    return load_workspace_settings(vault)


def _echo(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@annotation_app.command("create")
def annotation_create(
    paper_uid: str,
    pdf_link: str,
    kind: str = typer.Option("passage-comment", "--kind"),
    motivation: str = typer.Option("commenting", "--motivation"),
    body: str = typer.Option("", "--body"),
    selected_text: str = typer.Option("", "--selected-text"),
    pdf_version: int = typer.Option(1, "--pdf-version", min=1),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    _echo(AnnotationService(root, settings, dry_run=dry_run).create(
        paper_uid, pdf_link, pdf_version=pdf_version, kind=kind,
        motivation=motivation, body=body, selected_text=selected_text,
    ))


@annotation_app.command("list")
def annotation_list(
    paper_uid: str = typer.Option("", "--paper-uid"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    items = []
    for path in sorted((root / settings.paths.annotation_note.root).rglob("*.annotation.md")):
        annotation, _ = parse_annotation(path)
        if not paper_uid or annotation.paper_uid == paper_uid:
            items.append({
                "annotation_id": annotation.annotation_id,
                "paper_uid": annotation.paper_uid,
                "kind": annotation.kind,
                "status": annotation.preferred_revision.status,
                "path": path.relative_to(root).as_posix(),
            })
    _echo(items)


@annotation_app.command("validate")
def annotation_validate(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = _root(vault)
    errors = []
    for path in sorted((root / settings.paths.annotation_note.root).rglob("*.annotation.md")):
        try:
            parse_annotation(path)
        except Exception as exc:
            errors.append({"path": path.relative_to(root).as_posix(), "error": str(exc)})
    _echo({"ok": not errors, "errors": errors})
    if errors:
        raise typer.Exit(1)


@annotation_app.command("sync")
def annotation_sync(
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    _echo(AnnotationStore(
        root, settings.paths.annotation_note.root, settings.paths.user_annotations.root
    ).rebuild_index(dry_run=dry_run))


@annotation_app.command("ensure-index")
def annotation_ensure_index(
    paper_uid: str,
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    _echo(AnnotationService(root, settings, dry_run=dry_run).ensure_index(paper_uid))


@annotation_app.command("reanchor")
def annotation_reanchor(
    paper_uid: str,
    from_version: int = typer.Option(..., "--from-version", min=1),
    to_version: int = typer.Option(..., "--to-version", min=1),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    affected = []
    for path in sorted((root / settings.paths.annotation_note.root).rglob("*.annotation.md")):
        annotation, _ = parse_annotation(path)
        if annotation.paper_uid != paper_uid:
            continue
        revision = annotation.preferred_revision
        if revision.anchor.pdf_version == from_version:
            affected.append({
                "annotation_id": annotation.annotation_id,
                "from_version": from_version,
                "to_version": to_version,
                "status": "manual-review",
                "reason": "target PDF text extraction must be supplied before changing anchors",
            })
    if affected and not dry_run:
        review = root / "50 Inbox/Manual Review/Annotation Reanchor" / (
            paper_uid.replace(":", "_") + f"-v{from_version}-v{to_version}.md"
        )
        atomic_write(
            review,
            "---\ntype: paperflow-annotation-reanchor-review\n"
            f"paper_uid: {paper_uid}\nfrom_version: {from_version}\n"
            f"to_version: {to_version}\nstatus: pending\n---\n\n"
            "# 标注重定位人工审核\n\n"
            + "\n".join(f"- {item['annotation_id']}" for item in affected)
            + "\n",
        )
    _echo({"dry_run": dry_run, "affected": affected, "anchors_changed": 0})


@review_app.command("create")
def review_create(
    paper_uid: str,
    rating: int | None = typer.Option(None, "--rating", min=1, max=5),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    now = iso_beijing()
    review = PaperReview(
        review_id="review-" + uuid.uuid4().hex,
        paper_uid=paper_uid, rating=rating, created_at=now, updated_at=now,
    )
    year = "Unclassified"
    record = root / ".paperflow/data/papers" / f"{paper_uid.replace(':', '_')}.json"
    if record.exists():
        year = str(json.loads(record.read_text(encoding="utf-8")).get("paper_year") or year)
    path = root / settings.paths.paper_review.root / year / f"{paper_uid.replace(':', '_')}.review.md"
    if not dry_run:
        atomic_write(path, render_review(review))
    _echo({"dry_run": dry_run, "review_id": review.review_id,
           "path": path.relative_to(root).as_posix()})


@review_app.command("validate")
def review_validate(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = _root(vault)
    errors = []
    for path in (root / settings.paths.paper_review.root).rglob("*.review.md"):
        try:
            from paperflow.obsidian.frontmatter import read_note
            PaperReview.model_validate(read_note(path)[0])
        except Exception as exc:
            errors.append({"path": path.relative_to(root).as_posix(), "error": str(exc)})
    _echo({"ok": not errors, "errors": errors})
    if errors:
        raise typer.Exit(1)


def _outbox_items(root: Path) -> list[Path]:
    return sorted((root / ".paperflow/data/community/outbox").glob(
        "papers/*/community/*/*/r*.json"
    ))


@community_app.command("list")
def community_list(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo([path.relative_to(root).as_posix() for path in _outbox_items(root)])


@community_app.command("preview")
def community_preview(path: Path):
    value = CommunityContribution.model_validate_json(path.read_text(encoding="utf-8"))
    _echo({"contribution": value.model_dump(mode="json"),
           "privacy_findings": scan_community_contribution(value.model_dump(mode="json"))})


@community_app.command("select")
def community_select(
    source: Path,
    creator: str = typer.Option(..., "--creator"),
    license_name: str = typer.Option(..., "--license"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, settings = _root(vault)
    if not settings.community.publish_enabled:
        raise typer.BadParameter("community.publish_enabled is false")
    resolved = source.resolve()
    allowed_roots = [
        (root / settings.paths.user_annotations.root).resolve(),
        (root / settings.paths.paper_review.root).resolve(),
    ]
    if not any(resolved.is_relative_to(candidate) for candidate in allowed_roots):
        raise typer.BadParameter(
            "source must be a PaperFlow private annotation JSON or review Markdown"
        )
    if resolved.suffix.casefold() == ".json":
        private = json.loads(resolved.read_text(encoding="utf-8"))
    elif resolved.suffix.casefold() == ".md":
        from paperflow.obsidian.frontmatter import read_note

        private, _ = read_note(resolved)
    else:
        raise typer.BadParameter("source must end in .json or .md")
    private = normalize_private_contribution(private)
    snapshot = immutable_snapshot(private, creator=creator, license_name=license_name)
    _echo(build_outbox(root, snapshot, dry_run=dry_run))


@community_app.command("unselect")
def community_unselect(
    path: Path,
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
):
    if not dry_run:
        path.unlink(missing_ok=True)
    _echo({"dry_run": dry_run, "path": str(path), "deleted": not dry_run})


@community_publish_app.command("plan")
def community_publish_plan(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo({"files": [path.relative_to(root).as_posix() for path in _outbox_items(root)],
           "network_changes": 0})


@community_publish_app.command("build")
def community_publish_build(
    destination: Path,
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, _ = _root(vault)
    _echo(build_pr_tree(root, destination, dry_run=dry_run))


@community_publish_app.command("scan")
def community_publish_scan(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    findings = {}
    for path in _outbox_items(root):
        value = json.loads(path.read_text(encoding="utf-8"))
        current = scan_community_contribution(value)
        if current:
            findings[path.relative_to(root).as_posix()] = current
    _echo({"ok": not findings, "findings": findings})
    if findings:
        raise typer.Exit(1)


@community_publish_app.command("diff")
def community_publish_diff(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo({"files": [path.relative_to(root).as_posix() for path in _outbox_items(root)],
           "note": "immutable outbox snapshots only"})


@community_publish_app.command("submit-pr")
def community_submit_pr(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo({
        "dry_run": True,
        "files": [path.relative_to(root).as_posix() for path in _outbox_items(root)],
        "steps": ["fork", "branch", "commit", "pull-request"],
        "network_changes": 0,
        "reason": "real public contribution PR requires a separate explicit approval",
    })


@community_app.command("status")
def community_status(vault: Path | None = typer.Option(None, "--vault")):
    root, settings = _root(vault)
    _echo({"enabled": settings.community.enabled,
           "publish_enabled": settings.community.publish_enabled,
           "outbox": len(_outbox_items(root)),
           "subscriptions": len(list((root / settings.paths.community_cache.root).rglob("r*.json")))})


@community_app.command("retract")
def community_retract():
    raise typer.BadParameter(
        "Retractions are immutable public records; use a new selected snapshot and explicit PR approval."
    )


@integration_pdf_app.command("status")
def pdf_status(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo(pdf_plus_status(root))


@integration_pdf_app.command("install")
def pdf_install(
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, _ = _root(vault)
    _echo(install_pdf_plus(root, dry_run=dry_run))


@integration_pdf_app.command("configure")
def pdf_configure(
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, _ = _root(vault)
    _echo(configure_pdf_plus(root, dry_run=dry_run))


@integration_pdf_app.command("repair")
def pdf_repair(
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    vault: Path | None = typer.Option(None, "--vault"),
):
    root, _ = _root(vault)
    _echo(configure_pdf_plus(root, repair=True, dry_run=dry_run))


@integration_pdf_app.command("upgrade")
def pdf_upgrade(vault: Path | None = typer.Option(None, "--vault")):
    root, _ = _root(vault)
    _echo({"dry_run": True, "status": pdf_plus_status(root),
           "action": "use Obsidian official community-plugin updater"})


def attach_feature_apps(
    root_app: typer.Typer,
    integration_app: typer.Typer,
    migrate_app: typer.Typer,
    workspace_app: typer.Typer,
) -> None:
    community_app.add_typer(community_publish_app, name="publish")
    integration_app.add_typer(integration_pdf_app, name="pdf-plus")
    root_app.add_typer(annotation_app, name="annotation")
    root_app.add_typer(review_app, name="review")
    root_app.add_typer(community_app, name="community")

    @migrate_app.command("workspace-v3")
    def migrate_workspace_v3(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        root = resolve_vault_root(vault)
        result = (
            apply_workspace_v3(root)
            if apply_changes
            else plan_workspace_v3(root)
        )
        _echo(result)
        if apply_changes and not result.get("verification", {}).get("ok", False):
            raise typer.Exit(1)

    @migrate_app.command("verify-workspace-v3")
    def verify_v3(vault: Path | None = typer.Option(None, "--vault")):
        root = resolve_vault_root(vault)
        _echo(verify_workspace_v3(root))

    @migrate_app.command("rollback-workspace-v3")
    def rollback_v3(
        backup: Path | None = typer.Option(None, "--backup"),
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        """Restore a checksummed 1.5 backup without deleting later user files."""
        root = resolve_vault_root(vault)
        _echo(
            rollback_workspace_v3(root, backup)
            if apply_changes
            else plan_workspace_v3_rollback(root, backup)
        )

    @migrate_app.command("readable-paper-paths")
    def migrate_readable_paper_paths(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        """将论文 Hub 从纯 ID 文件名迁移为短标题-编号文件名。"""
        root = resolve_vault_root(vault)
        _echo(
            apply_readable_paper_paths(root)
            if apply_changes
            else plan_readable_paper_paths(root)
        )

    @migrate_app.command("entities")
    def migrate_entities(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        """合并重复 Topic/Method/Dataset 实体并更新 wikilink。"""
        root = resolve_vault_root(vault)
        _echo(
            apply_entity_normalization(root)
            if apply_changes
            else plan_entity_normalization(root)
        )

    @migrate_app.command("entity-labels")
    def migrate_entity_labels(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        """统一实体显示名称，保留 Topic/Method/Dataset 类型边界和用户正文。"""
        root = resolve_vault_root(vault)
        _echo(
            apply_entity_display_labels(root)
            if apply_changes
            else plan_entity_display_labels(root)
        )

    @migrate_app.command("entity-index")
    def migrate_entity_index(
        apply_changes: bool = typer.Option(False, "--apply/--dry-run"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        """重建 Topic/Method/Dataset 的反向论文索引，保留用户正文。"""
        root = resolve_vault_root(vault)
        _echo(rebuild_entity_indexes(root, apply=apply_changes))

    @workspace_app.command("rebuild-annotation-index")
    def rebuild_annotation_index(
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        root, settings = _root(vault)
        _echo(AnnotationStore(
            root, settings.paths.annotation_note.root,
            settings.paths.user_annotations.root,
        ).rebuild_index(dry_run=dry_run))

    @workspace_app.command("rebuild-community-index")
    def rebuild_community_index(
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        vault: Path | None = typer.Option(None, "--vault"),
    ):
        root, settings = _root(vault)
        entries = []
        for path in (root / settings.paths.community_cache.root).rglob("r*.json"):
            value = CommunityContribution.model_validate_json(path.read_text(encoding="utf-8"))
            entries.append({"paper_uid": value.paper_uid,
                            "contribution_id": value.contribution_id,
                            "path": path.relative_to(root).as_posix()})
        target = root / ".paperflow/data/derived/community-index.json"
        if not dry_run:
            from paperflow.utils import atomic_json
            atomic_json(target, {"schema_version": 1, "entries": entries})
        _echo({"dry_run": dry_run, "entries": len(entries)})
