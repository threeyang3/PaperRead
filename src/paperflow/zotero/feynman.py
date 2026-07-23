"""Feynman question projection with an isolated, user-owned answer store."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.security.artifacts import PermissionGuard
from paperflow.utils import atomic_write, iso_beijing, safe_slug
from paperflow.workspace import dump_yaml
from paperflow.zotero.store import standalone


def _safe_uid(paper_uid: str) -> str:
    value = str(paper_uid or "").strip()
    if not value or any(char in value for char in "\\/\x00"):
        raise ValueError("invalid paper_uid")
    return safe_slug(value.replace(":", "_"))


def feynman_path(root: Path, paper_uid: str) -> Path:
    folder = root / ("data/user/feynman" if standalone(root) else ".paperflow/data/user/feynman")
    return folder / f"{_safe_uid(paper_uid)}.yaml"


def question_id(paper_uid: str, question: str, index: int) -> str:
    digest = hashlib.sha256(f"{paper_uid}\0{index}\0{question}".encode("utf-8")).hexdigest()[:12]
    return f"fq-{digest}"


def normalize_questions(paper_uid: str, questions: list[object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for index, value in enumerate(questions):
        text = " ".join(str(value or "").split()).strip()
        if text:
            result.append({"id": question_id(paper_uid, text, index), "question": text})
    return result


def load_answers(root: Path, paper_uid: str) -> dict[str, Any]:
    path = feynman_path(root, paper_uid)
    if not path.is_file():
        return {"schema_version": 1, "paper_uid": paper_uid, "questions": [], "answers": {}, "feedback": []}
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def ensure_questions(root: Path, paper_uid: str, questions: list[object], *, apply_changes: bool = False) -> dict[str, Any]:
    normalized = normalize_questions(paper_uid, questions)
    path = feynman_path(root, paper_uid)
    existing = load_answers(root, paper_uid)
    merged = dict(existing)
    merged.setdefault("schema_version", 1)
    merged["paper_uid"] = paper_uid
    merged["questions"] = normalized
    merged.setdefault("answers", {})
    merged.setdefault("feedback", [])
    result = {"paper_uid": paper_uid, "path": path.as_posix(), "question_count": len(normalized), "dry_run": not apply_changes, "permission": "USER_MANAGED"}
    if apply_changes:
        PermissionGuard(root).authorize(path, "USER_MANAGED")
        dump_yaml(path, merged)
        result["status"] = "written"
    else:
        result["status"] = "would-write" if merged != existing else "up-to-date"
    return result


def save_answer(root: Path, paper_uid: str, question: str, answer: str) -> dict[str, Any]:
    text = " ".join(str(answer or "").split()).strip()
    if not text:
        raise ValueError("answer must not be empty")
    path = feynman_path(root, paper_uid)
    value = load_answers(root, paper_uid)
    questions = value.get("questions") if isinstance(value.get("questions"), list) else []
    question_key = str(question)
    if not any(str(item.get("id")) == question_key for item in questions if isinstance(item, dict)):
        raise ValueError(f"unknown Feynman question: {question_key}")
    answers = value.setdefault("answers", {})
    answers[question_key] = {"answer": text, "updated_at": iso_beijing()}
    PermissionGuard(root).authorize(path, "USER_MANAGED")
    dump_yaml(path, value)
    return {"status": "written", "paper_uid": paper_uid, "question_id": question_key, "path": path.as_posix()}


__all__ = ["ensure_questions", "feynman_path", "load_answers", "normalize_questions", "question_id", "save_answer"]
