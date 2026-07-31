from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from paperflow.data.store import persist_layer_records


def test_quarantined_legacy_fields_are_preserved_locally(tmp_path: Path) -> None:
    record = {
        "paper_uid": "arxiv:2607.20001",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2607.20001",
        "paper_arxiv_version": 1,
        "paper_title": "Legacy paper",
        "my_comment": "private",
        "lab_note": "keep locally",
        "reviewer_name": "anonymous",
        "private_rating": 4,
        "local_pdf_hint": "D:/Private/paper.pdf",
        "selection_coordinates": [1, 2, 3, 4],
    }

    persist_layer_records(tmp_path, record)

    quarantine = tmp_path / ".paperflow/data/quarantine/legacy-fields/2607.20001.json"
    assert quarantine.is_file()
    value = json.loads(quarantine.read_text(encoding="utf-8"))
    assert value["paper_uid"] == "arxiv:2607.20001"
    assert value["fields"] == {
        "lab_note": "keep locally",
        "local_pdf_hint": "D:/Private/paper.pdf",
        "my_comment": "private",
        "private_rating": 4,
        "reviewer_name": "anonymous",
        "selection_coordinates": [1, 2, 3, 4],
    }


def test_public_schema_rejects_unknown_fields() -> None:
    schema = json.loads(
        (Path(__file__).parents[2] / "schemas/public-raw-paper.schema.json").read_text(
            encoding="utf-8"
        )
    )
    value = {
        "schema_version": 1,
        "paper_uid": "arxiv:2607.20001",
        "source": "arxiv",
        "source_id": "2607.20001",
        "source_version": 1,
        "metadata": {"paper_title": "Safe", "private_rating": 5},
        "source_license": "arXiv",
        "pdf_sha256": "",
        "my_comment": "private",
    }

    errors = list(Draft202012Validator(schema).iter_errors(value))

    assert len(errors) == 2
