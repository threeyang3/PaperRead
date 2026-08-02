from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import fitz
import httpx

from paperflow.feed import subscriber
from paperflow.net import pdf_download
from paperflow.zotero import standalone_sync


class FakeResponse:
    def __init__(self, chunks: list[bytes], *, content_length: int | None = None):
        self.chunks = chunks
        self.headers = {"content-length": str(content_length)} if content_length is not None else {}
        self.chunk_size: int | None = None
        self.iterated = False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, *, chunk_size: int | None = None):
        self.chunk_size = chunk_size
        self.iterated = True
        yield from self.chunks


class FakeStream:
    def __init__(self, response: FakeResponse):
        self.response = response

    def __enter__(self) -> FakeResponse:
        return self.response

    def __exit__(self, *_args) -> None:
        return None


def _item(payload: bytes) -> dict:
    return {
        "paper_uid": "arxiv:2504.16054",
        "source_id": "2504.16054",
        "year": 2025,
        "version": 1,
        "pdf": {
            "source_url": "https://example.test/paper.pdf",
            "expected_size": len(payload),
            "expected_sha256": hashlib.sha256(payload).hexdigest(),
        },
    }


def test_linked_pdf_download_is_chunked_and_atomically_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = fitz.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    response = FakeResponse([payload[:3], payload[3:700_000], payload[700_000:]])
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )

    assert subscriber._download_linked_pdf(tmp_path, _item(payload)) is True

    target = tmp_path / "80 Attachments/Papers/2025/2504.16054/v1.pdf"
    assert target.read_bytes() == payload
    assert response.chunk_size == 1024 * 1024
    assert not target.with_name("v1.pdf.tmp").exists()


def test_invalid_download_never_replaces_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"<html>authentication required</html>"
    response = FakeResponse([payload])
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )

    with pytest.raises(ValueError, match="not a PDF"):
        subscriber._download_linked_pdf(tmp_path, _item(payload))

    target = tmp_path / "80 Attachments/Papers/2025/2504.16054/v1.pdf"
    assert not target.exists()
    assert not target.with_name("v1.pdf.tmp").exists()


def test_declared_oversize_is_rejected_before_streaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item(b"%PDF-small")
    item["pdf"]["expected_size"] = 100 * 1024 * 1024 + 1
    called = False

    def stream(*_args, **_kwargs):
        nonlocal called
        called = True
        return FakeStream(FakeResponse([]))

    monkeypatch.setattr(pdf_download.httpx, "stream", stream)

    with pytest.raises(ValueError, match="Refusing PDF larger"):
        subscriber._download_linked_pdf(tmp_path, item)
    assert called is False


def test_stream_that_exceeds_limit_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-" + b"x" * 20
    response = FakeResponse([payload[:8], payload[8:]])
    monkeypatch.setattr(subscriber, "MAX_LINKED_PDF_BYTES", 10)
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )
    item = _item(payload)
    item["pdf"].pop("expected_size")

    with pytest.raises(ValueError, match="exceeds 10 bytes"):
        subscriber._download_linked_pdf(tmp_path, item)

    target = tmp_path / "80 Attachments/Papers/2025/2504.16054/v1.pdf"
    assert not target.exists()
    assert not target.with_name("v1.pdf.tmp").exists()


def test_cancelled_download_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-" + b"x" * 100
    response = FakeResponse([payload[:20], payload[20:]])
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )

    class CancelAfterFirstChunk:
        checks = 0

        def raise_if_cancelled(self, **_kwargs) -> None:
            self.checks += 1
            if self.checks >= 3:
                raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        subscriber._download_linked_pdf(
            tmp_path,
            _item(payload),
            cancellation_token=CancelAfterFirstChunk(),
        )

    target = tmp_path / "80 Attachments/Papers/2025/2504.16054/v1.pdf"
    assert not target.exists()
    assert not target.with_name("v1.pdf.tmp").exists()


def _standalone_item(payload: bytes) -> dict:
    item = _item(payload)
    item.pop("year", None)
    return item


def test_standalone_rejects_oversized_content_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-small"
    response = FakeResponse([payload], content_length=11)
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )

    with pytest.raises(ValueError, match="larger than 10 bytes"):
        standalone_sync._download_pdf(tmp_path, _standalone_item(payload), maximum_size=10)

    assert response.iterated is False
    assert not list(tmp_path.rglob("*.tmp"))


def test_standalone_aborts_stream_after_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-" + b"x" * 20
    response = FakeResponse([payload[:8], payload[8:]])
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )
    item = _standalone_item(payload)
    item["pdf"].pop("expected_size")

    with pytest.raises(ValueError, match="exceeds 10 bytes"):
        standalone_sync._download_pdf(tmp_path, item, maximum_size=10)

    assert not list(tmp_path.rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_standalone_rejects_structurally_invalid_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-this is not a structurally valid document"
    response = FakeResponse([payload])
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(response),
    )

    with pytest.raises(ValueError, match="structurally invalid"):
        standalone_sync._download_pdf(tmp_path, _standalone_item(payload))

    assert not list(tmp_path.rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_standalone_rejects_expected_size_and_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = fitz.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(FakeResponse([payload])),
    )
    item = _standalone_item(payload)
    item["pdf"]["expected_size"] = len(payload) + 1
    with pytest.raises(ValueError, match="size mismatch"):
        standalone_sync._download_pdf(tmp_path, item)
    assert not list(tmp_path.rglob("*.tmp"))

    item["pdf"]["expected_size"] = len(payload)
    item["pdf"]["expected_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        standalone_sync._download_pdf(tmp_path, item)
    assert not list(tmp_path.rglob("*.tmp"))


def test_standalone_network_error_removes_partial_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenResponse(FakeResponse):
        def iter_bytes(self, *, chunk_size: int | None = None):
            yield b"%PDF-partial"
            raise httpx.ReadError("connection lost")

    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(BrokenResponse([])),
    )
    item = _standalone_item(b"%PDF-partial")
    item["pdf"].pop("expected_size")

    with pytest.raises(httpx.ReadError):
        standalone_sync._download_pdf(tmp_path, item)

    assert not list(tmp_path.rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_standalone_cancel_removes_partial_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"%PDF-" + b"x" * 20
    monkeypatch.setattr(
        pdf_download.httpx,
        "stream",
        lambda *_args, **_kwargs: FakeStream(FakeResponse([payload[:8], payload[8:]])),
    )

    class CancelAfterFirstChunk:
        checks = 0

        def raise_if_cancelled(self, **_kwargs) -> None:
            self.checks += 1
            if self.checks >= 3:
                raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        standalone_sync._download_pdf(
            tmp_path,
            _standalone_item(payload),
            cancellation_token=CancelAfterFirstChunk(),
        )

    assert not list(tmp_path.rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_existing_valid_pdf_is_reused_without_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = fitz.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    item = _standalone_item(payload)
    target = tmp_path / "documents/zotero/2504.16054.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _path: (_ for _ in ()).throw(AssertionError("read_bytes forbidden")),
    )

    assert standalone_sync._download_pdf(tmp_path, item) is False
