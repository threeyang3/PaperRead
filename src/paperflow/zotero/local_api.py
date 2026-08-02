"""Read-only adapter for Zotero's loopback Local API.

The adapter deliberately implements only GET requests.  It validates that the
configured endpoint is loopback-only and never accepts a remote host or a
write method, so it can be used for diagnostics and migration planning without
opening or modifying ``zotero.sqlite``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


class ZoteroLocalApiError(RuntimeError):
    """A safe, user-facing Local API failure."""


def _loopback_url(value: str) -> str:
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Zotero Local API must use an http loopback URL")
    path = parsed.path.rstrip("/") or "/api"
    return urlunparse(("http", parsed.netloc, path, "", "", ""))


@dataclass(frozen=True)
class ZoteroLocalApi:
    base_url: str = "http://127.0.0.1:23119/api/"
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _loopback_url(self.base_url))

    def _get(self, path: str, **query: object) -> Any:
        clean = "/" + str(path).lstrip("/")
        base = self.base_url.rstrip("/")
        params = {key: value for key, value in query.items() if value is not None and value != ""}
        url = f"{base}{clean}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            with exc:
                message = str(exc)
            raise ZoteroLocalApiError(f"Zotero Local API unavailable: {message}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ZoteroLocalApiError(f"Zotero Local API unavailable: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ZoteroLocalApiError("Zotero Local API returned invalid JSON") from exc

    def health(self) -> dict[str, Any]:
        value = self._get("")
        return value if isinstance(value, dict) else {"value": value}

    def libraries(self) -> list[dict[str, Any]]:
        value = self._get("users/0/items", limit=0)
        return value if isinstance(value, list) else []

    def items(
        self,
        library_id: int = 0,
        *,
        limit: int = 100,
        start: int = 0,
        q: str = "",
        item_type: str = "",
    ) -> list[dict[str, Any]]:
        if limit < 0 or limit > 1000 or start < 0:
            raise ValueError("limit must be 0..1000 and start must be non-negative")
        path = f"users/{int(library_id)}/items"
        value = self._get(path, limit=limit, start=start, q=q, itemType=item_type)
        return value if isinstance(value, list) else []

    def item(self, library_id: int, item_key: str) -> dict[str, Any]:
        value = self._get(f"users/{int(library_id)}/items/{item_key}")
        return value if isinstance(value, dict) else {"value": value}

    def children(self, library_id: int, item_key: str) -> list[dict[str, Any]]:
        value = self._get(f"users/{int(library_id)}/items/{item_key}/children")
        return value if isinstance(value, list) else []

    def annotations(self, library_id: int, attachment_key: str) -> list[dict[str, Any]]:
        value = self._get(f"users/{int(library_id)}/items/{attachment_key}/children", itemType="annotation")
        return value if isinstance(value, list) else []


__all__ = ["ZoteroLocalApi", "ZoteroLocalApiError"]
