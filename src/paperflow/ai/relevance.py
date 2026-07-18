from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from paperflow.models import PaperMetadata
from paperflow.utils import atomic_write, iso_beijing
from .codex_runtime import CODEX_ISOLATION_ARGS, isolated_codex_environment


def _payload(papers: list[PaperMetadata]) -> list[dict]:
    return [{
        "paper_uid": paper.paper_uid,
        "title": paper.paper_title,
        "abstract": paper.paper_abstract,
        "categories": paper.paper_categories,
    } for paper in papers]


def mock_relevance(papers: list[PaperMetadata]) -> dict[str, dict]:
    positive = ("robot", "manipulation", "embodied", "tactile", "visuomotor", "imitation", "diffusion policy", "teleoperation", "world model")
    result = {}
    for paper in papers:
        text = f"{paper.paper_title} {paper.paper_abstract}".casefold()
        score = min(5.0, 2.5 + 0.6 * sum(term in text for term in positive))
        result[paper.paper_uid] = {"score": round(score, 2), "reason": "Deterministic lightweight screening for tests.", "recommended": score >= 3.2}
    return result


def screen_relevance(root: Path, papers: list[PaperMetadata], provider: str, model: str, timeout: int, threshold: float) -> dict[str, dict]:
    if not papers:
        return {}
    if provider == "mock":
        return mock_relevance(papers)
    if provider != "codex":
        raise ValueError(f"Unsupported relevance provider: {provider}")
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI not found for lightweight relevance screening")
    schema_path = root / ".paperflow/schemas/paper-relevance.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    prompt = (root / ".paperflow/prompts/paper-relevance-v1.md").read_text(encoding="utf-8")
    prompt += f"\n\nThreshold: {threshold}\n\nCANDIDATES:\n" + json.dumps(_payload(papers), ensure_ascii=False)
    with tempfile.TemporaryDirectory(dir=root / ".paperflow/runtime") as temporary:
        output = Path(temporary) / "relevance.json"
        command = [
            executable, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
            *CODEX_ISOLATION_ARGS,
            "--model", model, "--output-schema", str(schema_path), "-o", str(output), "-",
        ]
        result = subprocess.run(command, cwd=temporary, env=isolated_codex_environment(Path(temporary)), input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        log = root / ".paperflow/logs/ai" / (iso_beijing().replace(":", "-") + "-relevance.log")
        atomic_write(log, (result.stdout or "") + "\nSTDERR:\n" + (result.stderr or ""))
        if result.returncode != 0:
            raise RuntimeError(f"Codex relevance screening failed with exit code {result.returncode}")
        raw = output.read_text(encoding="utf-8")
        atomic_write(log.with_name(log.name.replace(".log", "-raw.json")), raw)
        value = json.loads(raw)
        Draft202012Validator(schema).validate(value)
        expected = {paper.paper_uid for paper in papers}
        actual = {item["paper_uid"] for item in value["results"]}
        if expected != actual:
            raise ValueError("Relevance output did not contain exactly one result for every candidate")
        return {item["paper_uid"]: {"score": item["score"], "reason": item["reason"], "recommended": item["recommended"]} for item in value["results"]}
