from __future__ import annotations

import json
import re
from pathlib import Path

from paperflow.annotations.markdown_renderer import END, START
from paperflow.annotations.models import Annotation
from paperflow.obsidian.frontmatter import read_note

MACHINE_RE = re.compile(re.escape(START) + r"\s*<!--\s*(\{.*?\})\s*-->", re.S)


def parse_annotation(path: Path) -> tuple[Annotation, str]:
    _, body = read_note(path)
    match = MACHINE_RE.search(body)
    if not match:
        raise ValueError(f"{path}: PaperFlow annotation boundary is missing")
    annotation = Annotation.model_validate(json.loads(match.group(1)))
    start = body.find(START)
    end = body.find(END, start)
    unknown = body[:start]
    if end >= 0:
        unknown += body[end + len(END):]
    return annotation, unknown.strip()
