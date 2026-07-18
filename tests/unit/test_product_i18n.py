from __future__ import annotations

import json
from pathlib import Path

from paperflow.i18n import normalize_locale, resolve_locale, tr


def test_locale_follows_obsidian_marker_and_preserves_original_papers(
    tmp_path: Path,
) -> None:
    marker = tmp_path / ".paperflow/state/obsidian-locale.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps({"locale": "zh-CN", "source": "obsidian"}),
        encoding="utf-8",
    )

    locale = resolve_locale(tmp_path, configured="auto", fallback="en")

    assert locale.locale == "zh-CN"
    assert locale.source == "obsidian"
    assert locale.is_chinese
    assert tr(locale.locale, "validation.passed") == "校验通过"


def test_locale_supports_english_and_configured_override(tmp_path: Path) -> None:
    app = tmp_path / ".obsidian/app.json"
    app.parent.mkdir(parents=True)
    app.write_text(json.dumps({"language": "zh"}), encoding="utf-8")

    automatic = resolve_locale(tmp_path, configured="auto", fallback="en")
    configured = resolve_locale(tmp_path, configured="en", fallback="zh-CN")

    assert automatic.locale == "zh-CN"
    assert automatic.source == "obsidian-app"
    assert configured.locale == "en"
    assert configured.source == "paperflow.yaml"
    assert tr(configured.locale, "validation.passed") == "Validation passed"
    assert normalize_locale("zh_Hans") == "zh-CN"
