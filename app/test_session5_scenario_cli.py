import json
import io
import sys

import pytest

from app.testing.session5_scenario_harness import (
    DETERMINISTIC_CERTIFICATION,
    REAL_AVA_LANGUAGE,
)
from app.testing import session5_scenario_runner as cli
from app.api import test_chat as scenario_api


def test_turn_cli_accepts_explicit_real_ava_language():
    args = cli._parser().parse_args([
        "TURN", "--language-mode", REAL_AVA_LANGUAGE, "hello there",
    ])
    assert args.language_mode == REAL_AVA_LANGUAGE
    assert args.message == ["hello there"]


def test_turn_cli_keeps_backward_compatible_deterministic_default():
    args = cli._parser().parse_args(["TURN", "hello"])
    assert args.language_mode == DETERMINISTIC_CERTIFICATION


@pytest.mark.parametrize("mode", (
    REAL_AVA_LANGUAGE,
    DETERMINISTIC_CERTIFICATION,
))
def test_turn_cli_dispatches_the_explicit_language_mode(monkeypatch, capsys, mode):
    calls = []

    class Runner:
        def turn(self, message, *, language_mode, require_language_mode):
            calls.append((message, language_mode, require_language_mode))
            return {"languageCertification": language_mode}

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    monkeypatch.setattr(cli, "Session5ScenarioRunner", Runner)
    assert cli.main([
        "TURN", "--language-mode", mode, "current", "message",
    ]) == 0
    assert calls == [("current message", mode, True)]
    assert json.loads(capsys.readouterr().out)["languageCertification"] == mode


def test_explicit_real_language_evidence_must_show_live_provider():
    with pytest.raises(RuntimeError, match="REAL_AVA_LANGUAGE_NOT_HONORED"):
        cli.Session5ScenarioRunner._require_requested_language_mode({
            "syntheticProvider": {
                "syntheticProviderMode": DETERMINISTIC_CERTIFICATION,
                "liveProviderCalled": False,
            },
        }, REAL_AVA_LANGUAGE)


def test_real_language_evidence_preserves_test_transport_projection():
    evidence = {
        "scenarioId": "C10",
        "turnNumber": 1,
        "inboundText": "hello",
        "finalResponseText": "hey",
        "syntheticProvider": {
            "syntheticProviderMode": REAL_AVA_LANGUAGE,
            "liveProviderCalled": True,
        },
        "SalesBrainFullAnalysis": {},
    }
    cli.Session5ScenarioRunner._require_requested_language_mode(
        evidence, REAL_AVA_LANGUAGE,
    )
    projection = object.__new__(cli.Session5ScenarioRunner)._turn_projection(
        evidence, [],
    )
    assert projection["languageCertification"] == REAL_AVA_LANGUAGE
    assert projection["testTransport"] == "TEST_TRANSPORT_NO_WAIT"
    assert projection["telegramSent"] is False


def test_ui_api_marks_selected_language_mode_as_strict(monkeypatch):
    calls = []

    class Runner:
        def turn(self, message, *, language_mode, require_language_mode):
            calls.append((message, language_mode, require_language_mode))
            return {"ok": True}

    monkeypatch.setattr(scenario_api, "_scenario_action", lambda action: action(Runner()))
    request = scenario_api.ScenarioTurnRequest(
        customer_message="hello", language_mode=REAL_AVA_LANGUAGE,
    )
    assert scenario_api.scenario_turn(request) == {"ok": True}
    assert calls == [("hello", REAL_AVA_LANGUAGE, True)]


@pytest.mark.parametrize("mode", (
    REAL_AVA_LANGUAGE,
    DETERMINISTIC_CERTIFICATION,
))
def test_cli_emits_lossless_utf8_json_from_legacy_windows_stream(monkeypatch, mode):
    response = '😉 “that’s tempting” — okay – maybe ASCII'

    class Runner:
        def turn(self, message, *, language_mode, require_language_mode):
            return {
                "customer": message,
                "ava": response,
                "languageCertification": language_mode,
                "diagnostics": {"telegramSent": False, "price": "$29.00"},
            }

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    raw = io.BytesIO()
    legacy_stdout = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", legacy_stdout)
    monkeypatch.setattr(cli, "Session5ScenarioRunner", Runner)
    try:
        assert cli.main([
            "TURN", "--language-mode", mode, "unicode", "request",
        ]) == 0
        legacy_stdout.flush()
        emitted = raw.getvalue().decode("utf-8")
    finally:
        legacy_stdout.detach()

    parsed = json.loads(emitted)
    assert parsed["ava"] == response
    assert parsed["customer"] == "unicode request"
    assert parsed["languageCertification"] == mode
    assert parsed["diagnostics"] == {"telegramSent": False, "price": "$29.00"}
