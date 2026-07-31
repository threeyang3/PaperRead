"""Safe adapters parse data only and never execute PDF, plugin, or repository code."""

from paperflow.annotations.anchors import parse_pdf_link

__all__ = ["parse_pdf_link"]
