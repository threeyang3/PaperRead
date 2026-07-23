from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, atomic_write, iso_beijing
from paperflow.entity_migration import entity_key
from paperflow.obsidian.frontmatter import read_note


ARXIV_REFERENCE_RE = re.compile(
    r"(?<!\d)(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", re.I
)
DOI_REFERENCE_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


def _entity_link(root: Path, kind: str, label: str) -> str:
    clean = " ".join(str(label).split()).strip()
    if not clean:
        return ""
    folder = {
        "topic": "20 Topics",
        "method": "20 Topics/Methods",
        "dataset": "20 Topics/Datasets",
    }[kind]
    relative = Path(folder) / f"{safe_component(clean)[:100]}.md"
    target = root / relative
    # Reuse a pre-existing entity whose label differs only by case, whitespace
    # or hyphen punctuation.  This prevents new AI runs from recreating legacy
    # variants such as `Diffusion Policy` and `Diffusion-Policy`.
    desired_key = entity_key(clean)
    if not target.exists():
        candidates: list[Path] = []
        directory = root / folder
        for candidate in sorted(directory.glob("*.md")) if directory.exists() else []:
            try:
                frontmatter, _ = read_note(candidate)
            except Exception:
                continue
            candidate_type = str(frontmatter.get("type") or "").casefold()
            tags = frontmatter.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            if candidate_type and candidate_type != kind and f"entity/{kind}" not in tags:
                continue
            candidate_label = str(
                frontmatter.get("title")
                or frontmatter.get(f"{kind}_name")
                or candidate.stem
            )
            if entity_key(candidate_label) == desired_key:
                candidates.append(candidate)
        if candidates:
            target = next(
                (candidate for candidate in candidates if candidate.name.casefold() == relative.name.casefold()),
                candidates[0],
            )
    relative = target.relative_to(root)
    if not target.exists():
        atomic_write(
            target,
            "---\n"
            f"type: {kind}\n"
            f"title: {json.dumps(clean, ensure_ascii=False)}\n"
            "tags:\n"
            f"  - entity/{kind}\n"
            "---\n\n"
            f"# {clean}\n\n"
            "## 相关论文\n",
        )
    return f"[[{relative.with_suffix('').as_posix()}|{clean}]]"


def _local_papers(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in (root / ".paperflow/data/papers").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        uid = str(record.get("paper_uid") or "")
        if uid:
            result[uid] = record
    return result


def derive_relationships(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    threshold = 0.35
    max_links = 8
    enabled_entities = {"topic", "method", "dataset"}
    try:
        from paperflow.workspace import load_workspace_settings

        _, settings = load_workspace_settings(root)
        threshold = settings.relationships.semantic_threshold
        max_links = settings.relationships.max_semantic_links
        enabled_entities = set(settings.relationships.entity_types)
    except (FileNotFoundError, ValueError):
        pass
    topic_links = [
        link
        for value in record.get("ai_topics", [])
        if "topic" in enabled_entities
        if (link := _entity_link(root, "topic", str(value)))
    ]
    method_links = [
        link
        for value in record.get("ai_method_family", [])
        if "method" in enabled_entities
        if (link := _entity_link(root, "method", str(value)))
    ]
    dataset_links = [
        link
        for value in record.get("ai_datasets", [])
        if "dataset" in enabled_entities
        if (link := _entity_link(root, "dataset", str(value)))
    ]
    evidence = ""
    extraction = record.get("extraction") or {}
    text_path = extraction.get("text_path")
    if text_path:
        candidate = Path(str(text_path))
        if candidate.is_file():
            evidence = candidate.read_text(encoding="utf-8", errors="replace")
    citation_ids = sorted(
        {f"arxiv:{value}" for value in ARXIV_REFERENCE_RE.findall(evidence)}
        | {f"doi:{value.lower().rstrip('.,;')}" for value in DOI_REFERENCE_RE.findall(evidence)}
    )
    local = _local_papers(root)
    citation_lookup = dict(local)
    for target in local.values():
        arxiv_id = str(target.get("paper_arxiv_id") or "")
        doi = str(target.get("paper_doi") or "").casefold()
        if arxiv_id:
            citation_lookup[f"arxiv:{arxiv_id}"] = target
        if doi:
            citation_lookup[f"doi:{doi}"] = target
    cites: list[str] = []
    for uid in citation_ids:
        target = citation_lookup.get(uid)
        if not target:
            continue
        note_path = str(target.get("note_path") or "").removesuffix(".md")
        title = str(
            target.get("paper_title_display")
            or target.get("paper_title")
            or uid
        )
        if note_path:
            cites.append(f"[[{note_path}|{title}]]")
    unresolved_citation_ids = [
        value for value in citation_ids if value not in citation_lookup
    ]

    current_topics = {str(value).casefold() for value in record.get("ai_topics", [])}
    current_methods = {
        str(value).casefold() for value in record.get("ai_method_family", [])
    }
    current_datasets = {
        str(value).casefold() for value in record.get("ai_datasets", [])
    }
    semantic: list[tuple[float, str, dict[str, Any]]] = []
    for uid, target in local.items():
        if uid == record.get("paper_uid"):
            continue
        topic_overlap = current_topics & {
            str(value).casefold() for value in target.get("ai_topics", [])
        }
        method_overlap = current_methods & {
            str(value).casefold() for value in target.get("ai_method_family", [])
        }
        dataset_overlap = current_datasets & {
            str(value).casefold() for value in target.get("ai_datasets", [])
        }
        score = min(
            1.0,
            0.22 * len(topic_overlap)
            + 0.18 * len(method_overlap)
            + 0.2 * len(dataset_overlap),
        )
        if score < threshold:
            continue
        note_path = str(target.get("note_path") or "").removesuffix(".md")
        if not note_path:
            continue
        title = str(
            target.get("paper_title_display")
            or target.get("paper_title")
            or uid
        )
        semantic.append(
            (
                score,
                f"[[{note_path}|{title}]]",
                {
                    "target": uid,
                    "type": "semantic",
                    "confidence": round(score, 2),
                    "evidence": {
                        "topics": sorted(topic_overlap),
                        "methods": sorted(method_overlap),
                        "datasets": sorted(dataset_overlap),
                    },
                },
            )
        )
    semantic.sort(key=lambda item: (-item[0], item[1]))
    semantic = semantic[:max_links]
    relationships = {
        "schema_version": 1,
        "generator_version": "relationships-v1",
        "paper_uid": record.get("paper_uid"),
        "generated_at": iso_beijing(),
        "edges": [
            *[
                {
                    "target": value,
                    "type": "citation",
                    "confidence": 1.0,
                    "source": "extracted-reference-text",
                    "evidence": value,
                }
                for value in citation_ids
            ],
            *[item[2] for item in semantic],
        ],
    }
    paper_id = safe_component(
        str(record.get("paper_arxiv_id") or record.get("paper_uid")).replace(":", "_")
    )
    atomic_json(
        root / ".paperflow/data/relationships" / f"{paper_id}.json",
        relationships,
    )
    # Keep the reverse Topic/Method/Dataset views useful after every paper
    # render.  The index writer only touches its machine-managed section and
    # never replaces user-authored entity prose.
    try:
        from paperflow.entity_indexes import rebuild_entity_indexes

        rebuild_entity_indexes(root, apply=True, backup=False, record_history=False)
    except (OSError, ValueError, KeyError):
        # Relationship generation remains usable even if an entity projection
        # needs manual review or the Vault is mid-migration.
        pass
    return {
        "ai_topic_links": topic_links,
        "ai_method_links": method_links,
        "ai_dataset_links": dataset_links,
        "paper_citation_ids": unresolved_citation_ids,
        "paper_cites": cites,
        "ai_related_papers": [item[1] for item in semantic],
        "system_relationship_index": (
            f".paperflow/data/relationships/{paper_id}.json"
        ),
    }
