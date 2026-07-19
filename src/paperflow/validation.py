from __future__ import annotations
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from paperflow.obsidian.bases import validate_bases
from paperflow.obsidian.frontmatter import read_note

READING = {"inbox", "queued", "skimming", "reading", "read", "archived", "rejected"}
LEARNING = {"none", "understanding", "reviewing", "reproducing", "mastered"}
REPRODUCTION = {"none", "candidate", "planned", "in_progress", "blocked", "completed", "abandoned"}
LIST_FIELDS = {
    "paper_authors", "paper_categories", "ai_topics", "ai_method_family",
    "ai_task_types", "ai_robot_platforms", "ai_datasets", "ai_baselines",
    "ai_topic_links", "ai_method_links", "ai_dataset_links",
    "paper_cites", "paper_citation_ids", "ai_related_papers",
    "user_added_tags",
}
BOOL_FIELDS = {"paper_has_code", "paper_has_project_page", "paper_has_dataset", "user_favorite", "system_requires_manual_review"}
NUMBER_FIELDS = {"paper_arxiv_version", "ai_relevance_score", "ai_novelty_score", "ai_completeness_score", "ai_reproducibility_score", "ai_overall_score", "user_priority", "user_rating"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_visual_assets(root: Path) -> list[str]:
    errors: list[str] = []
    schema_path = root / ".paperflow/schemas/visual-assets.schema.json"
    if not schema_path.exists():
        schema_path = Path(__file__).resolve().parents[2] / "schemas/visual-assets.schema.json"
    try:
        validator = Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:
        return [f"visual asset schema: {exc}"]
    for manifest_path in (root / "80 Attachments/Papers").rglob(
        "*.assets/manifest.json"
    ):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for error in validator.iter_errors(manifest):
                location = ".".join(str(part) for part in error.absolute_path)
                errors.append(
                    f"{manifest_path}: {location or '<root>'}: {error.message}"
                )
            asset_dir = manifest_path.parent
            pdf_name = asset_dir.name.removesuffix(".assets") + ".pdf"
            pdf_path = asset_dir.with_name(pdf_name)
            if not pdf_path.is_file():
                errors.append(f"{manifest_path}: source PDF missing: {pdf_path}")
            elif _sha256(pdf_path) != manifest.get("pdf_sha256"):
                errors.append(f"{manifest_path}: source PDF SHA256 mismatch")
            for asset in manifest.get("assets", []):
                relative = str(asset.get("path") or "")
                candidate = (root / relative).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    errors.append(f"{manifest_path}: asset escapes Vault: {relative}")
                    continue
                if not candidate.is_file():
                    errors.append(f"{manifest_path}: asset missing: {relative}")
                elif _sha256(candidate) != asset.get("sha256"):
                    errors.append(f"{manifest_path}: asset SHA256 mismatch: {relative}")
        except Exception as exc:
            errors.append(f"{manifest_path}: {exc}")
    return errors


def validate_all(root: Path) -> list[str]:
    errors: list[str] = []
    yaml = YAML(typ="safe")
    try: yaml.load((root / "paperflow.yaml").read_text(encoding="utf-8"))
    except Exception as exc: errors.append(f"paperflow.yaml: {exc}")
    try: json.loads((root / ".paperflow/schemas/paper-analysis.schema.json").read_text(encoding="utf-8"))
    except Exception as exc: errors.append(f"analysis schema: {exc}")
    errors.extend(validate_visual_assets(root))
    errors.extend(validate_bases(root))
    relationship_schema_path = (
        root / ".paperflow/schemas/paper-relationships.schema.json"
    )
    if relationship_schema_path.exists():
        relationship_validator = Draft202012Validator(
            json.loads(relationship_schema_path.read_text(encoding="utf-8"))
        )
        for path in (root / ".paperflow/data/relationships").glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                for error in relationship_validator.iter_errors(value):
                    errors.append(f"{path}: {error.message}")
            except Exception as exc:
                errors.append(f"{path}: {exc}")
    for path in (root / "10 Papers").rglob("*.md"):
        try:
            frontmatter, body = read_note(path)
            if frontmatter.get("type") != "paper": errors.append(f"{path}: type is not paper")
            if "<!-- USER_NOTES_START -->" not in body or "<!-- USER_NOTES_END -->" not in body: errors.append(f"{path}: user note markers missing")
            if frontmatter.get("user_reading_status") not in READING: errors.append(f"{path}: invalid user_reading_status")
            if frontmatter.get("user_learning_status") not in LEARNING: errors.append(f"{path}: invalid user_learning_status")
            if frontmatter.get("user_reproduction_status") not in REPRODUCTION: errors.append(f"{path}: invalid user_reproduction_status")
            for field in LIST_FIELDS:
                if not isinstance(frontmatter.get(field), list): errors.append(f"{path}: {field} must be a list")
            for field in BOOL_FIELDS:
                if not isinstance(frontmatter.get(field), bool): errors.append(f"{path}: {field} must be boolean")
            for field in NUMBER_FIELDS:
                if not isinstance(frontmatter.get(field), (int, float)) or isinstance(frontmatter.get(field), bool): errors.append(f"{path}: {field} must be numeric")
            for field in ["ai_analyzed_at", "system_imported_at", "system_last_synced_at"]:
                value = frontmatter.get(field)
                if value is not None and value != "" and not str(value).endswith("+08:00"): errors.append(f"{path}: {field} must include +08:00")
        except Exception as exc: errors.append(f"{path}: {exc}")
    request_folders = [root / "50 Inbox/Paper Requests", root / "50 Inbox/Processed Requests", root / "50 Inbox/Failed Imports"]
    for folder in request_folders:
        for path in folder.glob("*.md"):
            try:
                frontmatter, _ = read_note(path)
                if frontmatter.get("type") != "paper-import-request": errors.append(f"{path}: invalid request type")
                if frontmatter.get("status") not in {"pending", "processing", "completed", "failed"}: errors.append(f"{path}: invalid request status")
            except Exception as exc: errors.append(f"{path}: {exc}")
    return errors
