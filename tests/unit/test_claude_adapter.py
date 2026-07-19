from __future__ import annotations

from paperflow.ai.claude_adapter import _claude_cli_schema


def test_claude_cli_schema_omits_unsupported_draft_declaration() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"answer": {"type": "string"}},
    }

    cli_schema = _claude_cli_schema(schema)

    assert "$schema" not in cli_schema
    assert cli_schema["properties"] == schema["properties"]
    assert schema["$schema"].endswith("/2020-12/schema")
