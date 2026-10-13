"""Explicit, local-only first-run initialization for the Obsidian adapter."""
from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from paperflow.locking import FileLock
from paperflow.obsidian.bases import definitions, validate_bases
from paperflow.paths.service import validate_path_settings
from paperflow.security.paths import resolve_under
from paperflow.workspace import (
    _distribution_resource, default_workspace_dict, init_workspace,
    install_workspace_resources, load_workspace_settings,
)
from paperflow.workspace_ops import create_workspace_backup


def setup_plan(vault: Path) -> dict:
    root = vault.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Open an existing local Obsidian vault first")
    resolve_under(root, ".paperflow")
    resolve_under(root, ".obsidian")
    resolve_under(root, ".paperflow", "workspace.yaml")
    if (root / ".paperflow/workspace.yaml").exists():
        _, settings = load_workspace_settings(root)
        return {"status": "ready", "vault": str(root), "changes": [],
                "errors": validate_path_settings(root, settings) + validate_bases(
                    root, base_root=settings.obsidian.bases.root,
                    paper_root=settings.obsidian.bases.paper_source_folder), "dry_run": True}
    targets = {".paperflow/workspace.yaml", ".paperflow/workspace.local.yaml",
               "00 Dashboard/PaperFlow Start.md"}
    resource_hashes = {}
    for source, destination in (("schemas", ".paperflow/schemas"),
                                ("prompts", ".paperflow/prompts"),
                                ("templates", "90 System/Templates"),
                                ("taxonomy", "90 System/Taxonomy")):
        directory = _distribution_resource(source)
        targets.update(f"{destination}/{p.relative_to(directory).as_posix()}"
                       for p in directory.rglob("*") if p.is_file())
        resource_hashes.update({f"{destination}/{p.relative_to(directory).as_posix()}":
                               hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in directory.rglob("*") if p.is_file()})
    targets.update(f"00 Dashboard/Bases/{name}" for name in definitions())
    changes, conflicts = [], []
    for relative in sorted(targets):
        target = resolve_under(root, *Path(relative).parts)
        if target.exists():
            conflicts.append(relative)
        for parent in target.parents:
            if parent == root:
                break
            if parent.exists() and not parent.is_dir():
                conflicts.append(parent.relative_to(root).as_posix())
        changes.append(relative)
    folders = sorted({p["root"] for p in default_workspace_dict()["paths"].values()})
    for folder in folders:
        target = resolve_under(root, *Path(folder).parts)
        if target.exists() and not target.is_dir():
            conflicts.append(folder)
    plan = {"status": "conflict" if conflicts else "new", "vault": str(root),
            "changes": changes, "folders": folders, "conflicts": sorted(set(conflicts)),
            "resource_hashes": resource_hashes,
            "automation_enabled": False, "network_changes": 0, "dry_run": True}
    plan["digest"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def initialize(vault: Path, digest: str) -> dict:
    root = vault.expanduser().resolve()
    plan = setup_plan(root)
    if plan["status"] == "ready":
        return {**plan, "initialized": False}
    if plan["status"] != "new" or not digest or digest != plan["digest"]:
        raise ValueError("Initialization preview changed or has conflicts; preview again")
    with FileLock(root / ".paperflow/runtime/onboarding.lock"):
        if setup_plan(root) != plan:
            raise ValueError("Vault changed after preview; preview again")
        backup = create_workspace_backup(root, label=f"pre-onboarding-{uuid.uuid4().hex[:8]}")
        written: dict[Path, bytes] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="stage-", dir=backup) as directory:
                stage = Path(directory).resolve()
                if not stage.is_relative_to(root):
                    raise ValueError("Initialization stage escaped the workspace")
                init_workspace(stage, overrides={"obsidian": {"enable_daily_automation": False},
                                                "ai": {"profiles": {"full_analysis": {"fallback_profile": ""}}}})
                _, settings = load_workspace_settings(stage)
                resources = install_workspace_resources(stage, settings)
                start_relative = "00 Dashboard/PaperFlow Start.md"
                (stage / start_relative).write_text("# PaperFlow\n\n资料库已初始化。\n\n"
                    "- 从 PaperFlow 控制中心配置 AI 并导入第一篇论文。\n"
                    "- 在 Zotero 设置 → PaperFlow 中连接本机 Core。\n"
                    "- 安装并启用 Form Flow，以使用手动论文录入表单。\n"
                    "- 自动调度暂未启用；请完成配置后再启用。\n", encoding="utf-8")
                errors = validate_path_settings(stage, settings) + validate_bases(stage)
                if errors:
                    raise ValueError("; ".join(errors))
                if setup_plan(root) != plan:
                    raise ValueError("Vault changed during initialization; preview again")
                # Publish the Workspace marker last; no existing file is overwritten.
                ordered = sorted(plan["changes"], key=lambda name: name == ".paperflow/workspace.yaml")
                for relative in ordered:
                    target = resolve_under(root, *Path(relative).parts)
                    payload = (stage / relative).read_bytes()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        written[target] = payload
                        stream.write(payload)
        except Exception as exc:
            for target, payload in reversed(list(written.items())):
                if target.is_file() and payload.startswith(target.read_bytes()):
                    target.unlink()
            raise RuntimeError(f"Initialization failed; unchanged generated files removed. Backup: {backup}. {exc}") from exc
        _, settings = load_workspace_settings(root)
        start = root / "00 Dashboard/PaperFlow Start.md"
        from paperflow.obsidian.form_flow import integration_status
        form = integration_status(root)["plugin"]
        errors = validate_path_settings(root, settings) + validate_bases(root)
        return {"status": "initialized" if not errors else "needs-attention",
                "initialized": True, "vault": str(root), "backup": str(backup),
                "resources": resources, "errors": errors,
                "form_flow_installed": form["installed"], "automation_enabled": False,
                "network_changes": 0, "start_note": start.relative_to(root).as_posix()}


def prepare_form(vault: Path) -> dict:
    root = vault.expanduser().resolve()
    plan = setup_plan(root)
    if plan["status"] != "ready" or plan["errors"]:
        raise ValueError("Initialize and validate the workspace before preparing forms")
    from paperflow.obsidian.form_flow import integration_status, install_or_upgrade
    plugin = integration_status(root)["plugin"]
    if not plugin["installed"] or not plugin["compatible"]:
        return {"status": "plugin-required", "plugin_id": "form-flow", "minimum_version": "0.0.8"}
    if not plugin["enabled"]:
        return {"status": "plugin-disabled", "plugin_id": "form-flow"}
    backup = create_workspace_backup(root, label=f"pre-onboarding-form-{uuid.uuid4().hex[:8]}")
    form = install_or_upgrade(root, mode="install")
    conflicts = [item["path"] for item in form.get("actions", []) if item["action"] == "merge-review"]
    return {"status": "needs-attention" if conflicts else "prepared", "backup": str(backup),
            "form": form, "conflicts": conflicts}


def check_core(vault: Path) -> dict:
    """Verify a live, authenticated Core session for this workspace, without mutation."""
    from paperflow.zotero.core_service import read_session, read_pairing_token
    root = vault.expanduser().resolve()
    resolve_under(root, ".paperflow", "state", "zotero-core-session.json")
    resolve_under(root, ".paperflow", "runtime", "zotero-core-session.token")
    session = read_session(root) or {}
    base_url = str(session.get("base_url") or "")
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("No valid local Core session; start Core first")
    base_url = base_url.rstrip("/")
    token = read_pairing_token(root)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(base_url + "/health", timeout=3) as response:
            health = json.loads(response.read(65537))
        if not isinstance(health, dict) or health.get("service") != "paperflow-core" or health.get("status") != "ready" or not health.get("ok"):
            raise ValueError("Core is not ready")
        request = urllib.request.Request(base_url + "/jobs?limit=1", headers={"Authorization": f"Bearer {token}"})
        with opener.open(request, timeout=3) as response:
            jobs = json.loads(response.read(65537))
        if not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list):
            raise ValueError("Invalid authenticated Core response")
    except (OSError, ValueError) as exc:
        raise ValueError("Core connection could not be verified for this workspace") from exc
    return {"status": "verified", "base_url": base_url, "authenticated": True,
            "version": health.get("version"), "scheduler": health.get("scheduler")}
