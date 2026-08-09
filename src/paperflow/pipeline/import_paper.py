from __future__ import annotations
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any
from paperflow.ai.factory import make_adapter
from paperflow.ai.providers import make_provider
from paperflow.config import Config, ensure_layout
from paperflow.data.store import load_reusable_analysis, persist_layer_records
from paperflow.data.records import AnalysisIdentity
from paperflow.paths.templates import safe_component
from paperflow.paths.service import preview_record_paths
from paperflow.database import Database
from paperflow.models import PaperMetadata
from paperflow.logging_config import configure_logging
from paperflow.obsidian.frontmatter import read_note
from paperflow.obsidian.artifacts import ensure_user_note
from paperflow.obsidian.note_renderer import render_paper
from paperflow.sources.arxiv import ArxivSource
from paperflow.sources.url_parser import parse_input
from paperflow.sources.web import fetch_generic
from paperflow.clock import WorkspaceClock
from paperflow.utils import atomic_json, atomic_write, iso_utc, safe_slug, sha256_bytes
from paperflow.taxonomy import canonicalize_topics
from paperflow.text_quality import short_title
from .deduplicate import decide
from .download import download_pdf
from .extract import extract_pdf
from .resources import find_resource_links
from .visuals import refresh_record_visuals


def pending_analysis() -> dict[str, Any]:
    return {
        "ai_analysis_status": "pending", "ai_relevance_score": 0.0, "ai_relevance_reason": "", "ai_topic_primary": "", "ai_topics": [],
        "ai_method_family": [], "ai_task_types": [], "ai_robot_platforms": [], "ai_datasets": [], "ai_baselines": [],
        "ai_novelty_score": 0, "ai_novelty_confidence": 0.0, "ai_novelty_reason": "", "ai_completeness_score": 0,
        "ai_completeness_confidence": 0.0, "ai_completeness_reason": "", "ai_reproducibility_score": 0,
        "ai_reproducibility_confidence": 0.0, "ai_reproducibility_reason": "", "ai_overall_score": 0.0,
        "ai_overall_confidence": 0.0, "ai_recommendation": "待分析", "ai_summary_short": "尚未执行 AI 分析。",
        "ai_difficulty": "medium", "ai_math_level": "medium", "ai_code_level": "medium", "ai_estimated_reading_priority": 0,
        "sections": {},
    }


def _metadata(cfg: Config, value: str) -> PaperMetadata:
    parsed = parse_input(value)
    if parsed.kind == "arxiv":
        section = cfg.section("arxiv")
        cache_dir = cfg.root / ".paperflow/cache/arxiv" if cfg.section("retention").get("keep_raw_api_responses", True) else None
        return ArxivSource(section["timeout_seconds"], section["max_retries"], section["request_interval_seconds"], cache_dir=cache_dir).fetch(value)
    return fetch_generic(parsed, cfg.section("arxiv")["timeout_seconds"])


def _year_paths(cfg: Config, metadata: PaperMetadata) -> tuple[Path, Path, Path, Path]:
    ident = metadata.paper_arxiv_id or safe_slug(metadata.paper_uid.replace(":", "_"))
    year = str(metadata.paper_year or WorkspaceClock(str(cfg.timezone)).now().year)
    if cfg.workspace is not None:
        # Keep the importer on the same path-template contract as the
        # renderer/migration code.  The old importer bypassed the workspace
        # template and always created ``{paper_id}.md`` files, which made
        # papers added from Form Flow/subscriptions regress to ID-only names.
        preview = preview_record_paths(
            cfg.root,
            cfg.workspace,
            metadata.model_dump(mode="json"),
        )
        note_path = cfg.root / preview["note"]["new_path"]
        pdf_path = cfg.root / preview["pdf"]["new_path"]
    else:
        # Legacy paperflow.yaml workspaces do not have a WorkspaceSettings
        # object.  Still use a readable title fragment for newly imported
        # papers while retaining the arXiv ID suffix for uniqueness.
        title_fragment = safe_component(short_title(metadata.paper_title))
        note_path = cfg.path("paper_folder") / year / f"{title_fragment}-{ident}.md"
        pdf_path = cfg.path("pdf_folder") / year / ident / f"v{metadata.paper_arxiv_version}.pdf"
    return (
        note_path,
        pdf_path,
        cfg.root / ".paperflow/data/papers" / f"{safe_slug(metadata.paper_uid)}.json",
        cfg.root / ".paperflow/cache" / f"{safe_slug(metadata.paper_uid)}.txt",
    )


def import_paper(cfg: Config, value: str, *, priority: int = 3, topic: str = "", run_ai: bool = True, force: bool = False, favorite: bool = False, queued: bool = False, user_tags: list[str] | None = None, user_note: str = "", import_method: str = "manual", provider: str | None = None, metadata_override: PaperMetadata | None = None, reuse_local_assets: bool = False) -> dict[str, Any]:
    ensure_layout(cfg)
    db = Database(cfg.root / ".paperflow/state/paperflow.db")
    logger = configure_logging(cfg.root)
    job_id = str(uuid.uuid4())
    paper_uid = ""
    failure_checkpoint: tuple[Path, dict[str, Any]] | None = None
    preserve_existing_record = False
    try:
        db.set_import_job(job_id, paper_uid, "metadata_ready", "metadata")
        metadata = metadata_override or _metadata(cfg, value)
        paper_uid = metadata.paper_uid
        db.set_import_job(job_id, paper_uid, "metadata_ready", "metadata")
        logger.info("Metadata ready", extra={"run_id": job_id, "paper_uid": paper_uid, "stage": "metadata"})
        decision = decide(db, metadata, force)
        note_path, pdf_path, json_path, text_path = _year_paths(cfg, metadata)
        preserve_existing_record = json_path.exists()
        # An update must keep the currently selected note/PDF paths.  This is
        # important for user-authored notes and for workspaces migrated from
        # the former ID-only layout; only brand-new records use the readable
        # template above.
        if json_path.exists():
            try:
                existing_record = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing_record = {}
            existing_note = str(existing_record.get("note_path") or "").strip()
            existing_pdf = str(existing_record.get("paper_pdf_path") or "").strip()
            if existing_note:
                note_path = cfg.root / existing_note
            if existing_pdf:
                pdf_path = cfg.root / existing_pdf
        if decision.action == "skip" and json_path.exists():
            db.set_import_job(job_id, paper_uid, "completed", "deduplicate")
            logger.info("Existing paper skipped", extra={"run_id": job_id, "paper_uid": paper_uid, "stage": "deduplicate"})
            return {"status": "skipped", "paper_uid": metadata.paper_uid, "note_path": note_path.relative_to(cfg.root).as_posix()}
        if decision.action == "update" and json_path.exists():
            snapshots = cfg.root / ".paperflow/data/papers/versions"
            snapshots.mkdir(parents=True, exist_ok=True)
            snapshot = snapshots / f"{safe_slug(metadata.paper_uid)}-v{decision.existing_version}.json"
            shutil.copy2(json_path, snapshot)
            db.record_version(metadata.paper_uid, decision.existing_version, snapshot.relative_to(cfg.root).as_posix())
        content_hash = ""
        extraction = {"headings": [], "page_count": 0}
        if reuse_local_assets:
            if not json_path.exists():
                raise FileNotFoundError(
                    f"Local paper record is missing: {json_path}"
                )
            existing_record = json.loads(json_path.read_text(encoding="utf-8"))
            if not pdf_path.exists():
                raise FileNotFoundError(
                    f"Local PDF is missing: {pdf_path}"
                )
            content_hash = existing_record.get("system_content_hash") or sha256_bytes(
                pdf_path.read_bytes()
            )
            if text_path.exists():
                extraction = existing_record.get("extraction") or {
                    "headings": [],
                    "page_count": 0,
                }
            else:
                extraction = extract_pdf(pdf_path, text_path)
            db.set_import_job(job_id, paper_uid, "text_extracted", "local-assets")
        elif metadata.paper_pdf_url:
            db.set_import_job(job_id, paper_uid, "pdf_downloaded", "download")
            content_hash = download_pdf(metadata.paper_pdf_url, pdf_path, cfg.section("arxiv")["max_pdf_size_mb"], cfg.section("arxiv")["timeout_seconds"])
            db.set_import_job(job_id, paper_uid, "text_extracted", "extract")
            extraction = extract_pdf(pdf_path, text_path)
        else:
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(metadata.paper_abstract, encoding="utf-8")
            content_hash = sha256_bytes(metadata.paper_abstract.encode())
        extracted_text = text_path.read_text(encoding="utf-8", errors="replace")
        resource_links = find_resource_links(metadata.paper_abstract + "\n" + extracted_text)
        for key, value in resource_links.items():
            if value and not getattr(metadata, key):
                setattr(metadata, key, value)
        analysis = pending_analysis()
        used_provider = provider or cfg.section("analysis")["provider"]
        used_profile = (
            cfg.workspace.ai.full_analysis_profile
            if cfg.workspace
            else "full_analysis"
        )
        model = ""
        analyzed_at: str | None = None
        failure_checkpoint = (
            json_path,
            metadata.model_dump(mode="json")
            | analysis
            | {
                "paper_pdf_path": (
                    pdf_path.relative_to(cfg.root).as_posix()
                    if pdf_path.exists()
                    else ""
                ),
                "note_path": note_path.relative_to(cfg.root).as_posix(),
                "json_path": json_path.relative_to(cfg.root).as_posix(),
                "extraction": extraction,
                "system_content_hash": content_hash,
                "system_import_method": import_method,
                "system_imported_at": iso_utc(),
                "system_last_synced_at": iso_utc(),
                "system_pipeline_version": "0.1.0",
                "system_requires_manual_review": not bool(metadata.paper_pdf_url),
                "system_status": "failed",
                "system_error": "",
                "ai_analysis_provider": used_provider if run_ai else "",
                "ai_analysis_model": "",
                "ai_analysis_profile": used_profile if run_ai else "",
                "ai_analysis_prompt_version": PROMPT_VERSION if run_ai else "",
                "ai_analyzed_at": None,
            },
        )
        if run_ai:
            db.set_import_job(job_id, paper_uid, "analysis_running", "analysis")
            analysis_cfg = cfg.section("analysis")
            providers = [used_provider]
            fallback = analysis_cfg.get("fallback_provider")
            if fallback and fallback not in providers:
                providers.append(fallback)
            retries = int(analysis_cfg.get("retry_invalid_output", 0))
            last_error: Exception | None = None
            completed = False
            for candidate_provider in providers:
                for _attempt in range(retries + 1):
                    analysis_run_id = str(uuid.uuid4())
                    try:
                        if cfg.workspace:
                            profile_name = cfg.workspace.ai.full_analysis_profile
                            profile = cfg.workspace.ai.profiles[profile_name]
                            if candidate_provider != profile.provider:
                                matching = [
                                    (name, value)
                                    for name, value in cfg.workspace.ai.profiles.items()
                                    if value.provider == candidate_provider
                                ]
                                if not matching:
                                    raise ValueError(
                                        "No AI profile configured for fallback "
                                        f"provider {candidate_provider}"
                                    )
                                profile_name, profile = matching[0]
                            used_profile = profile_name
                            provider_config = cfg.workspace.ai.providers[
                                candidate_provider
                            ]
                            selected_model = profile.model or provider_config.model
                            identity = AnalysisIdentity(
                                provider=candidate_provider,
                                model=selected_model,
                                profile=profile_name,
                                prompt_version=PROMPT_VERSION,
                                source_content_hash=content_hash,
                            )
                            paper_id = safe_component(
                                (
                                    metadata.paper_arxiv_id
                                    or metadata.paper_uid
                                ).replace(":", "_")
                            )
                            stored = load_reusable_analysis(
                                cfg.root,
                                paper_id=paper_id,
                                source_version=metadata.paper_arxiv_version,
                                identity=identity,
                            )
                            if stored is not None:
                                analysis = stored["analysis"]
                                analyzed_at = str(
                                    stored.get("analyzed_at")
                                    or analysis.get("ai_analyzed_at")
                                    or ""
                                ) or None
                                model = selected_model
                                used_provider = candidate_provider
                                db.record_analysis(
                                    analysis_run_id,
                                    metadata.paper_uid,
                                    candidate_provider,
                                    model,
                                    PROMPT_VERSION,
                                    "reused",
                                )
                                db.set_import_job(
                                    job_id,
                                    paper_uid,
                                    "analysis_complete",
                                    "analysis-reused",
                                )
                                completed = True
                                break
                            adapter = make_provider(
                                candidate_provider, cfg.root, provider_config
                            )
                            result = adapter.analyze(metadata, text_path, profile)
                            selected_model = (
                                adapter.config.model or selected_model
                            )
                        else:
                            adapter = make_adapter(candidate_provider, cfg.root, analysis_cfg["timeout_seconds"], analysis_cfg.get("model"))
                            result = adapter.analyze(metadata, text_path)
                            selected_model = getattr(adapter, "model", "")
                        if not completed:
                            analysis = result.model_dump()
                        model = selected_model
                        used_provider = candidate_provider
                        db.record_analysis(
                            analysis_run_id,
                            metadata.paper_uid,
                            candidate_provider,
                            model,
                            PROMPT_VERSION,
                            analysis["ai_analysis_status"],
                        )
                        db.set_import_job(job_id, paper_uid, "analysis_complete", "analysis")
                        completed = True
                        break
                    except Exception as exc:
                        last_error = exc
                        db.record_analysis(
                            analysis_run_id,
                            metadata.paper_uid,
                            candidate_provider,
                            getattr(locals().get("adapter", None), "model", ""),
                            PROMPT_VERSION,
                            "failed",
                        )
                if completed:
                    break
            if not completed:
                assert last_error is not None
                raise last_error
            if analyzed_at is None:
                analyzed_at = iso_utc()
        record = metadata.model_dump(mode="json") | analysis
        primary, canonical_topics, unmatched_topics = canonicalize_topics(
            cfg.root,
            record.get("ai_topic_primary", ""),
            record.get("ai_topics", []),
            " ".join([metadata.paper_title, metadata.paper_abstract, *record.get("ai_method_family", []), *record.get("ai_task_types", [])]),
        )
        record["ai_topic_primary"] = primary
        record["ai_topics"] = canonical_topics
        record["paper_short_title"] = short_title(metadata.paper_title)
        record["version_change_note"] = (f"由 v{decision.existing_version} 更新到 v{metadata.paper_arxiv_version}；旧分析已保存快照。" if decision.action == "update" else f"当前版本 v{metadata.paper_arxiv_version}。")
        record.update({
            "paper_pdf_path": pdf_path.relative_to(cfg.root).as_posix() if pdf_path.exists() else "",
            "paper_has_code": bool(metadata.paper_code_url), "paper_has_project_page": bool(metadata.paper_project_url), "paper_has_dataset": bool(metadata.paper_dataset_url),
            "ai_analysis_provider": used_provider if run_ai else "", "ai_analysis_model": model, "ai_analysis_profile": used_profile if run_ai else "", "ai_analysis_prompt_version": PROMPT_VERSION if run_ai else "",
        "ai_analyzed_at": analyzed_at if run_ai else None, "user_priority": priority, "user_favorite": favorite,
            "user_reading_status": "queued" if queued else "inbox", "user_learning_status": "none", "user_rating": 0,
            "user_reproduction_status": "none", "user_added_tags": user_tags or [], "user_last_read_at": None, "user_next_review_at": None,
        "system_import_method": import_method, "system_imported_at": iso_utc(), "system_last_synced_at": iso_utc(),
            "system_content_hash": content_hash, "system_pipeline_version": "0.1.0", "system_requires_manual_review": not bool(metadata.paper_pdf_url) or bool(unmatched_topics), "system_error": "",
            "extraction": extraction,
        })
        if pdf_path.exists() and not reuse_local_assets:
            try:
                refresh_record_visuals(cfg.root, record)
            except Exception as exc:
                record["extraction"]["visual_assets"] = []
                record["extraction"]["visual_extraction_status"] = "failed"
                record["extraction"]["visual_extraction_error"] = str(exc)
        if topic:
            topic_primary, topic_values, topic_unmatched = canonicalize_topics(cfg.root, topic, [topic])
            if not record["ai_topic_primary"] and topic_primary:
                record["ai_topic_primary"] = topic_primary
            record["ai_topics"] = list(
                dict.fromkeys([*record["ai_topics"], *topic_values])
            )
            unmatched_topics.extend(value for value in topic_unmatched if value not in unmatched_topics)
            record["system_requires_manual_review"] = record["system_requires_manual_review"] or bool(topic_unmatched)
        if unmatched_topics:
            review_path = cfg.path("manual_review_folder") / f"{safe_slug(metadata.paper_uid)}-topics.md"
            atomic_write(review_path, "---\ntype: paper-topic-review\npaper_uid: " + metadata.paper_uid + "\nstatus: pending\ncreated_at: " + iso_utc() + "\n---\n\n# Topic 人工审核\n\n以下 AI 候选主题未自动创建：\n\n" + "\n".join(f"- {value}" for value in unmatched_topics) + "\n")
        if note_path.exists():
            existing_frontmatter, _ = read_note(note_path)
            for key, value in existing_frontmatter.items():
                if key.startswith("user_"):
                    record[key] = value
            if existing_frontmatter.get("system_imported_at"):
                record["system_imported_at"] = existing_frontmatter["system_imported_at"]
        record["note_path"] = note_path.relative_to(cfg.root).as_posix()
        record["json_path"] = json_path.relative_to(cfg.root).as_posix()
        if cfg.workspace is not None:
            ensure_user_note(
                cfg.root,
                cfg.workspace,
                record,
                content=user_note,
                locale=cfg.ui_locale.locale,
            )
        elif user_note:
            raise RuntimeError(
                "Independent User Notes require a PaperFlow Workspace; "
                "migrate this legacy Vault before importing Form Flow notes."
            )
        render_paper(cfg.root, record, note_path, import_method, cfg.ui_locale.locale)
        db.set_import_job(job_id, paper_uid, "rendered", "render")
        atomic_json(json_path, record)
        if cfg.workspace:
            record["layer_paths"] = persist_layer_records(
                cfg.root,
                record,
                preserve_existing_raw=preserve_existing_record,
            )
            atomic_json(json_path, record)
            if pdf_path.exists():
                from paperflow.annotations.pdf_versions import build_pdf_index

                existing = sorted(
                    pdf_path.parent.glob("v*.pdf"),
                    key=lambda item: int(item.stem.removeprefix("v")),
                )
                build_pdf_index(
                    cfg.root,
                    metadata.paper_uid,
                    [
                        {
                            "version": int(item.stem.removeprefix("v")),
                            "path": item.relative_to(cfg.root).as_posix(),
                        }
                        for item in existing
                    ],
                    current_version=metadata.paper_arxiv_version,
                )
        db.upsert_paper(record)
        if not cfg.section("retention").get("keep_extracted_text", True):
            text_path.unlink(missing_ok=True)
        db.set_import_job(job_id, paper_uid, "completed", "completed")
        logger.info("Paper import completed", extra={"run_id": job_id, "paper_uid": paper_uid, "stage": "completed"})
        return {"status": "updated" if decision.action == "update" else "imported", "paper_uid": metadata.paper_uid, "note_path": record["note_path"], "record": record}
    except Exception as exc:
        if failure_checkpoint is not None and not preserve_existing_record:
            checkpoint_path, checkpoint = failure_checkpoint
            checkpoint["ai_analysis_status"] = "failed"
            checkpoint["system_status"] = "failed"
            checkpoint["system_error"] = str(exc)
            atomic_json(checkpoint_path, checkpoint)
        db.set_import_job(job_id, paper_uid, "failed_retryable", "failed", str(exc))
        logger.error(str(exc), extra={"run_id": job_id, "paper_uid": paper_uid, "stage": "failed", "error_type": type(exc).__name__})
        raise
    finally:
        db.close()
PROMPT_VERSION = "paper-analysis-v3"
