"""Private, plugin-independent paper annotation protocol."""

from .models import Annotation, AnnotationAnchor, AnnotationRevision, PaperReview
from .service import AnnotationService

__all__ = [
    "Annotation",
    "AnnotationAnchor",
    "AnnotationRevision",
    "AnnotationService",
    "PaperReview",
]
