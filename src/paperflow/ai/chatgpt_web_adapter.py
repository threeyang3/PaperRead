from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from paperflow.ai.schema_validation import validate_analysis
from paperflow.models import Analysis, PaperMetadata
from paperflow.text_quality import validate_text_quality
from paperflow.utils import atomic_json, atomic_write, iso_beijing
from paperflow.zotero.store import runtime_root, state_root
from paperflow.paths.templates import safe_component
from paperflow.pdf_resolver import resolve_current_pdf
from .paths import ai_log_path, prompt_path, schema_path


PROMPT_VERSION = "paper-analysis-v3"
DEFAULT_MODEL_PREFERENCE = [
    "Pro",
    "Thinking",
    "GPT-5.6",
    "GPT-5",
]


def default_edge_path() -> Path | None:
    for candidate in (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ):
        if candidate.exists():
            return candidate
    return None


def default_profile_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "PaperFlow" / "ChatGPTWeb"


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S | re.I)
    candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    if not candidate:
        raise ValueError("ChatGPT response did not contain a JSON object")
    return json.loads(candidate)


class ChatGPTWebAdapter:
    provider = "chatgpt-web"

    def __init__(
        self,
        root: Path,
        *,
        timeout: int = 3600,
        browser_executable: str = "",
        browser_profile_dir: str = "",
        base_url: str = "https://chatgpt.com/",
        allow_pdf_upload: bool = False,
        model_preference: list[str] | None = None,
    ):
        self.root = root
        self.timeout = timeout
        self.browser_executable = Path(browser_executable) if browser_executable else default_edge_path()
        self.browser_profile_dir = (
            Path(os.path.expandvars(browser_profile_dir)).expanduser()
            if browser_profile_dir
            else default_profile_dir()
        )
        self.base_url = base_url
        self.allow_pdf_upload = allow_pdf_upload
        self.model_preference = model_preference or DEFAULT_MODEL_PREFERENCE
        self.actual_model = ""

    def _save_state(self, status: str, detail: str = "") -> None:
        atomic_json(
            state_root(self.root) / "chatgpt-web.json",
            {
                "status": status,
                "detail": detail,
                "actual_model": self.actual_model,
                "checked_at": iso_beijing(),
            },
        )

    def _paper_pdf(self, metadata: PaperMetadata) -> Path:
        record = metadata.model_dump(mode="json")
        paper_id = metadata.paper_arxiv_id or safe_component(
            metadata.paper_uid.replace(":", "_")
        )
        canonical = self.root / ".paperflow/data/papers" / f"{paper_id}.json"
        if canonical.is_file():
            try:
                record.update(json.loads(canonical.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Canonical paper record is invalid for {metadata.paper_uid}"
                ) from exc
        return resolve_current_pdf(
            self.root,
            metadata.paper_uid,
            record=record,
        ).path

    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis:
        if not self.allow_pdf_upload:
            raise PermissionError(
                "ChatGPT Web PDF upload is disabled; enable allow_pdf_upload explicitly"
            )
        if not self.browser_executable or not self.browser_executable.exists():
            raise RuntimeError("Microsoft Edge was not found")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed; install paperflow[browser]"
            ) from exc

        pdf = self._paper_pdf(metadata)
        schema = schema_path(self.root)
        prompt = prompt_path(self.root).read_text(encoding="utf-8")
        prompt += (
            "\n\nAnalyze the attached PDF. METADATA:\n"
            + metadata.model_dump_json(indent=2)
            + "\nReturn one schema-valid JSON object."
        )
        staging_root = runtime_root(self.root) / "staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging_root) as temporary:
            staged_pdf = Path(temporary) / "paper.pdf"
            shutil.copy2(pdf, staged_pdf)
            response_text = ""
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(self.browser_profile_dir),
                    executable_path=str(self.browser_executable),
                    headless=False,
                    accept_downloads=False,
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.base_url, wait_until="domcontentloaded", timeout=120_000)
                page_text = page.locator("body").inner_text().casefold()
                if "verify you are human" in page_text or "captcha" in page_text:
                    self._save_state("user-action-required", "captcha")
                    context.close()
                    raise RuntimeError(
                        "ChatGPT requires human verification; take over the dedicated Edge window"
                    )
                if page.locator('input[type="password"]').count():
                    self._save_state("user-action-required", "login")
                    context.close()
                    raise RuntimeError(
                        "ChatGPT login is required; sign in using the dedicated Edge profile"
                    )
                model_button = page.locator(
                    'button[data-testid*="model"], button[aria-label*="model" i]'
                ).first
                if model_button.count() == 0:
                    self._save_state("user-action-required", "model-selector")
                    context.close()
                    raise RuntimeError("ChatGPT model selector was not found")
                model_button.click()
                menu_text = page.locator('[role="menu"], [role="listbox"]').last.inner_text()
                selected = next(
                    (name for name in self.model_preference if name.casefold() in menu_text.casefold()),
                    "",
                )
                if not selected:
                    self._save_state("user-action-required", "strongest-model")
                    context.close()
                    raise RuntimeError("The strongest visible ChatGPT model could not be identified")
                option = page.get_by_text(selected, exact=False).last
                self.actual_model = option.inner_text().strip()
                option.click()

                file_input = page.locator('input[type="file"]').last
                if file_input.count() == 0:
                    attach = page.locator(
                        'button[aria-label*="attach" i], button[data-testid*="attach"]'
                    ).first
                    if attach.count() == 0:
                        context.close()
                        raise RuntimeError("ChatGPT PDF upload control was not found")
                    attach.click()
                    file_input = page.locator('input[type="file"]').last
                file_input.set_input_files(str(staged_pdf))
                composer = page.locator(
                    '#prompt-textarea, textarea, [contenteditable="true"]'
                ).last
                composer.fill(prompt)
                send = page.locator(
                    'button[data-testid="send-button"], button[aria-label*="send" i]'
                ).last
                send.click()
                deadline = time.monotonic() + self.timeout
                while time.monotonic() < deadline:
                    stop = page.locator(
                        'button[data-testid="stop-button"], button[aria-label*="stop" i]'
                    )
                    if stop.count() == 0 and page.locator('[data-message-author-role="assistant"]').count():
                        break
                    page.wait_for_timeout(1000)
                else:
                    context.close()
                    raise TimeoutError("ChatGPT Web analysis timed out")
                response_text = page.locator(
                    '[data-message-author-role="assistant"]'
                ).last.inner_text()
                try:
                    value = _extract_json(response_text)
                except (ValueError, json.JSONDecodeError):
                    composer = page.locator(
                        '#prompt-textarea, textarea, [contenteditable="true"]'
                    ).last
                    composer.fill(
                        "The previous response was not valid JSON. Return only one "
                        "JSON object that conforms exactly to the requested schema; "
                        "do not add Markdown fences or commentary."
                    )
                    page.locator(
                        'button[data-testid="send-button"], '
                        'button[aria-label*="send" i]'
                    ).last.click()
                    deadline = time.monotonic() + min(self.timeout, 600)
                    previous_count = page.locator(
                        '[data-message-author-role="assistant"]'
                    ).count()
                    while time.monotonic() < deadline:
                        messages = page.locator(
                            '[data-message-author-role="assistant"]'
                        )
                        stop = page.locator(
                            'button[data-testid="stop-button"], '
                            'button[aria-label*="stop" i]'
                        )
                        if stop.count() == 0 and messages.count() > previous_count:
                            break
                        page.wait_for_timeout(1000)
                    response_text = page.locator(
                        '[data-message-author-role="assistant"]'
                    ).last.inner_text()
                    value = _extract_json(response_text)
                context.close()
            validate_text_quality(value, label="chatgpt-web-analysis")
            self._save_state("ready", self.actual_model)
            atomic_write(
                ai_log_path(self.root, f"{iso_beijing().replace(':', '-')}-chatgpt-web.txt"),
                response_text,
            )
            return validate_analysis(value, schema)
