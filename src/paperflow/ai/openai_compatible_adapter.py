"""Schema-validated analysis through a configured HTTPS model API."""
from __future__ import annotations

from pathlib import Path

from paperflow.models import Analysis, PaperMetadata
from paperflow.text_quality import validate_text_quality
from .context import select_context
from .http_client import chat_json
from .paths import prompt_path, schema_path
from .schema_validation import validate_analysis


class OpenAICompatibleAdapter:
    provider = "openai-api"

    def __init__(
        self, root: Path, *, model: str, base_url: str,
        api_key_env: str = "PAPERFLOW_OPENAI_API_KEY",
        timeout: int = 1800, max_tokens: int = 8192,
    ):
        self.root = root
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.max_tokens = max_tokens

    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis:
        value = chat_json(
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            model=self.model,
            system_prompt=prompt_path(self.root).read_text(encoding="utf-8"),
            user_prompt=(
                "METADATA:\n" + metadata.model_dump_json(indent=2)
                + "\n\nPAPER TEXT:\n"
                + select_context(text_path.read_text(encoding="utf-8", errors="replace"))
                + "\n\nReturn only schema-valid JSON. Do not invent unread sections."
            ),
            timeout=self.timeout,
            max_tokens=self.max_tokens,
        )
        validate_text_quality(value, label="api-analysis")
        return validate_analysis(value, schema_path(self.root))
