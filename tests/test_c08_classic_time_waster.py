from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    EconomicState,
    confirm_scenario_test_transport_ordinary_reply,
    merge_scenario_customer_behavior_evidence,
)
from app.testing.session5_scenario_runner import Session5ScenarioRunner


def _turn(*, intent=None, value=None, boundary=False, reactivation=False,
          decision=None, ava="plain conversation", provider_draft=None,
          rewrite_history=None):
    analysis = {
        "attentionEconomics": dict(value or {}),
        "nurture": {"supporterAttentionBoundaryDelivered": boundary},
        "commercialReactivation": {
            "commercialInterestType": "COMMERCIAL_CURIOSITY" if reactivation else "NONE",
            "nurtureBypassedForCommercialInterest": reactivation,
        },
        "finalSalesDecision": {"decision": decision} if decision else {},
    }
    return {
        "ava": ava,
        "customerValueAttention": dict(value or {}),
        "salesBrainFullAnalysis": analysis,
        "providerDraft": provider_draft,
        "rewriteHistory": list(rewrite_history or ()),
        "syntheticPpvPresentation": ({
            "purchaseIntent": {"id": intent, "state": "PRESENTED"}
        } if intent else None),
    }


def test_c08_definition_is_bounded_adaptive_nonsexual_nonbuyer():
    item = CustomerScenarioHarness.definition("C08")
    assert item.economic_state is EconomicState.FRESH_PROSPECT
    assert item.maximum_turn_count == 18
    assert item.canonical_turn_count == 3
    assert "LOW_COST_NURTURE_ACTIVE" in item.certification_objectives
    assert "SAME_WINDOW_REPLY_SUPPRESSED" in item.branch_checkpoints
    assert "COMMERCIAL_REACTIVATION" in item.branch_checkpoints
    assert all("sexual" not in value.lower() for value in item.canonical_customer_turns)


def test_c08_evidence_merge_preserves_durable_rejection_and_browsing_counts():
    result = merge_scenario_customer_behavior_evidence(
        {
            "rejection_count": 0,
            "idle_browsing_signal_count": 0,
            "compatibilityOnly": "kept",
        },
        {
            "source": "ORDINARY_CHAT_REPLY_OPERATIONS",
            "rejection_count": 4,
            "idle_browsing_signal_count": 4,
        },
    )
    assert result == {
        "source": "ORDINARY_CHAT_REPLY_OPERATIONS",
        "rejection_count": 4,
        "idle_browsing_signal_count": 4,
        "compatibilityOnly": "kept",
        "behaviorEvidenceLoaded": True,
    }


def test_test_transport_confirms_customer_visible_ordinary_reply_once():
    generated = SimpleNamespace(
        operation_id=UUID("40000000-0000-0000-0000-000000000001"),
        state=SimpleNamespace(value="GENERATED"),
        outbound_telegram_message_id=None,
    )
    sending = SimpleNamespace(**{**generated.__dict__,
        "state": SimpleNamespace(value="SENDING")})
    confirmed = SimpleNamespace(**{**generated.__dict__,
        "state": SimpleNamespace(value="SENT_CONFIRMED"),
        "outbound_telegram_message_id": 12345})
    calls = []

    class Service:
        def claim_send(self, operation):
            calls.append(("claim", operation.operation_id))
            return sending

        def confirmed(self, operation, provider_message_id):
            calls.append(("confirm", operation.operation_id, provider_message_id))
            return confirmed

    output = SimpleNamespace(
        response_text="Just relaxing tonight.", blocked=False,
        diagnostic_metadata={},
    )
    result = confirm_scenario_test_transport_ordinary_reply(
        service=Service(), operation=generated, output=output,
        purchase_intent=None, correlation_id="scenario:C08:attempt:5:turn:10",
    )
    assert result is confirmed
    assert [item[0] for item in calls] == ["claim", "confirm"]
    assert output.diagnostic_metadata["synthetic_ordinary_reply_state"] == "SENT_CONFIRMED"
    assert output.diagnostic_metadata["test_transport_customer_visible_confirmed"] is True


def test_test_transport_does_not_fake_confirmation_for_suppressed_turn():
    suppressed = SimpleNamespace(
        operation_id=UUID("40000000-0000-0000-0000-000000000002"),
        state=SimpleNamespace(value="SUPPRESSED"),
    )

    class Service:
        def claim_send(self, _operation):
            raise AssertionError("suppressed turn must not claim a send")

        def confirmed(self, _operation, _provider_message_id):
            raise AssertionError("suppressed turn must not be confirmed")

    output = SimpleNamespace(
        response_text="", blocked=True, diagnostic_metadata={},
    )
    result = confirm_scenario_test_transport_ordinary_reply(
        service=Service(), operation=suppressed, output=output,
        purchase_intent=None, correlation_id="scenario:C08:attempt:5:turn:11",
    )
    assert result is suppressed
    assert output.diagnostic_metadata == {
        "synthetic_ordinary_reply_operation_id": str(suppressed.operation_id),
        "synthetic_ordinary_reply_state": "SUPPRESSED",
        "test_transport_customer_visible_confirmed": False,
    }


def test_c08_completion_requires_two_terminal_presented_intents_and_boundaries():
    first = {"failedNonconvertedOpportunityCount": 1,
             "lowCostNurtureActive": False, "timeWasterRisk": "LOW"}
    nurture = {
        "failedNonconvertedOpportunityCount": 2, "lowCostNurtureActive": True,
        "timeWasterRisk": "HIGH", "attentionTier": "LOW", "effortMode": "MINIMAL",
        "nurtureResponseBudget": 1, "nurtureResponsesUsed": 1,
    }
    suppressed = {**nurture, "optionalOrdinaryReplySuppressed": True,
                  "suppressionReason": "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"}
    turns = [
        _turn(intent="one", value=first),
        _turn(intent="two", value=nurture, boundary=True),
        _turn(value=suppressed, ava=""),
        _turn(value=nurture, reactivation=True, decision="CONTINUE_CONVERSATION"),
    ]
    state = {
        "startingPurchaseCount": 0, "failedNonconvertedOpportunityCount": 2,
        "purchaseCount": 0, "ownershipCount": 0, "buyerStatus": "NONBUYER",
        "purchaseIntents": [
            {"id": "one", "state": "EXPIRED"},
            {"id": "two", "state": "ABANDONED"},
        ],
    }
    result = Session5ScenarioRunner.c08_completion_evidence(turns, state)
    assert result["complete"] is True
    assert all(result["checks"].values())


def test_c08_completion_rejects_first_failure_nurture_buyer_abuse_price_and_repeat_boundary():
    value = {
        "failedNonconvertedOpportunityCount": 2, "lowCostNurtureActive": True,
        "timeWasterRisk": "HIGH", "attentionTier": "LOW", "effortMode": "MINIMAL",
        "nurtureResponseBudget": 1, "nurtureResponsesUsed": 1,
        "optionalOrdinaryReplySuppressed": True,
        "suppressionReason": "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED",
    }
    turns = [
        _turn(intent="one", value=value, boundary=True, ava="only $9.99"),
        _turn(intent="two", value=value, boundary=True, ava=""),
        _turn(value=value, reactivation=True, decision="NO_SALE"),
    ]
    state = {
        "startingPurchaseCount": 1, "failedNonconvertedOpportunityCount": 2,
        "purchaseCount": 1, "ownershipCount": 1, "buyerStatus": "VERIFIED_BUYER",
        "qualifyingAbuse": True,
        "purchaseIntents": [{"id": "one", "state": "EXPIRED"},
                            {"id": "two", "state": "EXPIRED"}],
    }
    checks = Session5ScenarioRunner.c08_completion_evidence(turns, state)["checks"]
    assert checks["firstFailureDidNotPrematurelyNurture"] is False
    assert checks["supporterBoundaryConfirmedAtMostOnce"] is False
    assert checks["nonbuyerOnly"] is False
    assert checks["noAbuse"] is False
    assert checks["noNumericPriceInAvaProse"] is False


def test_c08_orchestration_routes_two_failures_nurture_suppression_and_reactivation():
    fixed = ("hello",)
    action = Session5ScenarioRunner.c08_next_action([], {}, fixed_messages=fixed)
    assert action == {"kind": "FIXED", "message": "hello"}
    turns = [_turn(intent="one")]
    assert Session5ScenarioRunner.c08_next_action(
        turns, {"failedNonconvertedOpportunityCount": 0,
                "purchaseIntents": [{"id": "one", "state": "PRESENTED"}]},
        fixed_messages=fixed
    ) == {"kind": "TERMINALIZE_LATEST", "state": "ADMIN_CLOSED",
          "purchaseIntentId": "one"}
    turns.append(_turn(value={"failedNonconvertedOpportunityCount": 1}))
    assert "other private sets" in Session5ScenarioRunner.c08_next_action(
        turns, {"failedNonconvertedOpportunityCount": 1,
                "purchaseIntents": [{"id": "one", "state": "ADMIN_CLOSED"}]},
        fixed_messages=fixed
    )["message"]
    turns.append(_turn(intent="two", value={"failedNonconvertedOpportunityCount": 1}))
    assert Session5ScenarioRunner.c08_next_action(turns, {
        "failedNonconvertedOpportunityCount": 1,
        "purchaseIntents": [{"id": "one", "state": "ADMIN_CLOSED"},
                            {"id": "two", "state": "PRESENTED"}],
    }, fixed_messages=fixed)["purchaseIntentId"] == "two"
    turns.append(_turn(value={"failedNonconvertedOpportunityCount": 2,
                              "lowCostNurtureActive": True,
                              "nurtureResponsesUsed": 0}))
    assert "what are you up to" in Session5ScenarioRunner.c08_next_action(
        turns, {}, fixed_messages=fixed
    )["message"]
    turns.append(_turn(value={"failedNonconvertedOpportunityCount": 2,
                              "lowCostNurtureActive": True,
                              "nurtureResponsesUsed": 1}))
    assert "interesting" in Session5ScenarioRunner.c08_next_action(
        turns, {}, fixed_messages=fixed
    )["message"]
    turns.append(_turn(value={"failedNonconvertedOpportunityCount": 2,
                              "lowCostNurtureActive": True,
                              "nurtureResponsesUsed": 1,
                              "optionalOrdinaryReplySuppressed": True}))
    assert "private content" in Session5ScenarioRunner.c08_next_action(
        turns, {}, fixed_messages=fixed
    )["message"]


def test_c08_runtime_state_overlays_canonical_opportunity_evidence(monkeypatch):
    intent = UUID("30000000-0000-0000-0000-000000000001")
    rows = [{"purchase_intent_id": intent, "status": "ADMIN_CLOSED",
             "creator_profile_id": 12, "fanvue_account_id": 34}]

    class Builder:
        def derived_state(self, _scenario):
            return {"failedNonconvertedOpportunityCount": 0}

    class Harness(_Harness):
        def definition(self, _scenario): return SimpleNamespace()
        def customer_for(self, _definition):
            return SimpleNamespace(telegram_user_id=9_100_000_008)

    class Repository:
        def __init__(self, **_kwargs): pass
        def get_customer_opportunity_evidence(self, **scope):
            assert scope == {"creator_profile_id": 12, "fanvue_account_id": 34,
                             "telegram_user_id": 9_100_000_008}
            return {
                "commercial_opportunity_evidence_source":
                    "PURCHASE_INTENT_PRESENTATION_LIFECYCLE",
                "presented_opportunity_count": 1,
                "failed_nonconverted_opportunity_count": 1,
                "converted_opportunity_count": 0,
                "active_unresolved_opportunity": False,
            }

    monkeypatch.setattr(
        "app.repositories.purchase_intent_repository.PurchaseIntentRepository",
        Repository,
    )
    runner = object.__new__(Session5ScenarioRunner)
    runner.builder = Builder()
    runner.harness = Harness(rows)
    state = runner._c08_runtime_state([_turn(value={
        "failedNonconvertedOpportunityCount": 0,
    })])
    assert state["presentedOpportunityCount"] == 1
    assert state["failedNonconvertedOpportunityCount"] == 1
    assert state["commercialOpportunityEvidenceSource"] == (
        "PURCHASE_INTENT_PRESENTATION_LIFECYCLE"
    )


def test_c08_non_progress_guard_is_bounded():
    runner = object.__new__(Session5ScenarioRunner)
    runner.harness = SimpleNamespace(definition=lambda _scenario: SimpleNamespace(
        maximum_turn_count=18, canonical_customer_turns=("hello",),
    ))
    runner.recovery = SimpleNamespace(scenario_attempt=lambda _scenario: 3)
    runner._current_attempt_turn_projections = lambda *_args: [_turn(intent="one")]
    runner._c08_runtime_state = lambda _turns: {
        "purchaseIntents": [{"id": "one", "state": "PRESENTED"}],
    }
    runner.c08_completion_evidence = lambda *_args: {"complete": False}
    calls = []
    runner._c08_expire_latest_presented = lambda intent_id: calls.append(intent_id)
    with pytest.raises(RuntimeError, match="C08_NON_PROGRESSING_ORCHESTRATION"):
        runner._execute_c08_primary_owned(language_mode="REAL_AVA_LANGUAGE")
    assert calls == ["one"]


def test_attempt_owner_marks_non_progress_failure_and_releases_lease():
    releases = []

    class Recovery:
        def scenario_attempt(self, _scenario): return 3
        def next_logical_turn(self, _scenario, _attempt): return 6
        def claim_execution(self, *_args, **_kwargs): return "owner"
        def release_execution(self, *args, **kwargs):
            releases.append((args, kwargs))

    runner = object.__new__(Session5ScenarioRunner)
    runner.recovery = Recovery()
    with pytest.raises(RuntimeError, match="C08_NON_PROGRESSING_ORCHESTRATION"):
        runner._execute_with_attempt_owner(
            "C08", 18,
            lambda: (_ for _ in ()).throw(RuntimeError(
                "C08_NON_PROGRESSING_ORCHESTRATION"
            )),
        )
    assert releases == [(('C08', 3, 'owner'), {
        'failed': True,
        'reason': 'RuntimeError: C08_NON_PROGRESSING_ORCHESTRATION',
    })]


def test_c09_definition_remains_separate_and_sexual():
    item = CustomerScenarioHarness.definition("C09")
    assert item.name == "HORNY_TIME_WASTER"
    assert any("sexual" in value.lower() for value in item.certification_objectives)


class _Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def execute(self, _statement, parameters):
        if len(parameters) == 1:
            return SimpleNamespace(fetchall=lambda: self.rows)
        requested = parameters[1]
        eligible = [row for row in self.rows if requested is None or str(
            row["purchase_intent_id"]
        ) == str(requested)]
        return SimpleNamespace(fetchone=lambda: eligible[0] if eligible else None)


class _Harness:
    def __init__(self, rows):
        self.rows = rows

    @contextmanager
    def connection(self):
        yield _Rows(self.rows)


def _terminalization_runner(rows):
    runner = object.__new__(Session5ScenarioRunner)
    runner.harness = _Harness(rows)
    runner._active = lambda **_kwargs: {
        "scenario_id": "C08", "telegram_user_id": 9_100_000_008,
    }
    return runner


def test_c08_terminalization_uses_atomic_canonical_close_and_is_idempotent(monkeypatch):
    target = UUID("10000000-0000-0000-0000-000000000001")
    rows = [{"purchase_intent_id": target, "telegram_user_id": 9_100_000_008,
             "telegram_chat_id": 9_100_000_008}]
    calls = []

    class IntentRepository:
        def __init__(self, **_kwargs): pass
        def close_administratively(self, intent_id, **values):
            calls.append((intent_id, values))
            return SimpleNamespace(purchase_intent_id=intent_id,
                                   status=SimpleNamespace(value="ADMIN_CLOSED"))

    class UnlockRepository:
        def __init__(self, **_kwargs): pass
        def get_grant_for_intent(self, intent_id):
            return SimpleNamespace(purchase_intent_id=intent_id,
                                   state="REVOKED", use_count=0)

    monkeypatch.setattr(
        "app.repositories.purchase_intent_repository.PurchaseIntentRepository",
        IntentRepository,
    )
    monkeypatch.setattr(
        "app.repositories.private_chat_fingerprint_repository.PrivateChatFingerprintRepository",
        UnlockRepository,
    )
    runner = _terminalization_runner(rows)
    first = runner._c08_expire_latest_presented(target)
    second = runner._c08_expire_latest_presented(target)
    assert first == second == {
        "purchaseIntentId": str(target), "terminalState": "ADMIN_CLOSED",
        "unlockState": "REVOKED",
    }
    assert [item[0] for item in calls] == [target, target]
    assert {item[1]["reason_code"] for item in calls} == {
        "SCENARIO_LAB_C08_CANONICAL_NONCONVERSION"
    }


def test_c08_terminalization_targets_only_requested_intent(monkeypatch):
    first = UUID("20000000-0000-0000-0000-000000000001")
    second = UUID("20000000-0000-0000-0000-000000000002")
    rows = [
        {"purchase_intent_id": first, "telegram_user_id": 9_100_000_008,
         "telegram_chat_id": 9_100_000_008},
        {"purchase_intent_id": second, "telegram_user_id": 9_100_000_008,
         "telegram_chat_id": 9_100_000_008},
    ]
    closed = []

    class IntentRepository:
        def __init__(self, **_kwargs): pass
        def close_administratively(self, intent_id, **_values):
            closed.append(intent_id)
            return SimpleNamespace(status=SimpleNamespace(value="ADMIN_CLOSED"))

    class UnlockRepository:
        def __init__(self, **_kwargs): pass
        def get_grant_for_intent(self, intent_id):
            return SimpleNamespace(state="REVOKED", use_count=0)

    monkeypatch.setattr(
        "app.repositories.purchase_intent_repository.PurchaseIntentRepository",
        IntentRepository,
    )
    monkeypatch.setattr(
        "app.repositories.private_chat_fingerprint_repository.PrivateChatFingerprintRepository",
        UnlockRepository,
    )
    result = _terminalization_runner(rows)._c08_expire_latest_presented(first)
    assert result["purchaseIntentId"] == str(first)
    assert closed == [first]
    assert second not in closed


def test_c08_terminalization_has_no_nonexistent_expiry_column_reference():
    import inspect
    source = inspect.getsource(Session5ScenarioRunner._c08_expire_latest_presented)
    assert "expires_at" not in source
    assert "close_administratively" in source
