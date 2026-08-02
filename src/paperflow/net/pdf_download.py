"""Bounded, verified and atomic PDF downloads shared by all subscribers."""

from __future__ import annotations

import hashlib
import gc
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import fitz
import httpx


DEFAULT_MAX_PDF_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class DownloadedPdf:
    path: Path
    size: int
    sha256: str
    status: Literal["created", "reused"]


def _hash_and_header(path: Path) -> tuple[int, str, bytes]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        header = stream.read(5)
        digest.update(header)
        size += len(header)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest(), header


def _validate_structure(path: Path, *, source: str) -> None:
    document: fitz.Document | None = None
    valid = True
    try:
        document = fitz.open(filename=path, filetype="pdf")
        valid = document.page_count >= 1
    except Exception:
        valid = False
    finally:
        if document is not None:
            document.close()
    if not valid:
        # Raise outside the parser's exception handler so a partially
        # constructed PyMuPDF document cannot retain a Windows file handle.
        gc.collect()
        raise ValueError(f"PDF is structurally invalid: {source}") from None


def _check_expected(
    *,
    size: int,
    sha256: str,
    expected_size: int | None,
    expected_sha256: str,
    source: str,
) -> None:
    if expected_size is not None and size != expected_size:
        raise ValueError(f"Downloaded PDF size mismatch: {source}")
    if expected_sha256 and sha256 != expected_sha256.casefold():
        raise ValueError(f"Downloaded PDF checksum mismatch: {source}")


def download_pdf_safely(
    source_url: str,
    target: Path,
    *,
    expected_sha256: str = "",
    expected_size: int | None = None,
    maximum_size: int = DEFAULT_MAX_PDF_BYTES,
    cancellation_token: Any | None = None,
) -> DownloadedPdf:
    """Download one PDF without allowing partial or conflicting final files."""

    if maximum_size < 5:
        raise ValueError("maximum PDF size must be at least 5 bytes")
    if expected_size is not None:
        expected_size = int(expected_size)
        if expected_size < 5:
            raise ValueError(f"Downloaded PDF size mismatch: {source_url}")
        if expected_size > maximum_size:
            raise ValueError(f"Refusing PDF larger than {maximum_size} bytes: {source_url}")
    expected_sha256 = str(expected_sha256 or "").casefold()

    if target.exists():
        size, digest, header = _hash_and_header(target)
        if header != b"%PDF-":
            raise ValueError(f"Existing PDF has an invalid header: {target}")
        if size > maximum_size:
            raise ValueError(f"Existing PDF exceeds {maximum_size} bytes: {target}")
        _check_expected(
            size=size,
            sha256=digest,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            source=str(target),
        )
        _validate_structure(target, source=str(target))
        return DownloadedPdf(target, size, digest, "reused")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    digest = hashlib.sha256()
    size = 0
    header = bytearray()
    try:
        with httpx.stream("GET", source_url, timeout=60, follow_redirects=True) as response:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise ValueError("Invalid PDF Content-Length") from exc
                if declared_size < 0:
                    raise ValueError("Invalid PDF Content-Length")
                if declared_size > maximum_size:
                    raise ValueError(f"Refusing PDF larger than {maximum_size} bytes: {source_url}")
            with tempfile.NamedTemporaryFile(
                mode="xb",
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as output:
                temporary = Path(output.name)
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if cancellation_token is not None:
                        cancellation_token.raise_if_cancelled()
                    if not chunk:
                        continue
                    next_size = size + len(chunk)
                    if next_size > maximum_size:
                        raise ValueError(
                            f"Downloaded PDF exceeds {maximum_size} bytes: {source_url}"
                        )
                    if len(header) < 5:
                        header.extend(chunk[: 5 - len(header)])
                    digest.update(chunk)
                    size = next_size
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())

        if bytes(header) != b"%PDF-":
            raise ValueError(f"Downloaded file is not a PDF: {source_url}")
        if temporary is None:
            raise RuntimeError("PDF temporary file was not created")
        _validate_structure(temporary, source=source_url)
        computed = digest.hexdigest()
        _check_expected(
            size=size,
            sha256=computed,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            source=source_url,
        )
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        if target.exists():
            existing_size, existing_hash, existing_header = _hash_and_header(target)
            if existing_header == b"%PDF-" and existing_size == size and existing_hash == computed:
                return DownloadedPdf(target, size, computed, "reused")
            raise FileExistsError(f"PDF target changed during download: {target}")
        os.replace(temporary, target)
        temporary = None
        return DownloadedPdf(target, size, computed, "created")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except PermissionError:
                # PyMuPDF may defer releasing a failed parser's Windows handle
                # until its partially constructed document is collected.
                gc.collect()
                temporary.unlink(missing_ok=True)


__all__ = ["DEFAULT_MAX_PDF_BYTES", "DownloadedPdf", "download_pdf_safely"]
