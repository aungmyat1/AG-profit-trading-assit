"""Stateless C11: creation-anchored windows, frozen 1.1.2 selector reuse."""
import bisect
import datetime as dt
from collections.abc import Mapping

from large_smc_v112.targets import _candidate_target

from . import contract as C

HISTORY_MISSING = 'C11_CREATION_HISTORY_NOT_EVIDENCED'


def _creation_window(bars, timeframe, creation_close, capture_start):
    policy = C.SPEC['rules']['targets']['creation_window']
    lookback = policy['lookback_closed_bars'][timeframe]
    minimum = policy['minimum_closed_bars'][timeframe]
    if not bars or not isinstance(capture_start, str):
        return None
    try:
        origin = dt.datetime.fromisoformat(capture_start.replace('Z', '+00:00'))
        if origin.tzinfo is None:
            return None
        cutoff = creation_close-dt.timedelta(minutes=C.TIMEFRAME_MINUTES[timeframe])
        end = bisect.bisect_right(bars, cutoff, key=lambda b: b.time)
        window = list(bars[max(0, end-lookback):end])
        # Short initial captures are explicit; a clipped rolling history is not a capture start.
        if len(window) < minimum or (len(window) < lookback and bars[0].time != origin):
            return None
        if any(a.time >= b.time for a, b in zip(window, window[1:])):
            return None
        if window[0].time < origin:
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    return window


def _candidate_target_at_creation(opportunity, creation_close, history):
    """Only immutable creation inputs affect selection; no retained engine state.

    The caller supplies recorded history and its true capture-start timestamps.
    Missing creation evidence blocks selection, rather than substituting a current fallback.
    """
    missing = {'price': None, 'tier': None, 'source': None, 'c11_source': None,
               'reason': HISTORY_MISSING, 'creation_bar_close_utc': creation_close.isoformat()}
    if not isinstance(history, Mapping) or not isinstance(history.get('capture_start_utc'), Mapping):
        return missing
    windows = {tf: _creation_window(history.get(tf), tf, creation_close,
                                    history['capture_start_utc'].get(tf)) for tf in ('M5', 'H1')}
    if any(value is None for value in windows.values()):
        return missing
    record = _candidate_target({}, opportunity, windows['H1'], windows['M5'])
    return {**record, 'creation_bar_close_utc': creation_close.isoformat(),
            'creation_window_start_utc': {tf: bars[0].time.isoformat() for tf, bars in windows.items()},
            'creation_window_closed_bars': {tf: len(bars) for tf, bars in windows.items()},
            'selection_mode': 'STATELESS_CREATION_ANCHORED', 'verification_status': 'NOT_VERIFIED'}
