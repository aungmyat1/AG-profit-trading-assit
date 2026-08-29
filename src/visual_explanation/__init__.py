"""SMC_VISUAL_EXPLANATION_V1 -- portable annotation model over SMC_CONDITIONAL_ENTRY_V2
combinations. See builder.py's module docstring for what this deliberately does and does
not do (no independent recomputation, no coupling to matplotlib).
"""
from .builder import build_visual_explanation
from .models import (
    ANNOTATION_BOX,
    ANNOTATION_LABEL,
    ANNOTATION_LINE,
    ANNOTATION_MARKER,
    SMC_VISUAL_EXPLANATION_V1,
    Annotation,
    SMCVisualExplanation,
)

__all__ = [
    "build_visual_explanation", "Annotation", "SMCVisualExplanation", "SMC_VISUAL_EXPLANATION_V1",
    "ANNOTATION_BOX", "ANNOTATION_LINE", "ANNOTATION_MARKER", "ANNOTATION_LABEL",
]
