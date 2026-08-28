"""The only module that touches matplotlib. render_chart() draws exactly the
annotations it is given -- candles, a market_structure.models.StructureTier, a list of
supply_demand.models.ZoneResult, and/or a list of liquidity.models.LiquidityLevel -- and
never recomputes or reinterprets any of them (spec: "the renderer must consume
structured annotations, it must not independently reinterpret the market").

Each layer is optional (None/[] skips it) so callers can produce a structure-only,
zones-only, liquidity-only, or combined chart from the same function, matching the
"toggle layers" requirement without a separate detector per chart type.

Zone extension policy: ZoneResult carries an origin_time but no "current extension"
timestamp, so every zone rectangle is drawn from origin_time to the chart's right edge
(the last candle's time) -- a deterministic, always-computable default, not a visual
choice; status (FRESH/MITIGATED/etc.) is encoded via color/alpha instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")  # headless: this is a validation tool, not an interactive UI
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from liquidity.models import LiquidityLevel, LiquidityStatus
from market_structure.models import StructurePoint, StructurePointKind, StructureTier
from strategy_engine.session import Candle
from supply_demand.models import ZoneResult, ZoneRole, ZoneStatus

_SWING_LABELS = {
    StructurePointKind.HH: "HH", StructurePointKind.HL: "HL",
    StructurePointKind.LH: "LH", StructurePointKind.LL: "LL",
    StructurePointKind.SWING_HIGH: "H", StructurePointKind.SWING_LOW: "L",
}
_EVENT_LABELS = {
    StructurePointKind.BULLISH_BOS: "BOS+", StructurePointKind.BEARISH_BOS: "BOS-",
    StructurePointKind.BULLISH_CHOCH: "CHOCH+", StructurePointKind.BEARISH_CHOCH: "CHOCH-",
}
_ZONE_COLORS = {ZoneRole.SUPPLY: "tab:red", ZoneRole.DEMAND: "tab:green", ZoneRole.REFERENCE: "tab:gray"}
_ZONE_ALPHA = {
    ZoneStatus.FRESH: 0.35, ZoneStatus.TOUCHED: 0.25, ZoneStatus.MITIGATED: 0.15,
    ZoneStatus.INVALIDATED: 0.08, ZoneStatus.UNKNOWN: 0.10,
}
_LIQUIDITY_STYLE = {
    LiquidityStatus.UNSWEPT: dict(linestyle="-", alpha=0.9),
    LiquidityStatus.SWEPT: dict(linestyle="--", alpha=0.9),
    LiquidityStatus.RECLAIMED: dict(linestyle=":", alpha=0.6),
    LiquidityStatus.CONSUMED: dict(linestyle=":", alpha=0.4),
    LiquidityStatus.UNKNOWN: dict(linestyle=":", alpha=0.3),
}


@dataclass(frozen=True)
class RenderResult:
    out_path: str
    candle_count: int
    swing_label_count: int
    event_marker_count: int
    zone_rect_count: int
    liquidity_line_count: int


def render_chart(
    candles: Sequence[Candle],
    out_path: str,
    structure: Optional[StructureTier] = None,
    zones: Optional[Iterable[ZoneResult]] = None,
    liquidity: Optional[Iterable[LiquidityLevel]] = None,
    liquidity_roles: Optional[dict] = None,
    title: Optional[str] = None,
) -> RenderResult:
    """liquidity_roles: optional {liquidity.hierarchy.level_id(level): role} map --
    appends the role (TARGET/INDUCEMENT_CANDIDATE) to that level's line label. Purely a
    label lookup; drawn coordinates still come only from the LiquidityLevel objects
    themselves."""
    zones = list(zones) if zones is not None else []
    liquidity = list(liquidity) if liquidity is not None else []

    fig, ax = plt.subplots(figsize=(12, 6))

    candle_count = _draw_candles(ax, candles)
    swing_label_count = _draw_structure_swings(ax, structure) if structure else 0
    event_marker_count = _draw_structure_events(ax, structure) if structure else 0
    zone_rect_count = _draw_zones(ax, zones, candles[-1].time if candles else None)
    liquidity_line_count = _draw_liquidity(ax, liquidity, candles, liquidity_roles)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    if title:
        ax.set_title(title)
    if zone_rect_count or liquidity_line_count:  # only these layers add labeled artists
        ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=100)
    plt.close(fig)

    return RenderResult(
        out_path=out_path, candle_count=candle_count, swing_label_count=swing_label_count,
        event_marker_count=event_marker_count, zone_rect_count=zone_rect_count,
        liquidity_line_count=liquidity_line_count,
    )


def _draw_candles(ax, candles: Sequence[Candle]) -> int:
    for c in candles:
        t = mdates.date2num(c.time)
        color = "tab:green" if c.close >= c.open else "tab:red"
        ax.add_line(plt.Line2D([t, t], [c.low, c.high], color=color, linewidth=0.8))
        body_low, body_high = min(c.open, c.close), max(c.open, c.close)
        ax.add_patch(Rectangle((t - 0.015, body_low), 0.03, max(body_high - body_low, 1e-9), color=color))
    return len(candles)


def _draw_structure_swings(ax, tier: StructureTier) -> int:
    for point in tier.swings:
        label = _SWING_LABELS.get(point.kind, point.kind.value)
        ax.annotate(label, (mdates.date2num(point.time_utc), point.price), fontsize=7, color="tab:blue",
                    xytext=(0, 6), textcoords="offset points", ha="center")
    return len(tier.swings)


def _draw_structure_events(ax, tier: StructureTier) -> int:
    for point in tier.events:
        label = _EVENT_LABELS.get(point.kind, point.kind.value)
        color = "tab:purple" if "BOS" in point.kind.value else "tab:orange"
        t = mdates.date2num(point.time_utc)
        ax.plot(t, point.price, marker="^", color=color, markersize=6)
        ax.annotate(label, (t, point.price), fontsize=7, color=color, xytext=(4, -10), textcoords="offset points")
    return len(tier.events)


def _draw_zones(ax, zones: List[ZoneResult], chart_end) -> int:
    count = 0
    for zone in zones:
        if zone.low is None or zone.high is None or zone.origin_time is None or chart_end is None:
            continue
        start = mdates.date2num(zone.origin_time)
        end = mdates.date2num(chart_end)
        color = _ZONE_COLORS.get(zone.role, "tab:gray")
        alpha = _ZONE_ALPHA.get(zone.status, 0.1)
        ax.add_patch(Rectangle((start, zone.low), max(end - start, 1e-9), zone.high - zone.low, color=color, alpha=alpha,
                                label=f"{zone.role.value} {zone.status.value}"))
        count += 1
    return count


def _draw_liquidity(ax, levels: List[LiquidityLevel], candles: Sequence[Candle], roles: Optional[dict] = None) -> int:
    if not candles:
        return 0
    x_start, x_end = mdates.date2num(candles[0].time), mdates.date2num(candles[-1].time)
    count = 0
    for level in levels:
        style = _LIQUIDITY_STYLE.get(level.status, dict(linestyle=":", alpha=0.5))
        color = "tab:cyan" if level.side.value == "BUY_SIDE" else "tab:pink"
        label = f"{level.side.value} {level.source}"
        if roles is not None:
            from liquidity.hierarchy import level_id  # local import: keeps hierarchy optional/decoupled
            role = roles.get(level_id(level))
            if role:
                label = f"{label} [{role}]"
        ax.plot([x_start, x_end], [level.price, level.price], color=color, linewidth=1.2, label=label, **style)
        count += 1
    return count
