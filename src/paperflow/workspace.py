from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from ruamel.yaml import YAML

from paperflow.versioning import VERSIONS, check_schema_version


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceVersions(StrictModel):
    workspace: int = VERSIONS.workspace_schema_version
    raw: int = VERSIONS.raw_data_schema_version
    ai: int = VERSIONS.ai_analysis_schema_version
    user: int = VERSIONS.user_data_schema_version
    feed: int = VERSIONS.public_feed_schema_version
    templates: int = VERSIONS.template_bundle_version
    form_flow: int = VERSIONS.form_flow_integration_version
    annotations: int = VERSIONS.annotation_schema_version
    community: int = VERSIONS.community_data_schema_version


class PathRule(StrictModel):
    root: str
    template: str = ""

    @field_validator("root")
    @classmethod
    def relative_root(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or re.match(r"^[A-Za-z]:", value):
            raise ValueError("must be relative to the Vault")
        if ".." in candidate.parts:
            raise ValueError("must not contain parent traversal")
        return value.replace("\\", "/").rstrip("/")


class WorkspacePaths(StrictModel):
    raw_metadata: PathRule = PathRule(
        root=".paperflow/data/raw",
        template="{{source}}/{{paper_id}}/v{{version}}.json",
    )
    ai_analysis: PathRule = PathRule(
        root=".paperflow/data/ai",
        template="{{analysis_profile}}/{{paper_id}}/v{{version}}/{{analysis_id}}.json",
    )
    user_data: PathRule = PathRule(
        root=".paperflow/data/user",
        template="{{paper_id}}.yaml",
    )
    derived_data: PathRule = PathRule(root=".paperflow/data/derived")
    pdf: PathRule = PathRule(
        root="80 Attachments/Papers",
        template="{{year}}/{{paper_id}}/v{{version}}.pdf",
    )
    note: PathRule = PathRule(
        root="10 Papers",
        template="{{year}}/{{paper_id}}.md",
    )
    base: PathRule = PathRule(root="00 Dashboard/Bases")
    dashboard: PathRule = PathRule(root="00 Dashboard")
    daily_brief: PathRule = PathRule(
        root="40 Daily Briefs",
        template="{{date}}.md",
    )
    inbox: PathRule = PathRule(root="50 Inbox/Paper Requests")
    processed_inbox: PathRule = PathRule(root="50 Inbox/Processed Requests")
    failed_inbox: PathRule = PathRule(root="50 Inbox/Failed Imports")
    manual_review: PathRule = PathRule(root="50 Inbox/Manual Review")
    annotation_note: PathRule = PathRule(
        root="60 Annotations",
        template="{{year}}/{{paper_id}}/{{annotation_id}}.annotation.md",
    )
    paper_review: PathRule = PathRule(
        root="60 Reviews",
        template="{{year}}/{{paper_id}}.review.md",
    )
    community_note: PathRule = PathRule(
        root="70 Community",
        template="{{year}}/{{paper_id}}.community.md",
    )
    user_annotations: PathRule = PathRule(
        root=".paperflow/data/user/annotations",
        template="{{paper_id}}/{{annotation_id}}.json",
    )
    community_cache: PathRule = PathRule(
        root=".paperflow/data/community/subscriptions"
    )
    community_outbox: PathRule = PathRule(
        root=".paperflow/data/community/outbox"
    )
    cache: PathRule = PathRule(root=".paperflow/cache")
    logs: PathRule = PathRule(root=".paperflow/logs")
    backups: PathRule = PathRule(root=".paperflow/backups")
    state: PathRule = PathRule(root=".paperflow/state")


class PathTemplateSettings(StrictModel):
    missing_value: str = "Unclassified"
    collision_policy: Literal["append_id", "error"] = "append_id"
    preserve_old_path: bool = True
    max_path_length: int = Field(default=240, ge=80, le=1024)


class ProviderConfig(StrictModel):
    executable: str
    model: str = ""
    profile: str = ""
    reasoning_effort: str = ""
    sandbox: Literal["read-only"] = "read-only"
    permission_mode: Literal["restricted"] = "restricted"
    timeout_seconds: int = Field(default=1800, ge=1, le=14400)
    extra_args: list[str] = Field(default_factory=list)
    browser_executable: str = ""
    browser_profile_dir: str = ""
    base_url: str = "https://chatgpt.com/"
    allow_pdf_upload: bool = False
    model_preference: list[str] = Field(default_factory=list)


class AIProfile(StrictModel):
    provider: Literal["codex", "claude", "chatgpt-web", "mock"]
    model: str = ""
    timeout_seconds: int = Field(default=1800, ge=1, le=14400)
    reasoning_effort: Literal["", "low", "medium", "high", "xhigh", "max"] = ""
    fallback_profile: str = ""
    reuse_feed_analysis: bool = True
    reanalyze_when: Literal[
        "identity-changed", "never", "always"
    ] = "identity-changed"


class AISettings(StrictModel):
    providers: dict[str, ProviderConfig]
    profiles: dict[str, AIProfile]
    triage_profile: str = "triage"
    full_analysis_profile: str = "full_analysis"
    reanalysis_profile: str = "reanalysis"


class DiscoverySettings(StrictModel):
    enabled: bool = True
    profile: str = "embodied-intelligence"
    lookback_days: int = Field(default=3, ge=1, le=365)
    max_candidates: int = Field(default=100, ge=1, le=10000)
    max_full_analyses_per_run: int = Field(default=10, ge=0, le=1000)
    relevance_threshold: float = Field(default=3.2, ge=0, le=5)
    process_updated_versions: bool = True


class DownloadSettings(StrictModel):
    enabled: bool = True
    source: bool = False
    max_pdf_size_mb: int = Field(default=100, ge=1, le=2048)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    max_retries: int = Field(default=3, ge=0, le=20)
    request_interval_seconds: float = Field(default=3, ge=0)


class VisualSettings(StrictModel):
    selection_mode: Literal["adaptive"] = "adaptive"
    quality_threshold: float = Field(default=48.0, ge=0, le=200)
    safety_max_assets: int = Field(default=12, ge=0, le=50)


class RelationshipSettings(StrictModel):
    semantic_threshold: float = Field(default=0.35, ge=0, le=1)
    max_semantic_links: int = Field(default=8, ge=0, le=100)
    entity_types: list[Literal["topic", "method", "dataset", "author"]] = Field(
        default_factory=lambda: ["topic", "method", "dataset"]
    )


class SyncCompatibilitySettings(StrictModel):
    enabled: bool = True
    settle_seconds: int = Field(default=3, ge=0, le=300)
    refuse_conflict_files: bool = True


class ObsidianBasesSettings(StrictModel):
    enabled: bool = True
    root: str = "00 Dashboard/Bases"
    paper_source_folder: str = "10 Papers"
    enabled_views: list[str] = Field(
        default_factory=lambda: [
            "all",
            "high_value_unread",
            "reading_queue",
            "reproduction_queue",
            "requests",
        ]
    )


class ObsidianSettings(StrictModel):
    install_form_flow: bool = True
    create_bases: bool = True
    enable_daily_automation: bool = True
    daily_local_time: str = "08:00"
    inbox_interval_minutes: int = Field(default=5, ge=1, le=1440)
    catch_up_after_missed_run: bool = True
    bases: ObsidianBasesSettings = ObsidianBasesSettings()


class PublishingSettings(StrictModel):
    enabled: bool = False
    feed_id: str = ""
    name: str = ""
    publisher_name: str = ""
    publisher_url: str = ""
    repository_url: str = ""
    branch: str = "main"
    include_raw_metadata: bool = True
    include_ai_analysis: bool = True
    include_extracted_text: bool = False
    include_pdf_files: bool = False
    include_rendered_notes: bool = False
    data_license: str = ""
    pdf_policy: Literal["link-only", "include-when-licensed"] = "link-only"
    include_community_contributions: bool = False


class Subscription(StrictModel):
    name: str
    url: str
    branch: str = "main"
    enabled: bool = True
    trust: Literal["metadata-only", "metadata-and-ai", "disabled"] = "metadata-and-ai"
    priority: int = Field(default=50, ge=0, le=100)
    auto_download_pdf: bool = True
    auto_render_notes: bool = True
    capabilities: list[Literal["raw", "ai", "community"]] = Field(
        default_factory=lambda: ["raw", "ai"]
    )


class SubscriptionSettings(StrictModel):
    sources: list[Subscription] = Field(default_factory=list)


class UpdateSettings(StrictModel):
    repository_url: str = "https://github.com/threeyang3/PaperRead"
    channel: Literal["stable"] = "stable"
    auto_check: bool = True
    auto_stage: bool = True
    require_confirm_apply: bool = True


class AnalysisSelection(StrictModel):
    policy: Literal[
        "prefer-local",
        "publisher-priority",
        "newest-compatible",
        "highest-confidence",
        "manual",
    ] = "prefer-local"
    prefer_local: bool = True
    minimum_schema_version: int = 1
    minimum_confidence: float = Field(default=0.6, ge=0, le=1)


class AnnotationSettings(StrictModel):
    adapter: Literal["pdf-plus", "native", "local", "legacy"] = "pdf-plus"
    direct_pdf_editing: bool = False
    reanchor_fuzzy_threshold: float = Field(default=0.86, ge=0, le=1)


class CommunitySettings(StrictModel):
    enabled: bool = True
    publish_enabled: bool = False
    maximum_quote_characters: int = Field(default=500, ge=0, le=500)
    default_license: str = ""
    show_small_sample_warning_below: int = Field(default=5, ge=1, le=100)


class WorkspaceSettings(StrictModel):
    workspace_name: str = "PaperFlow Workspace"
    versions: WorkspaceVersions = WorkspaceVersions()
    timezone: str = "Asia/Shanghai"
    language: str = "auto"
    language_fallback: str = "zh-CN"
    research_profile: str = "embodied-intelligence"
    paths: WorkspacePaths = WorkspacePaths()
    path_templates: PathTemplateSettings = PathTemplateSettings()
    ai: AISettings
    discovery: DiscoverySettings = DiscoverySettings()
    downloads: DownloadSettings = DownloadSettings()
    visuals: VisualSettings = VisualSettings()
    relationships: RelationshipSettings = RelationshipSettings()
    sync_compatibility: SyncCompatibilitySettings = SyncCompatibilitySettings()
    obsidian: ObsidianSettings = ObsidianSettings()
    publishing: PublishingSettings = PublishingSettings()
    subscriptions: SubscriptionSettings = SubscriptionSettings()
    updates: UpdateSettings = UpdateSettings()
    analysis_selection: AnalysisSelection = AnalysisSelection()
    annotations: AnnotationSettings = AnnotationSettings()
    community: CommunitySettings = CommunitySettings()

    @field_validator("timezone")
    @classmethod
    def timezone_required(cls, value: str) -> str:
        ZoneInfo(value)
        return value


def default_workspace_dict() -> dict[str, Any]:
    return {
        "workspace_name": "PaperFlow Workspace",
        "versions": {
            "workspace": VERSIONS.workspace_schema_version,
            "raw": VERSIONS.raw_data_schema_version,
            "ai": VERSIONS.ai_analysis_schema_version,
            "user": VERSIONS.user_data_schema_version,
            "feed": VERSIONS.public_feed_schema_version,
            "templates": VERSIONS.template_bundle_version,
            "form_flow": VERSIONS.form_flow_integration_version,
            "annotations": VERSIONS.annotation_schema_version,
            "community": VERSIONS.community_data_schema_version,
        },
        "timezone": "Asia/Shanghai",
        "language": "auto",
        "language_fallback": "zh-CN",
        "research_profile": "embodied-intelligence",
        "paths": WorkspacePaths().model_dump(mode="json"),
        "path_templates": PathTemplateSettings().model_dump(mode="json"),
        "ai": {
            "providers": {
                "codex": {
                    "executable": "codex",
                    "model": "",
                    "profile": "",
                    "reasoning_effort": "",
                    "sandbox": "read-only",
                    "permission_mode": "restricted",
                    "timeout_seconds": 1800,
                    "extra_args": [],
                },
                "claude": {
                    "executable": "claude",
                    "model": "",
                    "profile": "",
                    "reasoning_effort": "",
                    "sandbox": "read-only",
                    "permission_mode": "restricted",
                    "timeout_seconds": 1800,
                    "extra_args": [],
                },
                "mock": {
                    "executable": "mock",
                    "model": "deterministic-v1",
                    "sandbox": "read-only",
                    "permission_mode": "restricted",
                    "timeout_seconds": 30,
                    "extra_args": [],
                },
                "chatgpt-web": {
                    "executable": "msedge",
                    "model": "",
                    "sandbox": "read-only",
                    "permission_mode": "restricted",
                    "timeout_seconds": 3600,
                    "extra_args": [],
                    "browser_executable": "",
                    "browser_profile_dir": "%LOCALAPPDATA%/PaperFlow/ChatGPTWeb",
                    "base_url": "https://chatgpt.com/",
                    "allow_pdf_upload": False,
                    "model_preference": ["Pro", "Thinking", "GPT-5.6", "GPT-5"],
                },
            },
            "profiles": {
                "triage": {
                    "provider": "codex",
                    "model": "",
                    "timeout_seconds": 300,
                    "reasoning_effort": "low",
                    "fallback_profile": "",
                    "reuse_feed_analysis": True,
                    "reanalyze_when": "identity-changed",
                },
                "full_analysis": {
                    "provider": "codex",
                    "model": "",
                    "timeout_seconds": 1800,
                    "reasoning_effort": "high",
                    "fallback_profile": "fallback_analysis",
                    "reuse_feed_analysis": True,
                    "reanalyze_when": "identity-changed",
                },
                "fallback_analysis": {
                    "provider": "claude",
                    "model": "",
                    "timeout_seconds": 1800,
                    "reasoning_effort": "",
                    "fallback_profile": "",
                    "reuse_feed_analysis": True,
                    "reanalyze_when": "identity-changed",
                },
                "web_analysis": {
                    "provider": "chatgpt-web",
                    "model": "",
                    "timeout_seconds": 3600,
                    "reasoning_effort": "",
                    "fallback_profile": "",
                    "reuse_feed_analysis": True,
                    "reanalyze_when": "identity-changed",
                },
                "reanalysis": {
                    "provider": "claude",
                    "model": "",
                    "timeout_seconds": 2400,
                    "reasoning_effort": "",
                    "fallback_profile": "",
                    "reuse_feed_analysis": True,
                    "reanalyze_when": "identity-changed",
                },
            },
            "triage_profile": "triage",
            "full_analysis_profile": "full_analysis",
            "reanalysis_profile": "reanalysis",
        },
        "discovery": DiscoverySettings().model_dump(mode="json"),
        "downloads": DownloadSettings().model_dump(mode="json"),
        "visuals": VisualSettings().model_dump(mode="json"),
        "relationships": RelationshipSettings().model_dump(mode="json"),
        "sync_compatibility": SyncCompatibilitySettings().model_dump(mode="json"),
        "obsidian": ObsidianSettings().model_dump(mode="json"),
        "publishing": PublishingSettings().model_dump(mode="json"),
        "subscriptions": SubscriptionSettings().model_dump(mode="json"),
        "updates": UpdateSettings().model_dump(mode="json"),
        "analysis_selection": AnalysisSelection().model_dump(mode="json"),
        "annotations": AnnotationSettings().model_dump(mode="json"),
        "community": CommunitySettings().model_dump(mode="json"),
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def _environment_overlay(prefix: str = "PAPERFLOW__") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, raw_value in os.environ.items():
        if not name.startswith(prefix):
            continue
        parts = [part.lower() for part in name[len(prefix) :].split("__") if part]
        if not parts:
            continue
        try:
            value: Any = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        cursor = result
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return result


def resolve_vault_root(vault: Path | None = None) -> Path:
    if vault is not None:
        return vault.expanduser().resolve()
    env_vault = os.environ.get("PAPERFLOW_VAULT")
    if env_vault:
        return Path(env_vault).expanduser().resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".paperflow/workspace.yaml").exists() or (candidate / "paperflow.yaml").exists():
            return candidate
    raise FileNotFoundError(
        "No PaperFlow Workspace found. Use `paperflow init --vault <path>` "
        "or set PAPERFLOW_VAULT."
    )


def load_workspace_settings(
    vault: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> tuple[Path, WorkspaceSettings]:
    root = resolve_vault_root(vault)
    workspace_file = root / ".paperflow/workspace.yaml"
    local_file = root / ".paperflow/workspace.local.yaml"
    if not workspace_file.exists():
        raise FileNotFoundError(
            f"{workspace_file} does not exist; run `paperflow init --vault \"{root}\"` "
            "or migrate this legacy Workspace."
        )
    data = default_workspace_dict()
    data = _deep_merge(data, _load_yaml(workspace_file))
    data = _deep_merge(data, _load_yaml(local_file))
    data = _deep_merge(data, _environment_overlay())
    data = _deep_merge(data, cli_overrides or {})
    try:
        settings = WorkspaceSettings.model_validate(data)
    except ValidationError as exc:
        lines = ["Workspace configuration is invalid:"]
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"])
            lines.append(
                f"- field={field}; value={error.get('input')!r}; "
                f"error={error['msg']}; fix=edit `.paperflow/workspace.yaml` "
                "or `.paperflow/workspace.local.yaml`."
            )
        raise ValueError("\n".join(lines)) from exc
    check_schema_version(
        "workspace",
        settings.versions.workspace,
        VERSIONS.workspace_schema_version,
    )
    return root, settings


def dump_yaml(path: Path, value: dict[str, Any]) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    path.parent.mkdir(parents=True, exist_ok=True)
    from io import StringIO

    stream = StringIO()
    yaml.dump(value, stream)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(stream.getvalue(), encoding="utf-8")
    temporary.replace(path)


def init_workspace(
    vault: Path,
    *,
    config_file: Path | None = None,
    overrides: dict[str, Any] | None = None,
    force: bool = False,
) -> Path:
    root = vault.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    workspace_file = root / ".paperflow/workspace.yaml"
    if workspace_file.exists() and not force:
        raise FileExistsError(
            f"{workspace_file} already exists; use `paperflow workspace info` "
            "or explicitly request a repair."
        )
    data = default_workspace_dict()
    if config_file:
        data = _deep_merge(data, _load_yaml(config_file))
    if overrides:
        data = _deep_merge(data, overrides)
    settings = WorkspaceSettings.model_validate(data)
    dump_yaml(workspace_file, settings.model_dump(mode="json"))
    local_file = root / ".paperflow/workspace.local.yaml"
    if not local_file.exists():
        dump_yaml(local_file, {"ai": {"providers": {}}})
    for rule in settings.paths.model_dump().values():
        (root / rule["root"]).mkdir(parents=True, exist_ok=True)
    for folder in ["20 Topics", "30 Reading Notes", "90 System/Forms", "90 System/Templates", "90 System/Taxonomy"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return workspace_file


def _distribution_resource(relative: str) -> Path:
    repository = Path(__file__).resolve().parents[2] / relative
    if repository.exists():
        return repository
    from importlib.resources import files

    return Path(str(files("paperflow").joinpath("resources", relative)))


def install_workspace_resources(
    root: Path, settings: WorkspaceSettings
) -> dict[str, Any]:
    """Install versioned schemas/templates without replacing user edits."""
    actions: list[dict[str, str]] = []
    mappings = [
        (
            _distribution_resource("schemas"),
            root / ".paperflow/schemas",
            True,
        ),
        (
            _distribution_resource("templates"),
            root / "90 System/Templates",
            False,
        ),
        (
            _distribution_resource("prompts"),
            root / ".paperflow/prompts",
            True,
        ),
    ]
    for source_root, destination_root, managed in mappings:
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(source_root)
            target = destination_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
                actions.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "action": "installed",
                    }
                )
            elif target.read_bytes() == source.read_bytes():
                actions.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "action": "unchanged",
                    }
                )
            elif managed:
                stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y%m%d-%H%M%S"
                )
                backup = (
                    root
                    / ".paperflow/backups"
                    / f"resources-{stamp}"
                    / target.relative_to(root)
                )
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                temporary = target.with_name(target.name + ".tmp")
                shutil.copy2(source, temporary)
                temporary.replace(target)
                actions.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "action": "upgraded",
                        "backup": backup.relative_to(root).as_posix(),
                    }
                )
            else:
                candidate = target.with_name(target.name + ".new")
                shutil.copy2(source, candidate)
                actions.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "action": "merge-review",
                        "candidate": candidate.relative_to(root).as_posix(),
                    }
                )
    if settings.obsidian.create_bases:
        from paperflow.obsidian.bases import rebuild_bases

        rebuild_bases(
            root,
            base_root=settings.obsidian.bases.root,
            paper_root=settings.obsidian.bases.paper_source_folder,
            request_roots=(
                settings.paths.inbox.root,
                settings.paths.processed_inbox.root,
                settings.paths.failed_inbox.root,
            ),
        )
    automation = {"enabled": False}
    if settings.obsidian.enable_daily_automation:
        automation = _install_automation_plugin(root, settings)
    return {
        "actions": actions,
        "bases_created": settings.obsidian.create_bases,
        "automation": automation,
    }


def _install_automation_plugin(
    root: Path, settings: WorkspaceSettings
) -> dict[str, Any]:
    bundle = _distribution_resource(
        "integrations/obsidian-paperflow-automation"
    )
    target_root = root / ".obsidian/plugins/paperflow-automation"
    target_root.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(
        (bundle / "integration.json").read_text(encoding="utf-8")
    )
    state_path = (
        root
        / ".paperflow/state/integrations/paperflow-automation.json"
    )
    previous_hashes: dict[str, str] = {}
    if state_path.exists():
        previous_hashes = json.loads(
            state_path.read_text(encoding="utf-8")
        ).get("installed_hashes", {})
    beijing_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    stamp = beijing_now.strftime("%Y%m%d-%H%M%S")
    backup_root = (
        root
        / ".paperflow/backups"
        / f"paperflow-automation-{stamp}"
    )
    installed_hashes: dict[str, str] = {}
    actions = []
    for name in [
        "main.js",
        "reading-workspace.js",
        "manifest.json",
        "styles.css",
        "scheduler-core.js",
        "README.md",
    ]:
        source = bundle / name
        target = target_root / name
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if not target.exists():
            shutil.copy2(source, target)
            installed_hashes[name] = source_hash
            actions.append({"file": name, "action": "installed"})
        elif target.read_bytes() == source.read_bytes():
            installed_hashes[name] = source_hash
            actions.append({"file": name, "action": "unchanged"})
        elif (
            previous_hashes.get(name)
            == hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            backup = backup_root / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            temporary = target.with_name(target.name + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(target)
            installed_hashes[name] = source_hash
            actions.append(
                {
                    "file": name,
                    "action": "upgraded",
                    "backup": backup.relative_to(root).as_posix(),
                }
            )
        else:
            candidate = target.with_name(target.name + ".new")
            shutil.copy2(source, candidate)
            actions.append(
                {"file": name, "action": "merge-review", "candidate": candidate.name}
            )
    data_path = target_root / "data.json"
    if not data_path.exists():
        default_data = json.loads(
            (bundle / "default-data.json").read_text(encoding="utf-8")
        )
        default_data["dailyLocalTime"] = settings.obsidian.daily_local_time
        default_data[
            "inboxIntervalMinutes"
        ] = settings.obsidian.inbox_interval_minutes
        default_data[
            "catchUpDailyAfterStartup"
        ] = settings.obsidian.catch_up_after_missed_run
        temporary = data_path.with_name(data_path.name + ".tmp")
        temporary.write_text(
            json.dumps(default_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(data_path)
        actions.append({"file": "data.json", "action": "initialized"})
    else:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        runtime = data.pop("runtime", None)
        if runtime is not None:
            backup = backup_root / "data.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_path, backup)
            runtime_path = root / ".paperflow/runtime/plugin-state.json"
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            if not runtime_path.exists():
                runtime_path.write_text(
                    json.dumps(runtime, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            temporary = data_path.with_name(data_path.name + ".tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(data_path)
            actions.append(
                {
                    "file": "data.json",
                    "action": "split-runtime-state",
                    "backup": backup.relative_to(root).as_posix(),
                }
            )
    enabled_path = root / ".obsidian/community-plugins.json"
    enabled = []
    if enabled_path.exists():
        enabled = json.loads(enabled_path.read_text(encoding="utf-8"))
    if "paperflow-automation" not in enabled:
        enabled.append("paperflow-automation")
        enabled_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = enabled_path.with_name(enabled_path.name + ".tmp")
        temporary.write_text(
            json.dumps(enabled, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(enabled_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "integration": "paperflow-automation",
        "integration_version": metadata["integration_version"],
        "plugin_version": metadata["version"],
        "updated_at": beijing_now.isoformat(),
        "installed_hashes": installed_hashes,
        "actions": actions,
    }
    temporary_state = state_path.with_name(state_path.name + ".tmp")
    temporary_state.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_state.replace(state_path)
    return {"enabled": True, "actions": actions, "state": state}


def export_example(path: Path) -> Path:
    data = default_workspace_dict()
    data["publishing"]["enabled"] = False
    data["publishing"]["data_license"] = ""
    data["subscriptions"]["sources"] = []
    dump_yaml(path, data)
    return path


def backup_workspace_config(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for relative in [
        ".paperflow/workspace.yaml",
        ".paperflow/workspace.local.yaml",
        "paperflow.yaml",
    ]:
        source = root / relative
        if source.exists():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
