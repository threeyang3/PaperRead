from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote

from paperflow.annotations.models import AnnotationAnchor, FragmentSelector, TextQuoteSelector


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


PDF_SELECTION = re.compile(r"^\d+,\d+,\d+,\d+$")


def parse_pdf_link(
    value: str, *, vault: Path, pdf_version: int, selected_text: str = ""
) -> AnnotationAnchor:
    value = html.unescape(value)
    if not value.startswith("[[") or not value.endswith("]]"):
        raise ValueError("expected an Obsidian PDF wikilink")
    target = value[2:-2].split("|", 1)[0]
    path_text, separator, fragment = target.partition("#")
    query = parse_qs(fragment, keep_blank_values=True) if separator else {}
    page = int(query.get("page", ["1"])[0])
    selection = unquote(query.get("selection", [""])[0])
    pdf_selection = selection if PDF_SELECTION.fullmatch(selection) else ""
    # PaperFlow 1.4 treated selection= as quote text. Keep those links readable,
    # but never render free text as a PDF++ selection coordinate.
    quote_text = selected_text.strip() or (selection if selection and not pdf_selection else "")
    color = unquote(query.get("color", [""])[0]) if pdf_selection else ""
    path = (vault / path_text).resolve()
    try:
        path.relative_to(vault.resolve())
    except ValueError as exc:
        raise ValueError("PDF link escapes the Vault") from exc
    if not path.exists() or path.suffix.casefold() != ".pdf":
        raise ValueError(f"PDF does not exist: {path_text}")
    quote_selector = TextQuoteSelector(exact=quote_text) if quote_text else None
    return AnnotationAnchor(
        pdf_version=pdf_version,
        pdf_sha256=sha256_file(path),
        pdf_path=path.relative_to(vault).as_posix(),
        page=page,
        fragment_selector=FragmentSelector(page=page),
        text_quote_selector=quote_selector,
        pdf_selection=pdf_selection,
        highlight_color=color,
        selected_text_sha256=(
            hashlib.sha256(quote_text.encode("utf-8")).hexdigest() if quote_text else ""
        ),
    )
