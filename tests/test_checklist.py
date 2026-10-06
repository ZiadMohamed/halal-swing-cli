"""Checklist brain fixtures. No network. Bars are synthetic."""

import math
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from swing.analyze import analyze
from swing.brain.checklist import ChecklistBrain, earnings_window
from swing.brain.indicators import atr, ema
from swing.brain.positions import OpenPosition
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import BarSeries, DailyBar, DividendEvent, EarningsEvent, MarketData
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope

NEXT_OPEN = "2026-10-01T09:30:00-04:00"
SIGNAL_DAY = date(2026, 9, 30)


def _days(count: int, end: date) -> list[date]:
    found: list[date] = []
    cursor = end
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(found))


def _series(
    closes: list[float],
    end: date,
    *,
    high_pad: float = 0.4,
    low_pad: float = 0.4,
    **last: float,
) -> tuple[DailyBar, ...]:
    sessions = _days(len(closes), end)
    bars: list[DailyBar] = []
    for index, (session, close) in enumerate(zip(sessions, closes)):
        high = close + high_pad
        low = close - low_pad
        volume = 1_000_000.0
        if index == len(closes) - 1:
            close = last.get("close", close)
            high = last.get("high", close + high_pad)
            low = last.get("low", close - low_pad)
            volume = last.get("volume", volume)
        bars.append(
            DailyBar(
                session=session,
                open=close,
                high=high,
                low=low,
                close=close,
                volume=volume,
                raw_close=1.0,
            )
        )
    return tuple(bars)


def _bo_bars(end: date = SIGNAL_DAY) -> tuple[DailyBar, ...]:
    closes = [100 + index * 0.05 for index in range(80)]
    prior_high = max(close + 0.4 for close in closes[-21:-1])
    last_close = prior_high + 1
    closes[-1] = last_close
    return _series(
        closes,
        end,
        close=last_close,
        high=last_close + 0.2,
        low=last_close - 0.2,
        volume=3_000_000,
    )


def _pb_bars(end: date = SIGNAL_DAY) -> tuple[DailyBar, ...]:
    closes = [80 + index * 0.4 for index in range(80)]
    touch = ema(closes, 20)
    assert touch is not None
    return _series(closes, end, low=touch - 0.05, volume=1_000_000)


def _rsi_bars(end: date = SIGNAL_DAY) -> tuple[DailyBar, ...]:
    up = [100 + index * 0.2 for index in range(220)]
    dipped = up[:-8] + [up[-9] - 0.3 * step for step in range(1, 9)]
    return _series(dipped, end)


def _market(
    bars: tuple[DailyBar, ...],
    *,
    next_open: str | None = NEXT_OPEN,
    earnings: tuple[EarningsEvent, ...] = (),
    dividends: tuple[DividendEvent, ...] = (),
    events_known: bool = True,
    suspect: bool = False,
    reasons: tuple[str, ...] = (),
    status: str = "ok",
) -> MarketData:
    return MarketData(
        ticker="AAPL",
        status=status,  # type: ignore[arg-type]
        bars_provider="yfinance",
        events_provider="finnhub",
        bars=BarSeries(
            ticker="AAPL",
            provider="yfinance",
            bars=bars,
            corp_action_suspect=suspect,
            corp_action_reasons=reasons,
            adjustment="split_and_dividend",
        ),
        earnings=earnings,
        dividends=dividends,
        next_open=next_open,
        errors=(),
        events_known=events_known,
    )


def _config(equity: float | None = 100_000.0, **extra: object) -> SwingConfig:
    payload: dict[str, object] = {}
    if equity is not None or "account" not in extra:
        payload["account"] = {"equity_usd": equity}
    payload.update(extra)
    return SwingConfig.model_validate(payload)


def _gate(result, name: str) -> str:
    return next(gate.status for gate in result.gates if gate.name == name)


def _codes(result) -> set[ReasonCode]:
    return {item.code for item in (*result.reasons, *result.warnings)}


def test_blackout_window_uses_nyse_sessions_across_the_july_holiday():
    start, end = earnings_window(NyseCalendar(), date(2026, 7, 6), 2, 1)
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 7)


def test_breakout_enters_long_from_the_signal_close_with_a_1_5_atr_stop_and_2r_target():
    bars = _bo_bars()
    market = _market(bars)
    result = ChecklistBrain().evaluate("AAPL", _config(), market)
    assert result.decision is DecisionKind.ENTER_LONG
    assert result.confidence == "checklist_only"
    assert result.side == "long"
    assert result.reasons == ()
    plan = result.plan
    assert plan is not None
    assert plan.setup == "BO_RVOL"
    assert plan.side == "long"
    assert plan.entry == pytest.approx(bars[-1].close)
    reading = atr([bar.high for bar in bars], [bar.low for bar in bars], [bar.close for bar in bars], 14)
    assert reading is not None
    assert plan.stop == pytest.approx(plan.entry - 1.5 * reading)
    assert plan.target == pytest.approx(plan.entry + 2 * (plan.entry - plan.stop))
    assert plan.next_open == NEXT_OPEN
    assert plan.size_shares == math.floor(100_000 * 0.01 / (plan.entry - plan.stop))
    assert plan.size_shares >= 1
    assert all(gate.status == "pass" for gate in result.gates)
    assert "ENTER_SHORT" not in result.decision.value


def test_pullback_and_rsi2_can_each_be_the_winning_setup():
    pullback = ChecklistBrain().evaluate("AAPL", _config(), _market(_pb_bars()))
    assert pullback.decision is DecisionKind.ENTER_LONG
    assert pullback.plan is not None and pullback.plan.setup == "PB_EMA"
    mean_rev = ChecklistBrain().evaluate("AAPL", _config(), _market(_rsi_bars()))
    assert mean_rev.decision is DecisionKind.ENTER_LONG
    assert mean_rev.plan is not None and mean_rev.plan.setup == "RSI2_MR"


def test_losing_setups_are_suppressed_and_do_not_block_the_breakout():
    closes = [100 + index * 0.05 for index in range(80)]
    prior_high = max(close + 0.4 for close in closes[-21:-1])
    last_close = prior_high + 1
    closes[-1] = last_close
    touch = ema(closes, 20)
    assert touch is not None
    bars = _series(closes, SIGNAL_DAY, close=last_close, high=last_close + 0.2, low=touch - 1, volume=3_000_000)
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(bars))
    assert result.decision is DecisionKind.ENTER_LONG
    assert result.plan is not None and result.plan.setup == "BO_RVOL"
    suppressed = [item for item in result.warnings if item.code is ReasonCode.SETUP_SUPPRESSED]
    assert len(suppressed) == 1
    assert "PB_EMA" in suppressed[0].message
    assert "RSI2_MR" not in suppressed[0].message


def test_suspect_series_does_not_run_indicators():
    market = _market(_bo_bars(), suspect=True, reasons=("missing_split",))
    result = ChecklistBrain().evaluate("AAPL", _config(), market)
    assert result.decision is DecisionKind.NO_TRADE
    assert result.plan is None
    assert result.confidence is None
    assert result.reasons[0].code is ReasonCode.CORP_ACTION_SUSPECT
    assert "missing_split" in result.reasons[0].message
    assert "Prices loaded" in result.reasons[0].message
    assert all("No usable daily prices" not in line for line in result.analysis)
    assert result.analysis[0].startswith("Breakout: not checked.")
    assert _gate(result, "data_auth") == "no_trade"
    assert _gate(result, "liquidity") == "not_run"
    assert _gate(result, "setup_mutex") == "not_run"


def test_split_shaped_gap_names_the_two_closes():
    bars = _series([100.0, 50.0], SIGNAL_DAY)
    result = ChecklistBrain().evaluate(
        "AAPL",
        _config(),
        _market(bars, suspect=True, reasons=("unexplained_gap",)),
    )
    message = result.reasons[0].message
    assert result.reasons[0].code is ReasonCode.CORP_ACTION_SUSPECT
    assert "100.00" in message
    assert "50.00" in message
    assert "2-for-1" in message
    assert "Prices loaded" in message
    assert all("No usable daily prices" not in line for line in result.analysis)
    joined = " ".join(result.analysis)
    assert "did load" in joined


def test_missing_market_data_is_no_trade():
    result = ChecklistBrain().evaluate("AAPL", _config(), None)
    assert result.decision is DecisionKind.NO_TRADE
    assert result.reasons[0].code is ReasonCode.NO_MARKET_DATA
    assert result.plan is None
    assert _gate(result, "data_auth") == "no_trade"


def test_short_history_is_illiquid_and_does_not_reach_earnings():
    bars = _series([100.0] * 10, SIGNAL_DAY)
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(bars))
    assert result.reasons[0].code is ReasonCode.ILLIQUID
    assert _gate(result, "liquidity") == "no_trade"
    assert _gate(result, "earnings") == "not_run"


def test_zero_range_does_not_use_an_adr_gate():
    bars = _series([100.0] * 30, SIGNAL_DAY, high_pad=0.0, low_pad=0.0)
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(bars))
    assert result.decision is DecisionKind.NO_TRADE
    assert result.reasons[0].code is ReasonCode.NO_SETUP
    assert "adr" not in {gate.name for gate in result.gates}
    assert _gate(result, "heat") == "pass"
    assert _gate(result, "setup_mutex") == "no_trade"


def test_no_matching_setup_is_no_trade():
    closes = [100 + index * 0.01 for index in range(30)]
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(_series(closes, SIGNAL_DAY)))
    assert result.reasons[0].code is ReasonCode.NO_SETUP
    assert _gate(result, "setup_mutex") == "no_trade"
    assert _gate(result, "rr_stop") == "not_run"


def test_strict_earnings_blackout_uses_the_entry_session():
    earnings = (EarningsEvent(ticker="AAPL", report_date=date(2026, 10, 2), hour="amc"),)
    blocked = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), earnings=earnings))
    assert blocked.decision is DecisionKind.NO_TRADE
    assert blocked.reasons[0].code is ReasonCode.EARNINGS_BLACKOUT
    assert "amc" in blocked.reasons[0].message
    assert blocked.plan is None
    assert _gate(blocked, "earnings") == "no_trade"
    assert _gate(blocked, "setup_mutex") == "not_run"

    # Same print, but the fill is the session after the blackout ends.
    clear = ChecklistBrain().evaluate(
        "AAPL",
        _config(),
        _market(_bo_bars(), earnings=earnings, next_open="2026-10-06T09:30:00-04:00"),
    )
    assert clear.decision is DecisionKind.ENTER_LONG


def test_july_holiday_blackout_blocks_the_session_before_the_print():
    earnings = (EarningsEvent(ticker="AAPL", report_date=date(2026, 7, 6), hour="bmo"),)
    blocked = ChecklistBrain().evaluate(
        "AAPL",
        _config(),
        _market(_bo_bars(date(2026, 7, 1)), earnings=earnings, next_open="2026-07-02T09:30:00-04:00"),
    )
    assert blocked.reasons[0].code is ReasonCode.EARNINGS_BLACKOUT
    opened = ChecklistBrain().evaluate(
        "AAPL",
        _config(),
        _market(_bo_bars(date(2026, 7, 1)), earnings=earnings, next_open="2026-07-08T09:30:00-04:00"),
    )
    assert opened.decision is DecisionKind.ENTER_LONG


def test_unknown_earnings_calendar_does_not_enter_when_strict():
    market = _market(_bo_bars(), events_known=False, earnings=(), status="partial")
    blocked = ChecklistBrain().evaluate("AAPL", _config(), market)
    assert blocked.decision is DecisionKind.NO_TRADE
    assert blocked.reasons[0].code is ReasonCode.EARNINGS_UNKNOWN
    assert blocked.plan is None
    relaxed = ChecklistBrain().evaluate(
        "AAPL",
        _config(earnings={"strict": False}),
        market,
    )
    assert relaxed.decision is DecisionKind.ENTER_LONG


def test_known_empty_earnings_calendar_can_enter():
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), earnings=(), events_known=True))
    assert result.decision is DecisionKind.ENTER_LONG


def test_ordinary_exdiv_warns_and_a_large_distribution_blocks():
    small = DividendEvent(ticker="AAPL", ex_date=date(2026, 10, 1), amount=0.20, currency="USD")
    warned = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), dividends=(small,)))
    assert warned.decision is DecisionKind.ENTER_LONG
    assert any(item.code is ReasonCode.WARN_EXDIV for item in warned.warnings)
    assert _gate(warned, "soft_veto") == "warn"
    clean = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars()))
    assert warned.plan is not None and clean.plan is not None
    assert warned.plan.entry == pytest.approx(clean.plan.entry)
    assert warned.plan.stop == pytest.approx(clean.plan.stop)
    assert warned.plan.size_shares == clean.plan.size_shares

    large = DividendEvent(ticker="AAPL", ex_date=date(2026, 10, 1), amount=2.0, currency="USD")
    blocked = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), dividends=(large,)))
    assert blocked.decision is DecisionKind.NO_TRADE
    assert blocked.reasons[0].code is ReasonCode.EXDIV_BLOCK
    assert _gate(blocked, "soft_veto") == "block"
    assert _gate(blocked, "setup_mutex") == "not_run"

    strict = DividendEvent(ticker="AAPL", ex_date=date(2026, 10, 1), amount=0.10, currency="USD")
    strict_block = ChecklistBrain().evaluate(
        "AAPL",
        _config(exdiv={"strict": True}),
        _market(_bo_bars(), dividends=(strict,)),
    )
    assert strict_block.reasons[0].code is ReasonCode.EXDIV_BLOCK

    already_passed = DividendEvent(ticker="AAPL", ex_date=SIGNAL_DAY, amount=2.0, currency="USD")
    ignored = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), dividends=(already_passed,)))
    assert ignored.decision is DecisionKind.ENTER_LONG
    assert all(item.code is not ReasonCode.WARN_EXDIV for item in ignored.warnings)


def test_regime_gate_passes_without_a_spy_fetch():
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars()))
    assert result.decision is DecisionKind.ENTER_LONG
    assert _gate(result, "regime") == "pass"
    assert "spy_bars" not in ChecklistBrain.evaluate.__code__.co_varnames


def test_unset_equity_does_not_invent_a_size():
    result = ChecklistBrain().evaluate("AAPL", _config(equity=None), _market(_bo_bars()))
    assert result.decision is DecisionKind.NO_TRADE
    assert result.reasons[0].code is ReasonCode.EQUITY_UNSET
    assert "equity" in result.reasons[0].message.lower()
    assert result.plan is None
    assert result.confidence is None
    assert _gate(result, "setup_mutex") == "pass"
    assert _gate(result, "rr_stop") == "no_trade"
    assert _gate(result, "next_open") == "not_run"


def test_equity_of_zero_cannot_buy_a_share():
    result = ChecklistBrain().evaluate("AAPL", _config(equity=0), _market(_bo_bars()))
    assert result.reasons[0].code is ReasonCode.SIZE_BELOW_ONE_SHARE
    assert result.plan is None


def test_heat_and_position_count_stop_before_a_setup():
    bars = _bo_bars()
    market = _market(bars)
    full = tuple(OpenPosition(ticker=f"T{i}", risk_fraction=0.001, sector=f"s{i}") for i in range(4))
    counted = ChecklistBrain().evaluate("AAPL", _config(), market, positions=full)
    assert counted.reasons[0].code is ReasonCode.MAX_POSITIONS
    assert _gate(counted, "heat") == "no_trade"
    assert _gate(counted, "setup_mutex") == "not_run"

    heavy = tuple(OpenPosition(ticker=f"T{i}", risk_fraction=0.02, sector=f"s{i}") for i in range(3))
    total = ChecklistBrain().evaluate("AAPL", _config(), market, positions=heavy)
    assert total.reasons[0].code is ReasonCode.HEAT_LIMIT
    assert "total" in total.reasons[0].message.lower()

    crowded = (OpenPosition(ticker="MSFT", risk_fraction=0.025, sector="tech"),)
    sector = ChecklistBrain().evaluate("AAPL", _config(), market, positions=crowded, sector="tech")
    assert sector.reasons[0].code is ReasonCode.HEAT_LIMIT
    assert "sector" in sector.reasons[0].message.lower()

    at_cap = (OpenPosition(ticker="MSFT", risk_fraction=0.02, sector="tech"),)
    allowed = ChecklistBrain().evaluate("AAPL", _config(), market, positions=at_cap, sector="tech")
    assert allowed.decision is DecisionKind.ENTER_LONG

    unnamed = tuple(OpenPosition(ticker=f"T{i}", risk_fraction=0.01) for i in range(3))
    still_open = ChecklistBrain().evaluate("AAPL", _config(), market, positions=unnamed, sector=None)
    assert still_open.decision is DecisionKind.ENTER_LONG


def test_missing_next_open_stops_after_the_plan_math():
    result = ChecklistBrain().evaluate("AAPL", _config(), _market(_bo_bars(), next_open=None))
    assert result.reasons[0].code is ReasonCode.NO_NEXT_OPEN
    assert result.plan is None
    assert _gate(result, "rr_stop") == "pass"
    assert _gate(result, "next_open") == "no_trade"


def test_analyze_loads_the_ticker_and_does_not_fetch_spy(monkeypatch):
    calls: list[str] = []

    def fake(ticker: str, config: SwingConfig, **kwargs):
        del config, kwargs
        calls.append(ticker)
        return _market(_bo_bars())

    monkeypatch.setattr("swing.analyze.load_market_data", fake)
    config = _config()
    entered = analyze("AAPL", config=config, env={}, fetch_market=True)
    again = analyze("AAPL", config=config, env={}, fetch_market=True)
    assert entered.decision is DecisionKind.ENTER_LONG
    assert entered.stage == "checklist"
    assert entered.plan is not None and entered.plan.setup == "BO_RVOL"
    assert entered.plan.model_dump() == again.plan.model_dump()  # type: ignore[union-attr]
    assert calls == ["AAPL", "AAPL"]
    source = ChecklistBrain.evaluate.__code__.co_varnames
    assert "research" not in source
    assert "spy_bars" not in source


def test_analyze_stage_is_partial_until_every_gate_has_run():
    partial = analyze("AAPL", config=_config(), env={}, market=_market(_bo_bars(), events_known=False))
    assert partial.decision is DecisionKind.NO_TRADE
    assert partial.stage == "partial"
    assert partial.confidence is None
    assert any(gate.status == "not_run" for gate in partial.gates)
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"account": {"mode": "margin"}})


def test_envelope_accepts_the_widened_stages():
    for stage in ("skeleton", "partial", "checklist"):
        envelope = Envelope(
            ticker="AAPL",
            decision=DecisionKind.NO_TRADE,
            reasons=[],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            shariah={"screened": False, "status": "user_supplied", "note": "n"},
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
            gates=[],
            stage=stage,
        )
        assert envelope.stage == stage
    with pytest.raises(ValidationError):
        Envelope(
            ticker="AAPL",
            decision=DecisionKind.NO_TRADE,
            reasons=[],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            shariah={"screened": False, "status": "user_supplied", "note": "n"},
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
            gates=[],
            stage="finished",
        )
