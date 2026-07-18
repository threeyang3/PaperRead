from __future__ import annotations
import re
import subprocess
from pathlib import Path
import fitz
from paperflow.utils import atomic_write

HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?(?:abstract|introduction|related work|method|experiments?|results?|conclusion|limitations?)\b", re.I)


def extract_pdf(pdf: Path, output: Path) -> dict:
    pages, headings = [], []
    try:
        document = fitz.open(pdf)
        for index, page in enumerate(document):
            text = page.get_text("text")
            pages.append(f"\n\n--- PAGE {index + 1} ---\n{text}")
            headings.extend(line.strip() for line in text.splitlines() if HEADING_RE.match(line.strip()))
    except Exception as first_error:
        try:
            result = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True, timeout=120)
            pages = [result.stdout.decode("utf-8", errors="replace")]
        except Exception as second_error:
            raise RuntimeError(f"PDF extraction failed: {first_error}; fallback: {second_error}") from second_error
    text = "".join(pages)
    atomic_write(output, text)
    return {"text_path": str(output), "page_count": len(pages), "headings": headings, "character_count": len(text)}
