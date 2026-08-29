"""Chart rendering for SMC foundational skill validation (Structure, Supply & Demand,
Liquidity). Draws pre-computed annotations only -- see renderer.py's module docstring
for the "no recomputation" rule.
"""
from __future__ import annotations

from .renderer import RenderResult, render_annotations, render_chart

__all__ = ["RenderResult", "render_chart", "render_annotations"]
