from __future__ import annotations
from pathlib import Path
from ruamel.yaml import YAML


def normalize_topic(root: Path, value: str) -> str | None:
    data = YAML(typ="safe").load((root / "90 System/Taxonomy/research-topics.yaml").read_text(encoding="utf-8"))
    needle = value.strip().casefold()
    for topic in data["topics"]:
        values = [topic["name"], *topic.get("aliases", []), *topic.get("keywords", [])]
        if needle in {str(item).casefold() for item in values}:
            return topic["name"]
    return None


def canonicalize_topics(root: Path, primary: str, topics: list[str], evidence: str = "") -> tuple[str, list[str], list[str]]:
    data = YAML(typ="safe").load((root / "90 System/Taxonomy/research-topics.yaml").read_text(encoding="utf-8"))
    canonical: list[str] = []
    unmatched: list[str] = []
    for value in [primary, *topics]:
        if not value:
            continue
        match = normalize_topic(root, value)
        if match and match not in canonical:
            canonical.append(match)
        elif not match and value not in unmatched:
            unmatched.append(value)
    searchable = " ".join([primary, *topics, evidence]).casefold()
    for topic in data["topics"]:
        terms = [topic["name"], *topic.get("aliases", []), *topic.get("keywords", [])]
        if any(str(term).casefold() in searchable for term in terms) and topic["name"] not in canonical:
            canonical.append(topic["name"])
    return (canonical[0] if canonical else "", canonical, unmatched)
