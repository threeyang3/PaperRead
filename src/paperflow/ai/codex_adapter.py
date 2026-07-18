from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from paperflow.models import Analysis, PaperMetadata
from paperflow.utils import atomic_write, iso_beijing
from .schema_validation import validate_analysis
from .context import select_context
from .codex_runtime import CODEX_ISOLATION_ARGS, isolated_codex_environment

PROMPT_VERSION = "paper-analysis-v2"
REASONING_EFFORTS = {"", "low", "medium", "high", "xhigh"}


def reasoning_effort_args(value: str) -> list[str]:
    normalized = value.strip().lower()
    if normalized not in REASONING_EFFORTS:
        raise ValueError(
            "Codex reasoning effort must be low, medium, high, xhigh, or empty"
        )
    if not normalized:
        return []
    return ["--config", f'model_reasoning_effort="{normalized}"']


class CodexAdapter:
    provider = "codex"

    def __init__(
        self,
        root: Path,
        timeout: int = 1800,
        model: str | None = None,
        executable: str = "codex",
        profile: str = "",
        reasoning_effort: str = "",
        extra_args: list[str] | None = None,
    ):
        self.root, self.timeout = root, timeout
        self.model = model or "configured-default"
        self.executable = executable
        self.profile = profile
        self.reasoning_effort = reasoning_effort
        self.extra_args = list(extra_args or [])

    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis:
        executable = shutil.which(self.executable)
        if not executable:
            raise RuntimeError("Codex CLI not found")
        schema = self.root / ".paperflow/schemas/paper-analysis.schema.json"
        prompt_template = (self.root / ".paperflow/prompts/paper-analysis-v2.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(dir=self.root / ".paperflow/runtime") as temporary:
            work = Path(temporary)
            shutil.copy2(text_path, work / "paper.txt")
            (work / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
            output = work / "analysis.json"
            paper_text = select_context(text_path.read_text(encoding="utf-8", errors="replace"))
            prompt = prompt_template + "\n\nMETADATA:\n" + metadata.model_dump_json(indent=2) + "\n\nPAPER TEXT:\n" + paper_text + "\n\nReturn only schema-valid JSON."
            command = [
                executable, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                *CODEX_ISOLATION_ARGS,
            ]
            if self.model != "configured-default":
                command.extend(["--model", self.model])
            if self.profile:
                command.extend(["--profile", self.profile])
            command.extend(reasoning_effort_args(self.reasoning_effort))
            command.extend(self.extra_args)
            command.extend(["--output-schema", str(schema), "-o", str(output), "-"])
            result = subprocess.run(command, cwd=work, env=isolated_codex_environment(work), input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout)
            log_name = iso_beijing().replace(":", "-") + ".log"
            atomic_write(self.root / ".paperflow/logs/ai" / log_name, (result.stdout or "") + "\nSTDERR:\n" + (result.stderr or ""))
            if result.returncode != 0:
                raise RuntimeError(f"Codex analysis failed with exit code {result.returncode}")
            raw = output.read_text(encoding="utf-8")
            atomic_write(self.root / ".paperflow/logs/ai" / log_name.replace(".log", "-raw.json"), raw)
            return validate_analysis(json.loads(raw), schema)
