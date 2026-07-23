from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import fitz
import httpx

from paperflow.utils import atomic_json


CAPTION_RE = re.compile(
    r"^\s*(?:(?:extended\s+data\s+)?(?:figure|fig\.?)|图)\s*"
    r"([0-9]+[a-z]?)\s*[\.:：]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
ARCHITECTURE_TERMS = {
    "architecture",
    "architectural",
    "block diagram",
    "framework",
    "hardware design",
    "method overview",
    "model overview",
    "overview",
    "pipeline",
    "schematic",
    "sensor design",
    "system design",
    "system overview",
    "training and inference",
    "workflow",
}
RESULT_TERMS = {
    "accuracy",
    "ablation",
    "benchmark",
    "comparison",
    "evaluation",
    "performance",
    "quantitative",
    "result",
    "success rate",
}
CONTEXT_TERMS = {
    "demonstration",
    "hardware",
    "manipulation task",
    "real robot",
    "robot setup",
    "sensor",
    "task overview",
}
GENERATED_IMAGE_RE = re.compile(r"^figure-[0-9a-z-]+-p[0-9]+\.png$")
REFERENCE_START_RE = re.compile(
    r"^(?:shows?|depicts?|illustrates?|presents?|provides?)\b",
    re.IGNORECASE,
)
ARXIV_ID_RE = re.compile(r"^(?:arxiv:)?([0-9]{4}\.[0-9]{4,5})(?:v([0-9]+))?$", re.I)
MAX_HTML_IMAGE_BYTES = 25 * 1024 * 1024
HTML_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "source", "track", "wbr",
}


@dataclass(frozen=True)
class CaptionCandidate:
    page_index: int
    figure_number: str
    caption: str
    rectangle: fitz.Rect
    kind: str
    score: float


@dataclass(frozen=True)
class HtmlFigure:
    figure_number: str
    caption: str
    source_url: str


class _ArxivFigureParser(HTMLParser):
    """Extract single-image captioned figures from arXiv's LaTeXML HTML."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url.rstrip("/") + "/"
        self.depth = 0
        self.images: list[str] = []
        self.caption_parts: list[str] = []
        self.in_caption = False
        self.figures: list[HtmlFigure] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set(str(values.get("class") or "").split())
        if tag == "figure" and "ltx_figure" in classes and self.depth == 0:
            self.depth = 1
            self.images = []
            self.caption_parts = []
            return
        if not self.depth:
            return
        if tag == "img" and values.get("src"):
            self.images.append(urljoin(self.base_url, str(values["src"])))
        if tag in HTML_VOID_TAGS:
            return
        self.depth += 1
        if tag == "figcaption":
            self.in_caption = True

    def handle_data(self, data: str) -> None:
        if self.depth and self.in_caption:
            self.caption_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in HTML_VOID_TAGS:
            return
        if not self.depth:
            return
        if tag == "figcaption":
            self.in_caption = False
        self.depth -= 1
        if tag != "figure" or self.depth:
            return
        caption = _normalized_text(" ".join(self.caption_parts))
        match = CAPTION_RE.match(caption)
        if match and len(self.images) == 1:
            self.figures.append(
                HtmlFigure(
                    figure_number=match.group(1).lower(),
                    caption=_normalized_text(match.group(2)),
                    source_url=self.images[0],
                )
            )
        self.images = []
        self.caption_parts = []


def _safe_arxiv_image_url(url: str, paper_ref: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "arxiv.org"
        and parsed.path.startswith(f"/html/{paper_ref}/")
    )


def _arxiv_html_figures(
    arxiv_id: str,
    version: int,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, HtmlFigure], httpx.Client] | tuple[dict[str, HtmlFigure], None]:
    match = ARXIV_ID_RE.fullmatch(arxiv_id.strip())
    if not match:
        return {}, None
    paper_ref = f"{match.group(1)}v{version}"
    html_url = f"https://arxiv.org/html/{paper_ref}"
    client = httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(12.0, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "PaperFlow/1.5 (figure extraction)"},
    )
    try:
        response = client.get(html_url)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            client.close()
            return {}, None
        parser = _ArxivFigureParser(html_url)
        parser.feed(response.text)
        figures = {
            item.figure_number: item
            for item in parser.figures
            if _safe_arxiv_image_url(item.source_url, paper_ref)
        }
        return figures, client
    except (httpx.HTTPError, UnicodeError):
        client.close()
        return {}, None


def _fetch_html_png(client: httpx.Client, figure: HtmlFigure) -> tuple[bytes, int, int] | None:
    try:
        response = client.get(figure.source_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        payload = response.content
        if content_type != "image/png" or not payload or len(payload) > MAX_HTML_IMAGE_BYTES:
            return None
        pixmap = fitz.Pixmap(payload)
        if pixmap.width < 80 or pixmap.height < 60:
            return None
        return payload, pixmap.width, pixmap.height
    except (httpx.HTTPError, RuntimeError, ValueError):
        return None


def _normalized_text(value: str) -> str:
    return " ".join(value.replace("\u00ad", "").split())


def _classify(caption: str) -> tuple[str, float]:
    lowered = caption.casefold()
    architecture_hits = sum(term in lowered for term in ARCHITECTURE_TERMS)
    result_hits = sum(term in lowered for term in RESULT_TERMS)
    result_led = re.match(
        r"^(?:ablation|benchmark|comparison|evaluation|performance|"
        r"quantitative|results?)\b",
        lowered,
    )
    if result_led or (result_hits >= 2 and result_hits > architecture_hits):
        return "result", 62.0 + result_hits * 4
    if architecture_hits:
        return "architecture", 100.0 + architecture_hits * 8
    if result_hits:
        return "result", 62.0 + result_hits * 4
    context_hits = sum(term in lowered for term in CONTEXT_TERMS)
    if context_hits:
        return "figure", 52.0 + context_hits * 3
    return "figure", 40.0


def _caption_candidates(document: fitz.Document) -> list[CaptionCandidate]:
    candidates: list[CaptionCandidate] = []
    for page_index, page in enumerate(document):
        for block in page.get_text("blocks"):
            text = _normalized_text(str(block[4]))
            match = CAPTION_RE.match(text)
            if not match:
                continue
            figure_number = match.group(1).lower()
            caption = _normalized_text(match.group(2))
            if len(caption) < 8:
                continue
            kind, score = _classify(caption)
            if figure_number.rstrip("abcdefghijklmnopqrstuvwxyz") in {"1", "2"}:
                score += 12
            score += max(0, 12 - page_index)
            if REFERENCE_START_RE.match(caption):
                score -= 60
            candidates.append(
                CaptionCandidate(
                    page_index=page_index,
                    figure_number=figure_number,
                    caption=caption,
                    rectangle=fitz.Rect(block[:4]),
                    kind=kind,
                    score=score,
                )
            )
    best_by_number: dict[str, CaptionCandidate] = {}
    for candidate in candidates:
        existing = best_by_number.get(candidate.figure_number)
        if existing is None or candidate.score > existing.score:
            best_by_number[candidate.figure_number] = candidate
    return list(best_by_number.values())


def _select_candidates(
    candidates: list[CaptionCandidate],
    max_assets: int,
    *,
    quality_threshold: float = 48.0,
) -> list[CaptionCandidate]:
    """Select a variable number of non-duplicate, high-value figures."""
    ranked = sorted(candidates, key=lambda item: (-item.score, item.page_index))
    selected: list[CaptionCandidate] = []
    covered: set[str] = set()
    selected_terms: list[set[str]] = []
    remaining = list(ranked)
    while remaining and len(selected) < max_assets:
        scored: list[tuple[float, CaptionCandidate, set[str]]] = []
        for candidate in remaining:
            terms = {
                term
                for term in re.findall(r"[a-z0-9]{3,}", candidate.caption.casefold())
                if term not in {"figure", "shows", "using", "with", "from", "that"}
            }
            duplicate = max(
                (
                    len(terms & previous) / max(1, len(terms | previous))
                    for previous in selected_terms
                ),
                default=0.0,
            )
            coverage_bonus = 14.0 if candidate.kind not in covered else 0.0
            marginal = candidate.score + coverage_bonus - duplicate * 45.0
            scored.append((marginal, candidate, terms))
        marginal, candidate, terms = max(
            scored, key=lambda item: (item[0], -item[1].page_index)
        )
        required_coverage = candidate.kind in {"architecture", "result"} and candidate.kind not in covered
        if marginal < quality_threshold and not required_coverage:
            break
        selected.append(candidate)
        selected_terms.append(terms)
        covered.add(candidate.kind)
        remaining.remove(candidate)

    kind_order = {"architecture": 0, "result": 1, "figure": 2}
    return sorted(
        selected,
        key=lambda item: (
            kind_order[item.kind],
            -item.score,
            item.page_index,
            item.figure_number,
        ),
    )


def _intersects_horizontally(left: fitz.Rect, right: fitz.Rect) -> bool:
    overlap = min(left.x1, right.x1) - max(left.x0, right.x0)
    return overlap > min(left.width, right.width) * 0.15


def _visual_rectangles(
    page: fitz.Page,
    caption: fitz.Rect,
    *,
    require_horizontal_overlap: bool = True,
) -> list[fitz.Rect]:
    page_rect = page.rect
    minimum_area = page_rect.get_area() * 0.004
    rectangles: list[fitz.Rect] = []
    for image in page.get_image_info():
        rectangle = fitz.Rect(image["bbox"])
        if (
            rectangle.width >= 60
            and rectangle.height >= 35
            and rectangle.get_area() >= minimum_area
        ):
            rectangles.append(rectangle)
    for drawing in page.get_drawings():
        rectangle = fitz.Rect(drawing["rect"])
        if (
            rectangle.width >= 45
            and rectangle.height >= 25
            and rectangle.get_area() >= minimum_area
        ):
            rectangles.append(rectangle)
    return [
        rectangle
        for rectangle in rectangles
        if rectangle.y0 < caption.y0
        and caption.y0 - rectangle.y1 < page_rect.height * 0.55
        and (
            not require_horizontal_overlap
            or
            caption.width > page_rect.width * 0.55
            or _intersects_horizontally(rectangle, caption)
        )
    ]


def _crop_rectangle(page: fitz.Page, candidate: CaptionCandidate) -> fitz.Rect:
    page_rect = page.rect
    caption = candidate.rectangle
    visual_rectangles = _visual_rectangles(
        page,
        caption,
        require_horizontal_overlap=candidate.kind != "architecture",
    )
    if candidate.kind == "architecture":
        margin = 18
        if visual_rectangles:
            content = fitz.Rect(visual_rectangles[0])
            for rectangle in visual_rectangles[1:]:
                content.include_rect(rectangle)
            content.include_rect(caption)
            if (
                content.width > page_rect.width * 0.55
                or caption.width > page_rect.width * 0.55
            ):
                x0, x1 = margin, page_rect.width - margin
            else:
                x0 = max(margin, content.x0 - 12)
                x1 = min(page_rect.width - margin, content.x1 + 12)
            safe_top = max(
                margin,
                caption.y0 - page_rect.height * 0.58,
            )
            return fitz.Rect(
                x0,
                min(safe_top, max(margin, content.y0 - 14)),
                x1,
                min(page_rect.height - margin, content.y1 + 6),
            )
        return fitz.Rect(
            margin,
            max(margin, caption.y0 - page_rect.height * 0.48),
            page_rect.width - margin,
            min(page_rect.height - margin, caption.y1 + 6),
        )
    if visual_rectangles:
        content = fitz.Rect(visual_rectangles[0])
        for rectangle in visual_rectangles[1:]:
            content.include_rect(rectangle)
        content.include_rect(caption)
        clip = fitz.Rect(
            content.x0 - 12,
            content.y0 - 12,
            content.x1 + 12,
            content.y1 + 6,
        )
    else:
        margin = 24
        if caption.width < page_rect.width * 0.55:
            midpoint = page_rect.width / 2
            if caption.x0 + caption.width / 2 < midpoint:
                x0, x1 = margin, midpoint - 6
            else:
                x0, x1 = midpoint + 6, page_rect.width - margin
        else:
            x0, x1 = margin, page_rect.width - margin
        clip = fitz.Rect(
            x0,
            max(margin, caption.y0 - page_rect.height * 0.42),
            x1,
            min(page_rect.height - margin, caption.y1 + 6),
        )
    clip &= page_rect
    return clip


def _safe_asset_directory(root: Path, asset_dir: Path) -> Path:
    resolved_root = root.resolve()
    resolved_asset_dir = asset_dir.resolve()
    try:
        resolved_asset_dir.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Visual asset directory must stay inside the vault") from exc
    return resolved_asset_dir


def extract_visual_assets(
    pdf_path: Path,
    asset_dir: Path,
    *,
    root: Path,
    paper_uid: str,
    max_assets: int = 12,
    quality_threshold: float = 48.0,
    dpi: int = 180,
    arxiv_id: str = "",
    arxiv_version: int = 1,
    html_transport: httpx.BaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Extract caption-backed paper figures as rebuildable derived assets."""
    if max_assets < 0:
        raise ValueError("max_assets must be non-negative")
    asset_dir = _safe_asset_directory(root, asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)
    pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assets: list[dict[str, Any]] = []
    generated_names: set[str] = set()
    html_figures: dict[str, HtmlFigure] = {}
    html_client: httpx.Client | None = None
    if arxiv_id:
        html_figures, html_client = _arxiv_html_figures(
            arxiv_id,
            arxiv_version,
            transport=html_transport,
        )
    try:
        with fitz.open(pdf_path) as document:
            candidates = _select_candidates(
                _caption_candidates(document),
                max_assets,
                quality_threshold=quality_threshold,
            )
            for candidate in candidates:
                page = document[candidate.page_index]
                safe_number = re.sub(r"[^0-9a-z]+", "-", candidate.figure_number)
                filename = f"figure-{safe_number}-p{candidate.page_index + 1}.png"
                target = asset_dir / filename
                temporary = target.with_name(f".{target.name}.tmp.png")
                html_figure = html_figures.get(candidate.figure_number)
                downloaded = (
                    _fetch_html_png(html_client, html_figure)
                    if html_client is not None and html_figure is not None
                    else None
                )
                if downloaded is not None:
                    payload, width, height = downloaded
                    temporary.write_bytes(payload)
                    source_type = "arxiv-html"
                    source_url = html_figure.source_url
                else:
                    clip = _crop_rectangle(page, candidate)
                    if clip.width < 80 or clip.height < 60:
                        continue
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(dpi / 72, dpi / 72),
                        clip=clip,
                        alpha=False,
                    )
                    pixmap.save(temporary)
                    width, height = pixmap.width, pixmap.height
                    source_type = "pdf-crop"
                    source_url = ""
                temporary.replace(target)
                generated_names.add(filename)
                asset = {
                    "id": f"figure-{safe_number}",
                    "figure_number": candidate.figure_number,
                    "kind": candidate.kind,
                    "caption": candidate.caption,
                    "page": candidate.page_index + 1,
                    "path": target.relative_to(root.resolve()).as_posix(),
                    "width": width,
                    "height": height,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "score": round(candidate.score, 2),
                    "source_type": source_type,
                }
                if source_url:
                    asset["source_url"] = source_url
                assets.append(asset)
    finally:
        if html_client is not None:
            html_client.close()
    manifest_path = asset_dir / "manifest.json"
    if manifest_path.exists():
        for child in asset_dir.iterdir():
            if (
                child.is_file()
                and GENERATED_IMAGE_RE.fullmatch(child.name)
                and child.name not in generated_names
            ):
                child.unlink()
    atomic_json(
        manifest_path,
        {
            "schema_version": 1,
            "paper_uid": paper_uid,
            "pdf_sha256": pdf_sha256,
            "assets": assets,
        },
    )
    return assets


def refresh_record_visuals(
    root: Path,
    record: dict[str, Any],
    *,
    max_assets: int = 12,
    quality_threshold: float = 48.0,
) -> dict[str, Any]:
    pdf_relative = str(record.get("paper_pdf_path") or "")
    if not pdf_relative:
        raise ValueError(f"{record.get('paper_uid', 'paper')} has no local PDF")
    pdf_path = (root / pdf_relative).resolve()
    try:
        pdf_path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Paper PDF path must stay inside the vault") from exc
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    extraction = dict(record.get("extraction") or {})
    extraction["visual_assets"] = extract_visual_assets(
        pdf_path,
        pdf_path.with_suffix(".assets"),
        root=root,
        paper_uid=str(record["paper_uid"]),
        max_assets=max_assets,
        quality_threshold=quality_threshold,
        arxiv_id=str(record.get("paper_arxiv_id") or ""),
        arxiv_version=int(record.get("paper_version") or record.get("source_version") or 1),
    )
    extraction["visual_extraction_status"] = (
        "complete" if extraction["visual_assets"] else "no-captioned-figures"
    )
    extraction.pop("visual_extraction_error", None)
    record["extraction"] = extraction
    return record
