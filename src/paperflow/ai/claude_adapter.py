from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from paperflow.models import Analysis, PaperMetadata
from .schema_validation import validate_analysis
from .context import select_context
from paperflow.utils import atomic_write, iso_beijing

PROMPT_VERSION = "paper-analysis-v2"


def _claude_cli_schema(schema: dict) -> dict:
    """Return the validation shape supported by Claude Code structured output.

    Claude Code validates the supplied object itself and currently rejects the
    Draft 2020-12 declaration URI. PaperFlow still validates the returned value
    against the original on-disk schema after the CLI exits.
    """
    value = dict(schema)
    value.pop("$schema", None)
    return value


class ClaudeAdapter:
    provider = "claude"
    model = "configured-default"

    def __init__(
        self,
        root: Path,
        timeout: int = 1800,
        model: str | None = None,
        executable: str = "claude",
        extra_args: list[str] | None = None,
    ):
        self.root, self.timeout = root, timeout
        self.model = model or "configured-default"
        self.executable = executable
        self.extra_args = list(extra_args or [])

    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis:
        executable = shutil.which(self.executable)
        if not executable:
            raise RuntimeError("Claude Code not found")
        schema_path = self.root / ".paperflow/schemas/paper-analysis.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        prompt = (self.root / ".paperflow/prompts/paper-analysis-v2.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(dir=self.root / ".paperflow/runtime") as temporary:
            work = Path(temporary)
            shutil.copy2(text_path, work / "paper.txt")
            (work / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
            command = [executable, "--print", "--bare", "--tools", "", "--no-session-persistence", "--output-format", "json", "--json-schema", json.dumps(_claude_cli_schema(schema))]
            if self.model != "configured-default":
                command.extend(["--model", self.model])
            command.extend(self.extra_args)
            paper_text = select_context(text_path.read_text(encoding="utf-8", errors="replace"))
            full_prompt = prompt + "\n\nMETADATA:\n" + metadata.model_dump_json(indent=2) + "\n\nPAPER TEXT:\n" + paper_text + "\n\nReturn only schema-valid JSON."
            result = subprocess.run(command, cwd=work, input=full_prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout)
            log_name = iso_beijing().replace(":", "-") + "-claude.log"
            atomic_write(self.root / ".paperflow/logs/ai" / log_name, (result.stdout or "") + "\nSTDERR:\n" + (result.stderr or ""))
            if result.returncode != 0:
                raise RuntimeError(f"Claude analysis failed: {result.stderr[-500:]}")
            wrapper = json.loads(result.stdout)
            value = wrapper.get("structured_output") or wrapper.get("result") or wrapper
            if isinstance(value, str):
                value = json.loads(value)
            return validate_analysis(value, schema_path)
