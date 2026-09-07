from contextlib import contextmanager
from types import SimpleNamespace

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    HistoricalPurchaseFixtureBuilder,
)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def execute(self, statement, _parameters):
        if "FROM telegram_sales_prospects" in statement:
            return _Result({
                "creator_profile_id": 41,
                "fanvue_account_id": 42,
                "telegram_chat_id": 9_100_000_009,
            })
        if "FROM customer_commerce_profiles" in statement:
            return _Result(None)
        if "provider_purchase_asset_ownership" in statement:
            return _Result({"n": 0})
        if "FROM purchase_intents" in statement:
            return _Result(None)
        if "FROM sales_sessions" in statement:
            return _Result(None)
        raise AssertionError(statement)


class _Scenarios:
    definition = staticmethod(CustomerScenarioHarness.definition)
    customer_for = staticmethod(CustomerScenarioHarness.customer_for)

    @contextmanager
    def connection(self):
        yield _Connection()

    @staticmethod
    def behavior_summary(_scenario_id):
        return {
            "inbound_message_count": 10,
            "post_offer_sexual_engagement_count": 1,
            "direct_buying_intent": True,
            "content_request": True,
        }


def test_c09_accumulated_state_reads_durable_opportunities_and_nurture_once(
    monkeypatch,
):
    ordinary_calls = []
    opportunity_calls = []

    class OrdinaryRepository:
        def __init__(self, **_kwargs):
            pass

        def customer_behavior_evidence(self, **values):
            ordinary_calls.append(values)
            return {
                "inbound_message_count": 10,
                "rejection_count": 2,
                "commercial_movement": True,
                "nurture_response_count_rolling_day": 1,
                "last_nurture_response_at": "2026-09-02T21:31:01+00:00",
            }

    class PurchaseIntentRepository:
        def __init__(self, **_kwargs):
            pass

        def get_customer_opportunity_evidence(self, **values):
            opportunity_calls.append(values)
            return {
                "commercial_opportunity_evidence_source": (
                    "PURCHASE_INTENT_PRESENTATION_LIFECYCLE"
                ),
                "presented_opportunity_count": 2,
                "failed_nonconverted_opportunity_count": 2,
                "converted_opportunity_count": 0,
                "active_unresolved_opportunity": False,
            }

    monkeypatch.setattr(
        "app.repositories.ordinary_chat_reply_repository.OrdinaryChatReplyRepository",
        OrdinaryRepository,
    )
    monkeypatch.setattr(
        "app.repositories.purchase_intent_repository.PurchaseIntentRepository",
        PurchaseIntentRepository,
    )
    builder = HistoricalPurchaseFixtureBuilder(_Scenarios())

    first = builder.derived_state("C09")
    second = builder.derived_state("C09")

    for state in (first, second):
        assert state["failedNonconvertedOpportunityCount"] == 2
        assert state["timeWasterRisk"] == "HIGH"
        assert state["attentionTier"] == "LOW"
        assert state["effortMode"] == "MINIMAL"
        assert state["lowCostNurtureActive"] is True
        assert state["nurtureResponsesUsed"] == 1
        assert state["optionalOrdinaryReplySuppressed"] is True
    assert len(ordinary_calls) == 2
    assert len(opportunity_calls) == 2


def test_explicit_projection_does_not_manufacture_durable_failures(monkeypatch):
    monkeypatch.setattr(
        "app.repositories.ordinary_chat_reply_repository.OrdinaryChatReplyRepository",
        SimpleNamespace,
    )
    builder = HistoricalPurchaseFixtureBuilder(_Scenarios())

    state = builder.derived_state("C09", behavior={
        "inbound_message_count": 10,
        "presented_opportunity_count": 1,
        "failed_nonconverted_opportunity_count": 1,
        "nurture_response_count_rolling_day": 0,
    })

    assert state["failedNonconvertedOpportunityCount"] == 1
    assert state["lowCostNurtureActive"] is False
    assert state["nurtureResponsesUsed"] == 0
