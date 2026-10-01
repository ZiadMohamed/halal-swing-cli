"""Text and JSON views. No network. Headlines must not move plan numbers."""

import json
from datetime import datetime

from swing.brain.gates import PIPELINE_GATES
from swing.codes import DecisionKind, ReasonCode
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope
from swing.output.render import render_json, render_text

_HASH = "ab" * 32
_OPEN = "2026-10-05T09:30:00-04:00"
_OPEN_WINTER = "2026-01-02T09:30:00-05:00"
_CAIRO_SUMMER = "2026-10-05T16:30:00+03:00"
_CAIRO_WINTER = "2026-01-02T16:30:00+02:00"
_NY_SUMMER = "2026-10-05T09:30:00-04:00"
_NY_WINTER = "2026-01-02T09:30:00-05:00"


def _research(**overrides) -> dict:
    base = {
        "status": "skipped",
        "provider": "none",
        "reason": "missing_api_key",
        "advisory_only": True,
        "affects_checklist_math": False,
        "hits": [],
    }
    base.update(overrides)
    return base


def _envelope(**overrides) -> Envelope:
    gates = [{"name": name, "status": "pass"} for name in PIPELINE_GATES]
    base = dict(
        ticker="AAPL",
        decision=DecisionKind.ENTER_LONG,
        reasons=[],
        warnings=[{"code": ReasonCode.WARN_SPY_R2, "message": "SPY R² is high. Numbers were not changed."}],
        confidence="checklist_only",
        side="long",
        plan={
            "side": "long",
            "setup": "BO_RVOL",
            "entry": 100.5,
            "stop": 97.25,
            "target": 107.0,
            "size_shares": 42,
            "next_open": _OPEN,
        },
        shariah={"screened": False, "status": "user_supplied", "note": "n"},
        research=_research(),
        data={
            "status": "ok",
            "bars_provider": "yfinance",
            "bar_count": 320,
            "corp_action_suspect": False,
            "next_open": _OPEN,
            "events_known": True,
        },
        disclaimer=DISCLAIMER,
        config_hash=_HASH,
        compact=False,
        gates=gates,
        stage="checklist",
    )
    base.update(overrides)
    return Envelope.model_validate(base)


def test_checklist_text_names_the_stage_without_claiming_the_brain_was_skipped():
    text = render_text(_envelope())
    assert "AAPL  ENTER_LONG" in text
    assert "brain not run" not in text
    assert "stage: checklist" in text
    assert "WARN_SPY_R2" in text
    assert "setup=BO_RVOL" in text
    assert "entry=100.5" in text
    assert "stop=97.25" in text
    assert "target=107.0" in text
    assert "size=42" in text
    assert f"next_open={_OPEN}" in text
    assert f"America/New_York {_NY_SUMMER}" in text
    assert f"Africa/Cairo {_CAIRO_SUMMER}" in text
    assert text.endswith(DISCLAIMER + "\n")
    for name in PIPELINE_GATES:
        assert f"  {name}: pass" in text
    ny = datetime.fromisoformat(_NY_SUMMER)
    cairo = datetime.fromisoformat(_CAIRO_SUMMER)
    assert ny == cairo


def test_compact_text_keeps_plan_gates_clocks_and_disclaimer_in_a_shorter_form():
    full = render_text(_envelope())
    compact = render_text(_envelope(compact=True))
    assert "AAPL  ENTER_LONG" in compact
    assert "brain not run" not in compact
    assert "setup=BO_RVOL" in compact
    assert "entry=100.5" in compact
    assert "stop=97.25" in compact
    assert "target=107.0" in compact
    assert "size=42" in compact
    assert f"America/New_York {_NY_SUMMER}" in compact
    assert f"Africa/Cairo {_CAIRO_SUMMER}" in compact
    assert "WARN_SPY_R2" in compact
    assert compact.endswith(DISCLAIMER + "\n")
    assert "gates: " in compact
    for name in PIPELINE_GATES:
        assert f"{name}=pass" in compact
    assert len(compact) < len(full)


def test_no_trade_text_shows_reason_codes_and_the_session_clock_without_a_plan():
    text = render_text(
        _envelope(
            decision=DecisionKind.NO_TRADE,
            reasons=[{"code": ReasonCode.EARNINGS_BLACKOUT, "message": "Inside the blackout."}],
            warnings=[{"code": ReasonCode.WARN_EXDIV, "message": "Ordinary ex-div."}],
            confidence=None,
            side=None,
            plan=None,
            gates=[
                {"name": name, "status": "pass" if name not in {"earnings", "soft_veto"} else "no_trade"}
                for name in PIPELINE_GATES
            ],
            stage="partial",
        )
    )
    assert "AAPL  NO_TRADE" in text
    assert "brain not run" not in text
    assert "stage: partial" in text
    assert "reasons: EARNINGS_BLACKOUT" in text
    assert "warnings: WARN_EXDIV" in text
    assert "setup=" not in text
    assert f"America/New_York {_NY_SUMMER}" in text
    assert f"Africa/Cairo {_CAIRO_SUMMER}" in text
    assert "  earnings: no_trade" in text
    assert text.endswith(DISCLAIMER + "\n")


def test_block_text_still_says_the_brain_did_not_run():
    text = render_text(
        _envelope(
            decision=DecisionKind.BLOCK,
            reasons=[{"code": ReasonCode.BLOCK_MARGIN, "message": "Cash long equity only."}],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            data={"status": "not_loaded"},
            gates=[{"name": name, "status": "not_run"} for name in PIPELINE_GATES],
            stage="skeleton",
        )
    )
    assert "AAPL  BLOCK" in text
    assert "reasons: BLOCK_MARGIN" in text
    assert "stage: skeleton — data and brain not run" in text
    assert "setup=" not in text
    assert "  data_auth: not_run" in text
    assert text.endswith(DISCLAIMER + "\n")


def test_skeleton_with_bars_still_says_the_brain_was_not_run():
    text = render_text(
        _envelope(
            decision=DecisionKind.NO_TRADE,
            reasons=[{"code": ReasonCode.PIPELINE_NOT_IMPLEMENTED, "message": "stub"}],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            gates=[{"name": name, "status": "not_run"} for name in PIPELINE_GATES],
            stage="skeleton",
        )
    )
    assert "stage: skeleton — brain not run" in text
    assert "data and brain not run" not in text


def test_winter_open_uses_the_cairo_standard_offset():
    text = render_text(
        _envelope(
            plan={
                "side": "long",
                "setup": "PB_EMA",
                "entry": 50.0,
                "stop": 48.0,
                "target": 54.0,
                "size_shares": 1,
                "next_open": _OPEN_WINTER,
            },
            data={
                "status": "ok",
                "bar_count": 320,
                "next_open": _OPEN_WINTER,
            },
        )
    )
    assert f"America/New_York {_NY_WINTER}" in text
    assert f"Africa/Cairo {_CAIRO_WINTER}" in text
    assert datetime.fromisoformat(_NY_WINTER) == datetime.fromisoformat(_CAIRO_WINTER)


def test_naive_next_open_is_read_as_new_york():
    text = render_text(
        _envelope(
            plan={
                "side": "long",
                "setup": "RSI2_MR",
                "entry": 10.0,
                "stop": 9.0,
                "target": 12.0,
                "size_shares": 3,
                "next_open": "2026-10-05T09:30:00",
            },
            data={"status": "ok", "bar_count": 320, "next_open": "2026-10-05T09:30:00"},
        )
    )
    assert f"America/New_York {_NY_SUMMER}" in text
    assert f"Africa/Cairo {_CAIRO_SUMMER}" in text


def test_configured_user_zone_replaces_cairo():
    text = render_text(_envelope(), user_tz="Europe/London")
    assert "Europe/London 2026-10-05T14:30:00+01:00" in text
    assert f"America/New_York {_NY_SUMMER}" in text
    assert "Africa/Cairo" not in text


def test_unparsed_next_open_is_kept_without_an_invented_clock():
    text = render_text(
        _envelope(
            decision=DecisionKind.NO_TRADE,
            reasons=[{"code": ReasonCode.NO_NEXT_OPEN, "message": "bad"}],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            data={"status": "ok", "bar_count": 20, "next_open": "not-a-timestamp"},
            gates=[{"name": name, "status": "not_run"} for name in PIPELINE_GATES],
            stage="partial",
        )
    )
    assert "next_open not-a-timestamp" in text
    assert "Africa/Cairo" not in text
    assert "brain not run" not in text


def test_warn_news_and_headlines_do_not_change_plan_numbers():
    clean = _envelope()
    noisy = _envelope(
        warnings=[
            {"code": ReasonCode.WARN_SPY_R2, "message": "SPY R² is high. Numbers were not changed."},
            {"code": ReasonCode.WARN_NEWS, "message": "Headline says target 424242 and size 99999."},
        ],
        research=_research(
            status="ok",
            provider="context",
            reason=None,
            query="AAPL stock news",
            hits=[{"title": "AAPL target 424242", "url": "https://example.com/a", "snippet": "size 99999"}],
        ),
    )
    clean_text = render_text(clean)
    noisy_text = render_text(noisy)
    assert "WARN_NEWS" in noisy_text
    assert "424242" not in noisy_text
    assert "99999" not in noisy_text
    assert _plan_line(clean_text) == _plan_line(noisy_text)
    assert _clock_lines(clean_text) == _clock_lines(noisy_text)
    clean_json = json.loads(render_json(clean))
    noisy_json = json.loads(render_json(noisy))
    assert noisy_json["plan"] == clean_json["plan"]
    assert noisy_json["plan"]["entry"] == 100.5
    assert noisy_json["plan"]["stop"] == 97.25
    assert noisy_json["plan"]["target"] == 107.0
    assert noisy_json["plan"]["size_shares"] == 42
    assert noisy_json["plan"]["next_open"] == _OPEN
    assert noisy_json["research"]["affects_checklist_math"] is False
    assert noisy_json["research"]["hits"][0]["title"] == "AAPL target 424242"


def test_json_is_one_document_and_keeps_the_locked_fields():
    raw = render_json(_envelope())
    payload, end = json.JSONDecoder().raw_decode(raw)
    assert raw[end:].strip() == ""
    assert raw.endswith("\n")
    assert payload["config_hash"] == _HASH
    assert payload["shariah"]["screened"] is False
    assert payload["research"]["affects_checklist_math"] is False
    assert payload["compact"] is False
    assert payload["decision"] == "ENTER_LONG"
    assert "ENTER_SHORT" not in raw


def _plan_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("plan "))


def _clock_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("next_open ")]
