from __future__ import annotations

from pathlib import Path

from paperflow.config import load_config
from paperflow.models import PaperMetadata
from paperflow.pipeline.import_paper import _year_paths
from paperflow.workspace import init_workspace


def test_new_import_uses_readable_title_and_id_suffix(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    cfg = load_config(tmp_path)
    metadata = PaperMetadata(
        paper_uid="arxiv:2303.04137",
        paper_arxiv_id="2303.04137",
        paper_arxiv_version=5,
        paper_title="Diffusion Policy: Visuomotor Policy Learning via Action Diffusion",
        paper_year=2023,
    )

    note, pdf, _, _ = _year_paths(cfg, metadata)

    assert note.relative_to(tmp_path).as_posix() == (
        "10 Papers/2023/Diffusion-Policy-2303.04137.md"
    )
    assert pdf.relative_to(tmp_path).as_posix() == (
        "80 Attachments/Papers/2023/2303.04137/v5.pdf"
    )
