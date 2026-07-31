from __future__ import annotations
from pathlib import Path
import httpx
from paperflow.utils import atomic_write, sha256_bytes


def download_pdf(url: str, destination: Path, max_size_mb: int = 100, timeout: int = 60, transport=None) -> str:
    if destination.exists():
        payload = destination.read_bytes()
        if not payload.startswith(b"%PDF"):
            raise ValueError(f"Existing destination is not a PDF: {destination}")
        # Version-addressed PDFs are immutable. A refresh reuses the verified
        # local object rather than replacing it with mutable remote bytes.
        return sha256_bytes(payload)
    limit = max_size_mb * 1024 * 1024
    with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport, headers={"User-Agent": "PaperFlow/0.1"}) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError(f"PDF exceeds {max_size_mb} MB")
    payload = bytes(data)
    if not payload.startswith(b"%PDF"):
        raise ValueError(f"Invalid PDF header (content-type={content_type})")
    if "pdf" not in content_type and content_type not in {"", "application/octet-stream"}:
        raise ValueError(f"Unexpected PDF MIME type: {content_type}")
    atomic_write(destination, payload)
    return sha256_bytes(payload)

