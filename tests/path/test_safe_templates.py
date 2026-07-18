from __future__ import annotations

from pathlib import Path

import pytest

from paperflow.paths.templates import (
    PathTemplateError,
    SafePathTemplate,
    resolve_inside,
    safe_component,
)


def test_template_renders_allowlisted_variables_and_filters() -> None:
    template = SafePathTemplate(
        "{{year}}/{{first_author|slug|lower}}/"
        "{{title|truncate:18|slug}}-{{paper_id}}.pdf"
    )
    rendered = template.render(
        {
            "year": "2026",
            "first_author": "Ada Lovelace",
            "title": "Embodied Intelligence: A Study",
            "paper_id": "2607.00001",
        }
    )
    assert rendered == "2026/ada-lovelace/Embodied-Intellige-2607.00001.pdf"


@pytest.mark.parametrize(
    "template",
    [
        "../{{paper_id}}.json",
        "C:/{{paper_id}}.json",
        "/{{paper_id}}.json",
        "{{paper.__class__}}.json",
        "{{paper_id|eval}}.json",
        "{{paper_id",
    ],
)
def test_template_rejects_unsafe_syntax(template: str) -> None:
    with pytest.raises(PathTemplateError):
        SafePathTemplate(template)


def test_windows_names_illegal_characters_and_unicode_are_safe() -> None:
    assert safe_component("CON") == "_CON"
    assert safe_component('title<>:"/\\|?*') == "title"
    assert safe_component("机器人 学习") == "机器人-学习"
    assert not safe_component("paper. ").endswith((" ", "."))


def test_resolve_inside_never_escapes_root(tmp_path: Path) -> None:
    assert resolve_inside(tmp_path, "safe/paper.json").is_relative_to(
        tmp_path.resolve()
    )
    with pytest.raises(PathTemplateError):
        resolve_inside(tmp_path, "../escape.json")


def test_long_filename_is_truncated_without_losing_suffix() -> None:
    rendered = SafePathTemplate(
        "{{title}}.json", max_path_length=80
    ).render({"title": "x" * 500})
    assert len(rendered) <= 80
    assert rendered.endswith(".json")
