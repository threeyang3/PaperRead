"""Formal migration for human-readable Paper Hub filenames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.paths.migrate import migrate_paths
from paperflow.paths.service import preview_all
from paperflow.utils import atomic_write, iso_beijing
from paperflow.config import load_config
from paperflow.workspace import WorkspaceSettings, dump_yaml, load_workspace_settings
from paperflow.workspace_ops import create_workspace_backup


READABLE_NOTE_TEMPLATE = "{{year}}/{{short_title|slug}}-{{paper_id}}.md"
MIGRATION_ID = "paths-0001-readable-paper-filenames"


def _workspace_value(root: Path) -> dict[str, Any]:
    path = root / ".paperflow/workspace.yaml"
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def _candidate_settings(root: Path, current: WorkspaceSettings) -> WorkspaceSettings:
    value = current.model_dump(mode="json")
    raw = _workspace_value(root)
    raw_paths = dict(raw.get("paths") or {})
    paths = dict(value.get("paths") or {})
    for name in ("note", "paper_hub"):
        rule = dict(paths.get(name) or {})
        rule.update(dict(raw_paths.get(name) or {}))
        rule["template"] = READABLE_NOTE_TEMPLATE
        paths[name] = rule
    value["paths"] = paths
    return WorkspaceSettings.model_validate(value)


def plan_readable_paper_paths(root: Path) -> dict[str, Any]:
    """Return a dry-run plan without changing config or notes."""
    _, current = load_workspace_settings(root)
    candidate = _candidate_settings(root, current)
    records = preview_all(root, candidate)
    moves = [
        item["note"]
        for item in records
        if item["note"]["old_path"]
        and item["note"]["old_path"] != item["note"]["new_path"]
    ]
    conflicts = [item for item in moves if item["conflict"]]
    return {
        "migration_id": MIGRATION_ID,
        "dry_run": True,
        "current_template": current.paths.note.template,
        "target_template": READABLE_NOTE_TEMPLATE,
        "config_changed": current.paths.note.template != READABLE_NOTE_TEMPLATE
        or current.paths.paper_hub.template != READABLE_NOTE_TEMPLATE,
        "moves": moves,
        "move_count": len(moves),
        "conflicts": conflicts,
        "policy": (
            "retain paper IDs in the filename suffix; keep old paths as redirects; "
            "preserve user fields and USER_NOTES_START/END"
        ),
    }


def _rewrite_links(root: Path, moves: list[dict[str, Any]]) -> list[str]:
    replacements = [
        (
            str(item["old_path"]).removesuffix(".md"),
            str(item["new_path"]).removesuffix(".md"),
        )
        for item in moves
        if item.get("old_path") and item.get("new_path")
    ]
    changed: list[str] = []
    excluded = {".paperflow/backups", ".paperflow/runtime", ".paperflow/cache"}
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if any(relative == prefix or relative.startswith(prefix + "/") for prefix in excluded):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = text
        for old, new in replacements:
            updated = updated.replace(f"[[{old}]]", f"[[{new}]]")
            updated = updated.replace(f"[[{old}|", f"[[{new}|")
        if updated != text:
            atomic_write(path, updated)
            changed.append(relative)
    return changed


def _layer_path_mismatches(root: Path) -> list[tuple[Path, dict[str, Any], dict[str, Any]]]:
    """Find Derived records whose selected paths lag behind Paper records."""
    mismatches: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    papers = root / ".paperflow/data/papers"
    derived_root = root / ".paperflow/data/derived"
    for paper_path in sorted(papers.glob("*.json")):
        try:
            record = json.loads(paper_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        paper_id = str(record.get("paper_arxiv_id") or record.get("paper_uid") or "").replace(":", "_")
        derived_path = derived_root / f"{paper_id}.json"
        if not derived_path.exists():
            continue
        try:
            value = json.loads(derived_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        layer = dict(value.get("derived") or {})
        changed = False
        for key in ("note_path", "paper_pdf_path"):
            if record.get(key) and layer.get(key) != record[key]:
                layer[key] = record[key]
                changed = True
        if changed:
            updated = dict(value)
            updated["derived"] = layer
            mismatches.append((derived_path, value, updated))
    return mismatches


def _synchronize_layer_paths(root: Path, backup: Path | None = None) -> int:
    mismatches = _layer_path_mismatches(root)
    for path, original, updated in mismatches:
        if backup is not None:
            snapshot = backup / "files" / path.relative_to(root)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(path.read_bytes())
        from paperflow.utils import atomic_json
        atomic_json(path, updated)
    return len(mismatches)


def apply_readable_paper_paths(root: Path) -> dict[str, Any]:
    """Apply the readable filename migration with a full workspace backup."""
    plan = plan_readable_paper_paths(root)
    if plan["conflicts"]:
        raise RuntimeError(
            "Readable paper filename migration has target conflicts; "
            "resolve them or use a custom path template first."
        )
    layer_mismatches = _layer_path_mismatches(root)
    if not plan["config_changed"] and not plan["moves"] and not layer_mismatches:
        return {**plan, "dry_run": False, "status": "already-applied"}

    backup = create_workspace_backup(root, label="readable-paper-paths")
    workspace_path = root / ".paperflow/workspace.yaml"
    original = workspace_path.read_bytes()
    _, current = load_workspace_settings(root)
    try:
        value = _workspace_value(root)
        raw_paths = dict(value.get("paths") or {})
        paths = dict(current.paths.model_dump(mode="json"))
        for name in ("note", "paper_hub"):
            rule = dict(paths.get(name) or {})
            rule.update(dict(raw_paths.get(name) or {}))
            rule["template"] = READABLE_NOTE_TEMPLATE
            paths[name] = rule
        value["paths"] = paths
        dump_yaml(workspace_path, value)
        _, settings = load_workspace_settings(root)
        migration = migrate_paths(root, settings, dry_run=False)
        changed_links = _rewrite_links(root, migration.get("moves", []))
        synchronized_layers = _synchronize_layer_paths(root, backup)
    except Exception:
        workspace_path.write_bytes(original)
        raise

    # The redirects preserve old inbound links; re-rendering updates all
    # generated relationship links to the new canonical note paths. A legacy
    # note without a user marker is deliberately left for Manual Review rather
    # than blocking the other papers in the migration.
    from paperflow.pipeline.render import render_uid

    rendered: list[str] = []
    manual_review: list[dict[str, str]] = []
    config = load_config(root)
    for record_path in sorted((root / ".paperflow/data/papers").glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        try:
            rendered.append(str(render_uid(config, str(record["paper_uid"]))))
        except RuntimeError as exc:
            manual_review.append({"paper_uid": str(record["paper_uid"]), "error": str(exc)})

    result = {
        **plan,
        "dry_run": False,
        "status": "applied-with-manual-review" if manual_review else "applied",
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "moves": migration.get("moves", []),
        "applied": migration.get("applied", 0),
        "changed_links": changed_links,
        "rendered": rendered,
        "manual_review": manual_review,
        "synchronized_layers": synchronized_layers,
    }

    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    return result
