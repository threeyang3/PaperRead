from __future__ import annotations

import json
import shutil
from pathlib import Path

from paperflow.config import Config
from paperflow.database import Database
from paperflow.obsidian.note_renderer import render_paper
from paperflow.pipeline.resources import GENERIC_HOSTS, find_resource_links, plausible_resource_url
from urllib.parse import urlsplit
from ruamel.yaml import YAML
from paperflow.taxonomy import canonicalize_topics
from paperflow.utils import atomic_json, atomic_write, iso_beijing, now_beijing, safe_slug


def migrate_v2(cfg: Config, dry_run: bool = True) -> dict:
    registry_path = cfg.root / ".paperflow/data/verified-resources.yaml"
    verified = {}
    if registry_path.exists():
        verified = (YAML(typ="safe").load(registry_path.read_text(encoding="utf-8")) or {}).get("papers", {})
    changes: list[dict] = []
    all_uids: list[str] = []
    for json_path in (cfg.root / ".paperflow/data/papers").glob("*.json"):
        record = json.loads(json_path.read_text(encoding="utf-8"))
        all_uids.append(record["paper_uid"])
        before = {key: record.get(key) for key in ["ai_topic_primary", "ai_topics", "paper_project_url", "paper_code_url", "paper_dataset_url", "paper_published_venue", "system_requires_manual_review"]}
        cache = cfg.root / ".paperflow/cache" / f"{safe_slug(record['paper_uid'])}.txt"
        text = record.get("paper_abstract", "")
        if cache.exists():
            text += "\n" + cache.read_text(encoding="utf-8", errors="replace")
        resources = find_resource_links(text)
        for key, value in resources.items():
            existing = record.get(key, "")
            replace_generic_project = key == "paper_project_url" and existing and (urlsplit(existing).netloc.casefold() in GENERIC_HOSTS or not plausible_resource_url(existing))
            if value and (not existing or replace_generic_project):
                record[key] = value
        for key, value in verified.get(record["paper_uid"], {}).items():
            if key.startswith("paper_"):
                record[key] = value
        record["paper_has_code"] = bool(record.get("paper_code_url"))
        record["paper_has_project_page"] = bool(record.get("paper_project_url"))
        record["paper_has_dataset"] = bool(record.get("paper_dataset_url"))
        primary, topics, unmatched = canonicalize_topics(cfg.root, record.get("ai_topic_primary", ""), record.get("ai_topics", []), " ".join([record.get("paper_title", ""), record.get("paper_abstract", ""), *record.get("ai_method_family", []), *record.get("ai_task_types", [])]))
        record["ai_topic_primary"] = primary
        record["ai_topics"] = topics
        record["system_requires_manual_review"] = bool(record.get("system_requires_manual_review")) or bool(unmatched)
        after = {key: record.get(key) for key in before}
        if before != after:
            changes.append({"paper_uid": record["paper_uid"], "before": before, "after": after, "unmatched_topics": unmatched})
            if not dry_run:
                stamp = now_beijing().strftime("%Y%m%d-%H%M%S")
                backup = cfg.root / ".paperflow/state/migrations" / stamp / safe_slug(record["paper_uid"])
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(json_path, backup / json_path.name)
                note_path = cfg.root / record["note_path"]
                if note_path.exists():
                    shutil.copy2(note_path, backup / note_path.name)
                atomic_json(json_path, record)
                render_paper(cfg.root, record, note_path, record.get("system_import_method", "manual"))
                if unmatched:
                    review = cfg.path("manual_review_folder") / f"{safe_slug(record['paper_uid'])}-topics.md"
                    atomic_write(review, "---\ntype: paper-topic-review\npaper_uid: " + record["paper_uid"] + "\nstatus: pending\ncreated_at: " + iso_beijing() + "\n---\n\n# Topic 人工审核\n\n" + "\n".join(f"- {value}" for value in unmatched) + "\n")
    if not dry_run:
        db = Database(cfg.root / ".paperflow/state/paperflow.db")
        try:
            db.apply_migration(2)
            for uid in all_uids:
                db.set_import_job(f"migration-2:{uid}", uid, "completed", "migrated")
        finally:
            db.close()
    return {"migration": 2, "dry_run": dry_run, "changed": len(changes), "changes": changes}
