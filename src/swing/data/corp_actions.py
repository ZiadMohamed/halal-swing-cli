"""Flag bar series whose split adjustment does not agree with the vendor."""

from __future__ import annotations

from collections.abc import Sequence

from swing.data.models import Adjustment, BarSeries, CorpActionAssessment, CorporateAction, DailyBar

# Price ratio (today close / prior close) for common forward and reverse splits.
_PRICE_RATIOS = (
    10.0,
    5.0,
    4.0,
    3.0,
    2.0,
    1.5,
    2.0 / 3.0,
    0.5,
    1.0 / 3.0,
    0.25,
    0.2,
    0.1,
    1.0 / 1.5,
)
_RATIO_TOL = 0.03
_GAP = 0.40
_RECON_TOL = 0.02
_REASON_ORDER = ("adjustment_mismatch", "missing_split", "unexplained_gap")


def assess_corp_actions(
    bars: Sequence[DailyBar],
    actions: Sequence[CorporateAction],
    *,
    adjustment: Adjustment,
) -> CorpActionAssessment:
    """Return whether Chat 3 should refuse this series.

    Reasons, when present:

    - `missing_split`: the unadjusted close jumps by a common split ratio and
      the vendor did not list a split on that session.
    - `adjustment_mismatch`: a listed split or dividend does not match the
      vendor's adjusted series, or split-adjusted closes do not reconstruct
      from the unadjusted closes and the listed splits.
    - `unexplained_gap`: the adjusted close moves 40% or more and no listed
      split or cash dividend accounts for it.
    """
    reasons: set[str] = set()
    if len(bars) < 2:
        return CorpActionAssessment(False, ())
    splits = _splits(actions)
    dividends = _dividends(actions)
    if adjustment == "split":
        _check_reconstruction(bars, splits, reasons)
    for prev, bar in zip(bars, bars[1:], strict=False):
        _check_pair(prev, bar, splits, dividends, adjustment, reasons)
    ordered = tuple(name for name in _REASON_ORDER if name in reasons)
    return CorpActionAssessment(bool(ordered), ordered)


def apply_assessment(series: BarSeries, actions: Sequence[CorporateAction]) -> BarSeries:
    assessment = assess_corp_actions(series.bars, actions, adjustment=series.adjustment)
    return BarSeries(
        ticker=series.ticker,
        provider=series.provider,
        bars=series.bars,
        corp_action_suspect=assessment.suspect,
        corp_action_reasons=assessment.reasons,
        adjustment=series.adjustment,
    )


def _splits(actions: Sequence[CorporateAction]) -> dict:
    found = {}
    for action in actions:
        if action.kind != "split" or not action.split_to or not action.split_from:
            continue
        found[action.session] = action.split_to / action.split_from
    return found


def _dividends(actions: Sequence[CorporateAction]) -> dict:
    found = {}
    for action in actions:
        if action.kind != "dividend" or action.amount is None:
            continue
        found[action.session] = action.amount
    return found


def _check_reconstruction(bars: Sequence[DailyBar], splits: dict, reasons: set[str]) -> None:
    for bar in bars:
        factor = 1.0
        for session, split_factor in splits.items():
            if session > bar.session:
                factor *= split_factor
        if bar.raw_close <= 0 or bar.close <= 0 or factor <= 0:
            reasons.add("adjustment_mismatch")
            return
        expected = bar.raw_close / factor
        if abs(bar.close / expected - 1.0) > _RECON_TOL:
            reasons.add("adjustment_mismatch")
            return


def _check_pair(
    prev: DailyBar,
    bar: DailyBar,
    splits: dict,
    dividends: dict,
    adjustment: Adjustment,
    reasons: set[str],
) -> None:
    if min(prev.raw_close, prev.close, bar.raw_close, bar.close) <= 0:
        reasons.add("adjustment_mismatch")
        return
    raw_ratio = bar.raw_close / prev.raw_close
    adj_ratio = bar.close / prev.close
    raw_ret = raw_ratio - 1.0
    adj_ret = adj_ratio - 1.0
    split_factor = splits.get(bar.session)
    dividend = dividends.get(bar.session)

    if split_factor is not None:
        expected_raw = 1.0 / split_factor
        if _near(raw_ratio, expected_raw) and abs(adj_ret) >= 0.25:
            reasons.add("adjustment_mismatch")
        elif _near(adj_ratio, expected_raw) and abs(adj_ret) >= 0.25:
            reasons.add("adjustment_mismatch")
    elif _looks_like_split(raw_ratio):
        reasons.add("missing_split")

    if abs(adj_ret) >= _GAP and not _gap_explained(
        raw_ret, adj_ret, prev.raw_close, split_factor, raw_ratio, dividend, adjustment, reasons
    ):
        reasons.add("unexplained_gap")

    if (
        adjustment == "split_and_dividend"
        and dividend is not None
        and dividend / prev.raw_close >= 0.02
        and abs(raw_ratio - adj_ratio) <= 0.01
        and abs(raw_ret + dividend / prev.raw_close) <= max(0.03, 0.3 * dividend / prev.raw_close)
    ):
        reasons.add("adjustment_mismatch")


def _gap_explained(
    raw_ret: float,
    adj_ret: float,
    prev_raw: float,
    split_factor: float | None,
    raw_ratio: float,
    dividend: float | None,
    adjustment: Adjustment,
    reasons: set[str],
) -> bool:
    if split_factor is not None and _near(raw_ratio, 1.0 / split_factor) and abs(adj_ret) < 0.25:
        return True
    if dividend is None or prev_raw <= 0:
        return False
    drop = dividend / prev_raw
    if adjustment == "split" and abs(raw_ret + drop) <= max(0.05, 0.25 * drop):
        return True
    if adjustment == "split_and_dividend" and drop >= 0.02 and abs(adj_ret + drop) <= max(0.03, 0.25 * drop):
        reasons.add("adjustment_mismatch")
        return True
    return False


def _looks_like_split(price_ratio: float) -> bool:
    return any(_near(price_ratio, ratio) for ratio in _PRICE_RATIOS)


def _near(value: float, target: float, tol: float = _RATIO_TOL) -> bool:
    if target == 0:
        return False
    return abs(value - target) / abs(target) <= tol
