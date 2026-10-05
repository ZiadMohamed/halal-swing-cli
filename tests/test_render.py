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


def _envelope(**overrides) -> Envelope:
    gates = [{"name": name, "status": "pass"} for name in PIPELINE_GATES]
    base = dict(
        ticker="AAPL",
        decision=DecisionKind.ENTER_LONG,
        reasons=[],
        warnings=[{"code": ReasonCode.WARN_EXDIV, "message": "Ordinary ex-div. Numbers were not changed."}],
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
        gates=gates,
        stage="checklist",
    )
    base.update(overrides)
    return Envelope.model_validate(base)


def test_card_is_three_sections_without_the_hash_or_the_note():
    text = render_text(_envelope())
    assert "AAPL  BUY" in text
    assert "Volume breakout matched" in text
    assert "config_hash" not in text
    assert "Not financial advice" not in text
    assert "Prices" in text
    assert "Technical" in text
    assert "Buy 100.50 USD" in text
    assert "Stop 97.25 USD" in text
    assert "Profit 107.00 USD" in text
    assert "42 shares" in text
    assert "Dollars at risk 136.50 USD" in text
    assert "Total cost 4221.00 USD" in text
    assert "1.5 times the 14-day average daily range" in text
    assert "Ex-dividend" in text
    assert "WARN_EXDIV" not in text
    assert f"Next open Africa/Cairo {_CAIRO_SUMMER}" in text
    assert "America/New_York" not in text
    assert "data_auth:" not in text
    assert text.endswith(f"Next open Africa/Cairo {_CAIRO_SUMMER}\n")
    ny = datetime.fromisoformat(_NY_SUMMER)
    cairo = datetime.fromisoformat(_CAIRO_SUMMER)
    assert ny == cairo


def test_explain_adds_gates_and_is_longer_than_the_card():
    card = render_text(_envelope())
    explained = render_text(_envelope(), explain=True)
    assert "AAPL  BUY" in explained
    assert "Buy 100.50 USD" in explained
    assert "Stop 97.25 USD" in explained
    assert "Profit 107.00 USD" in explained
    assert "42 shares" in explained
    assert f"Next open America/New_York {_NY_SUMMER}" in explained
    assert "config_hash" in explained
    assert explained.endswith(DISCLAIMER + "\n")
    assert "Not financial advice" not in card
    assert "stage: checklist" in explained
    for name in PIPELINE_GATES:
        assert f"  {name}: pass" in explained
    assert len(explained) > len(card)


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
    assert "AAPL  NO TRADE" in text
    assert "Inside the blackout." in text
    assert "No buy price" in text
    assert "Ex-dividend" in text
    assert "setup=" not in text
    assert "America/New_York" not in text
    assert f"Next open Africa/Cairo {_CAIRO_SUMMER}" in text
    assert "  earnings: no_trade" not in text
    assert "Not financial advice" not in text
    explained = render_text(
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
        ),
        explain=True,
    )
    assert "stage: partial" in explained
    assert "  earnings: no_trade" in explained


def test_explain_names_a_skeleton_when_no_gate_has_run():
    text = render_text(
        _envelope(
            decision=DecisionKind.NO_TRADE,
            reasons=[{"code": ReasonCode.NO_MARKET_DATA, "message": "no bars"}],
            warnings=[],
            confidence=None,
            side=None,
            plan=None,
            data={"status": "not_loaded"},
            gates=[{"name": name, "status": "not_run"} for name in PIPELINE_GATES],
            stage="skeleton",
        ),
        explain=True,
    )
    assert "AAPL  NO TRADE" in text
    assert "no bars" in text
    assert "stage: skeleton — data and brain not run" in text
    assert "  data_auth: not_run" in text
    assert text.endswith(DISCLAIMER + "\n")


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
    assert "America/New_York" not in text
    assert f"Next open Africa/Cairo {_CAIRO_WINTER}" in text
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
    assert "America/New_York" not in text
    assert f"Next open Africa/Cairo {_CAIRO_SUMMER}" in text


def test_configured_user_zone_replaces_cairo():
    text = render_text(_envelope(), user_tz="Europe/London")
    assert "Next open Europe/London 2026-10-05T14:30:00+01:00" in text
    assert "America/New_York" not in text
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
    assert "Next open not-a-timestamp" in text
    assert "Africa/Cairo" not in text
    assert "brain not run" not in text


def test_warning_text_does_not_change_plan_numbers():
    clean = _envelope(warnings=[])
    noisy = _envelope(
        warnings=[{"code": ReasonCode.WARN_EXDIV, "message": "Headline says target 424242 and size 99999."}],
    )
    clean_text = render_text(clean)
    noisy_text = render_text(noisy)
    assert "Ex-dividend" in noisy_text
    assert "424242" not in noisy_text
    assert "99999" not in noisy_text
    assert _price_block(clean_text) == _price_block(noisy_text)
    assert _clock_lines(clean_text) == _clock_lines(noisy_text)
    clean_json = json.loads(render_json(clean))
    noisy_json = json.loads(render_json(noisy))
    assert noisy_json["plan"] == clean_json["plan"]
    assert noisy_json["plan"]["entry"] == 100.5
    assert noisy_json["plan"]["stop"] == 97.25
    assert noisy_json["plan"]["target"] == 107.0
    assert noisy_json["plan"]["size_shares"] == 42
    assert noisy_json["plan"]["next_open"] == _OPEN
    assert "research" not in noisy_json


def test_json_is_one_document_and_keeps_the_locked_fields():
    raw = render_json(_envelope())
    payload, end = json.JSONDecoder().raw_decode(raw)
    assert raw[end:].strip() == ""
    assert raw.endswith("\n")
    assert payload["schema_version"] == "2.0.0"
    assert payload["config_hash"] == _HASH
    assert payload["shariah"]["screened"] is False
    assert payload["decision"] == "ENTER_LONG"
    assert payload["plan"]["size_shares"] == 42
    assert "research" not in payload
    assert "ENTER_SHORT" not in raw


def _price_block(text: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index("Prices") + 1
    end = lines.index("Technical")
    return lines[start:end]


def _clock_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("Next open ")]
