from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from paperflow.models import Analysis


def validate_analysis(data: dict, schema_path: Path | None = None) -> Analysis:
    if schema_path:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(data)
    return Analysis.model_validate(data)

