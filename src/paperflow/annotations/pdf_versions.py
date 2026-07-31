from __future__ import annotations

from pathlib import Path
from typing import Any

from paperflow.utils import atomic_json, iso_beijing, sha256_file


def build_pdf_index(vault: Path, paper_uid: str, versions: list[dict[str, Any]],
                    *, current_version: int) -> Path:
    normalized = []
    for item in versions:
        path = (vault / str(item["path"])).resolve()
        path.relative_to(vault.resolve())
        if not path.exists() or path.suffix.casefold() != ".pdf":
            raise ValueError(f"Invalid PDF version path: {item['path']}")
        normalized.append({
            "version": int(item["version"]),
            "path": path.relative_to(vault).as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        })
    if current_version not in {item["version"] for item in normalized}:
        raise ValueError("current PDF version is absent from the index")
    target = vault / ".paperflow/data/derived/pdf-index" / f"{paper_uid.replace(':', '_')}.json"
    atomic_json(target, {
        "type": "paperflow-pdf-index", "schema_version": 1,
        "paper_uid": paper_uid, "current_version": current_version,
        "updated_at": iso_beijing(),
        "versions": sorted(normalized, key=lambda value: value["version"]),
    })
    return target
