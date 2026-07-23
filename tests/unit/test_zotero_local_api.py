from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.zotero.local_api import ZoteroLocalApi


def test_local_api_rejects_non_loopback() -> None:
    with pytest.raises(ValueError):
        ZoteroLocalApi("https://example.com/api/")


def test_local_api_builds_read_only_items_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps([{"key": "ABCD1234"}]).encode("utf-8")

    def fake_open(request, timeout):
        seen.append(request.full_url)
        assert request.method == "GET"
        assert timeout == 5.0
        return Response()

    monkeypatch.setattr("paperflow.zotero.local_api.urlopen", fake_open)
    items = ZoteroLocalApi().items(library_id=1, limit=10, q="pi")
    assert items == [{"key": "ABCD1234"}]
    assert seen == ["http://127.0.0.1:23119/api/users/1/items?limit=10&start=0&q=pi"]
