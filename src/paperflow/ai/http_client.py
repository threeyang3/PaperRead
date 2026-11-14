"""Opt-in HTTPS Chat Completions client for OpenAI-compatible endpoints.

Keys are read only from the environment, and never persisted or logged.
No redirects are followed with an Authorization header. All responses are
locally validated by their caller before being published.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
KEY_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("API endpoint redirects are forbidden")


def api_endpoint(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    parts = urlsplit(base)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.port not in (None, 443)
    ):
        raise ValueError("API base_url must be an HTTPS endpoint without credentials or query")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def chat_json(
    *,
    base_url: str,
    api_key_env: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    if not KEY_NAME.fullmatch(api_key_env):
        raise ValueError("Invalid API key environment variable name")
    key = os.environ.get(api_key_env, "")
    if not key:
        raise RuntimeError(f"API credential not configured: {api_key_env}")
    if not isinstance(key, str) or "\r" in key or "\n" in key:
        raise ValueError("Invalid API credential")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 14400:
        raise ValueError("Invalid API timeout")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not 1 <= max_tokens <= 65536:
        raise ValueError("Invalid API output budget")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("API provider requires an explicit model")
    url = api_endpoint(base_url)
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt + "\nReturn a JSON object."},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("API response exceeds 8 MiB safety limit")
    except urllib.error.HTTPError as exc:
        # Do not include provider response bodies: they may echo prompts/data.
        raise RuntimeError(f"API returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("API network request failed") from None
    envelope = json.loads(data.decode("utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("API response must be an object")
    choices = envelope.get("choices") or []
    if not isinstance(choices, list) or not choices:
        raise ValueError("API response has no choices")
    chosen = choices[0]
    if not isinstance(chosen, dict) or chosen.get("finish_reason") != "stop":
        raise ValueError("API response is incomplete or refused")
    message = chosen.get("message") or {}
    if not isinstance(message, dict) or message.get("refusal"):
        raise ValueError("API response is malformed or refused")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("API returned empty structured content")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("API output must be a JSON object")
    return value
