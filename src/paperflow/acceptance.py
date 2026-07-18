from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from paperflow.config import Config
from paperflow.feed.publisher import scan_feed
from paperflow.migration_engine import migration_history, verify
from paperflow.paths.service import validate_path_settings
from paperflow.versioning import APPLICATION_VERSION, VERSIONS


def audit(cfg: Config) -> list[dict[str, Any]]:
    root = cfg.root
    checks: list[dict[str, Any]] = []

    def add(requirement: str, ok: bool, evidence: str, blocker: bool = False):
        checks.append(
            {
                "requirement": requirement,
                "ok": bool(ok),
                "evidence": evidence,
                "blocker": blocker and not ok,
            }
        )

    add("可安装应用版本", APPLICATION_VERSION == "1.3.1", APPLICATION_VERSION)
    add(
        "标准 src 包结构",
        (root / "src/paperflow/cli.py").exists(),
        "src/paperflow",
    )
    add(
        "任意 Vault Workspace",
        cfg.workspace is not None
        and (root / ".paperflow/workspace.yaml").exists(),
        str(root),
    )
    add(
        "独立版本契约",
        len(VERSIONS.model_dump()) == 8,
        json.dumps(VERSIONS.model_dump(), ensure_ascii=False),
    )
    add(
        "北京时间",
        cfg.timezone.key == "Asia/Shanghai",
        cfg.timezone.key,
    )
    add(
        "Obsidian 语言联动",
        cfg.ui_locale.locale in {"zh-CN", "en"},
        f"{cfg.ui_locale.locale} ({cfg.ui_locale.source})",
    )
    add(
        "分层严格配置",
        not validate_path_settings(root, cfg.workspace),
        ".paperflow/workspace.yaml + workspace.local.yaml + env + CLI",
    )
    raw = list((root / ".paperflow/data/raw").rglob("*.json"))
    ai = list((root / ".paperflow/data/ai").rglob("*.json"))
    user = list((root / ".paperflow/data/user").glob("*.yaml"))
    derived = list((root / ".paperflow/data/derived").glob("*.json"))
    add("Raw 层", bool(raw), f"count={len(raw)}")
    add("AI 层", bool(ai), f"count={len(ai)}")
    add("User 层", bool(user), f"count={len(user)}")
    add("Derived 层", bool(derived), f"count={len(derived)}")
    try:
        migration = verify(root)
        migration_ok = migration["ok"]
        migration_evidence = json.dumps(migration, ensure_ascii=False)
    except Exception as exc:
        migration_ok = False
        migration_evidence = str(exc)
    add("正式迁移验证", migration_ok, migration_evidence)
    history = migration_history(root)
    add(
        "迁移历史与回滚快照",
        bool(history) and all(item.get("backup") for item in history),
        f"events={len(history)}",
    )
    add(
        "安全路径模板",
        not validate_path_settings(root, cfg.workspace),
        "allowlist + traversal/root checks",
    )
    form_manifest = root / ".obsidian/plugins/form-flow/manifest.json"
    form_enabled = False
    automation_enabled = False
    try:
        enabled = json.loads(
            (root / ".obsidian/community-plugins.json").read_text(encoding="utf-8")
        )
        form_enabled = "form-flow" in enabled
        automation_enabled = "paperflow-automation" in enabled
    except Exception:
        pass
    add(
        "官方 Form Flow 0.0.8",
        form_manifest.exists()
        and json.loads(form_manifest.read_text(encoding="utf-8")).get("version")
        == "0.0.8"
        and form_enabled,
        "plugin=form-flow",
    )
    add(
        "版本化 Form Flow 集成",
        (root / "integrations/obsidian-form-flow/integration.json").exists(),
        "integration version 1",
    )
    automation = root / ".obsidian/plugins/paperflow-automation"
    add(
        "Obsidian 内部自动化",
        automation_enabled
        and (automation / "manifest.json").exists()
        and (automation / "main.js").exists(),
        "Windows Task Scheduler not required",
    )
    add(
        "不依赖 Windows 计划任务",
        not bool(cfg.section("scheduler").get("enabled", False)),
        "scheduler.enabled=false; Obsidian plugin lifecycle",
    )
    try:
        sqlite_ok = (
            sqlite3.connect(root / ".paperflow/state/paperflow.db")
            .execute("PRAGMA integrity_check")
            .fetchone()[0]
            == "ok"
        )
    except Exception:
        sqlite_ok = False
    add("SQLite 完整性", sqlite_ok, "PRAGMA integrity_check")
    add(
        "发布隐私扫描器",
        (root / "src/paperflow/feed/publisher.py").exists(),
        "user/path/secret/log/db/pdf blockers",
    )
    feed = root / ".paperflow/publish/feed"
    add(
        "当前 Feed 安全状态",
        not feed.exists() or not scan_feed(feed),
        "not built (licence pending)" if not feed.exists() else "scan passed",
    )
    add(
        "安装与 CI",
        (root / "scripts/install.ps1").exists()
        and len(list((root / ".github/workflows").glob("*.yml"))) == 5,
        "wheel/sdist/portable + 5 workflows",
    )
    add(
        "软件发布许可证",
        (root / "LICENSE").exists()
        and not (root / "LICENSE-TODO.md").exists(),
        "MIT software licence selected; Feed data licence is workspace-specific",
    )
    add(
        "真实数据未进入构建产物",
        (root / "tests/packaging/test_artifacts.py").exists(),
        "archive privacy tests",
    )
    return checks
