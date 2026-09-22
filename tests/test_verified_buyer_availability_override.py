from datetime import datetime, timezone

import pytest

from app.models.ava_availability_session import AvaAvailabilityState
from app.repositories.ordinary_chat_reply_repository import (
    OrdinaryChatReplyRepository,
)
from app.services.ava_human_availability_service import AvaHumanAvailabilityService


NOW = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)


def availability(state):
    return AvaHumanAvailabilityService(
        now=lambda: NOW,
        uniform=lambda low, high: high,
        state_selector=lambda _at: state,
    )


def test_verified_buyer_away_uses_available_now_with_durable_evidence():
    decision = availability(AvaAvailabilityState.AWAY).calculate(
        inbound_text="hello", verified_buyer=True,
    )

    assert decision.state is AvaAvailabilityState.AWAY
    assert decision.available_at == NOW
    assert decision.delay_seconds == 0
    assert decision.quiet_period_seconds >= 8
    diagnostics = decision.diagnostics()
    assert diagnostics["buyerStatus"] == "VERIFIED_BUYER"
    assert diagnostics["availabilityTreatment"] == "BUYER_OVERRIDE"
    assert diagnostics["awayDeferralApplied"] is False
    assert diagnostics["messagePriorityAffectsAvailability"] is True
    assert diagnostics["effectiveProspectInvestment"] == "BUYER_AUTHORITY"
    assert diagnostics["typingSeparate"] is True


def test_verified_buyer_available_retains_normal_available_pacing():
    decision = availability(AvaAvailabilityState.AVAILABLE).calculate(
        verified_buyer=True,
    )

    assert decision.delay_seconds == 90
    assert decision.diagnostics()["availabilityTreatment"] == "STANDARD"
    assert decision.diagnostics()["typingSeparate"] is True


@pytest.mark.parametrize("state", [
    AvaAvailabilityState.AWAY,
    AvaAvailabilityState.AVAILABLE,
])
def test_nonbuyer_availability_behavior_is_unchanged(state):
    decision = availability(state).calculate(verified_buyer=False)

    assert decision.diagnostics()["buyerStatus"] == "NONBUYER"
    assert decision.diagnostics()["availabilityTreatment"] == "STANDARD"
    if state is AvaAvailabilityState.AWAY:
        assert decision.delay_seconds == 7200
        assert decision.diagnostics()["awayDeferralApplied"] is True
    else:
        assert decision.delay_seconds == 90


def test_verified_buyer_does_not_bypass_independent_sleep_control():
    decision = availability(AvaAvailabilityState.SLEEPING).calculate(
        verified_buyer=True,
    )

    assert decision.delay_seconds > 0
    assert decision.diagnostics()["availabilityTreatment"] == "STANDARD"
    assert decision.diagnostics()["awayDeferralApplied"] is False


def test_verified_buyer_does_not_bypass_busy_availability():
    decision = availability(AvaAvailabilityState.BUSY).calculate(
        verified_buyer=True,
    )

    assert decision.delay_seconds == 2100
    assert decision.diagnostics()["availabilityTreatment"] == "STANDARD"


def test_multiple_purchase_value_does_not_create_a_separate_speed_tier():
    first_purchase = availability(AvaAvailabilityState.AWAY).calculate(
        verified_buyer=True,
    )
    repeat_purchase = availability(AvaAvailabilityState.AWAY).calculate(
        verified_buyer=True,
    )

    assert first_purchase.available_at == repeat_purchase.available_at == NOW
    assert first_purchase.diagnostics()["availabilityTreatment"] == "BUYER_OVERRIDE"
    assert repeat_purchase.diagnostics()["availabilityTreatment"] == "BUYER_OVERRIDE"


class BuyerCursor:
    def __init__(self):
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return {"purchase_count": 0, "lifetime_gross_minor": 0}


class BuyerConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_value


def test_unscoped_buyer_lookup_types_nullable_postgres_parameters():
    cursor = BuyerCursor()
    repository = OrdinaryChatReplyRepository(
        connection_factory=lambda: BuyerConnection(cursor),
    )

    result = repository.buyer_attention_context(telegram_user_id=7489120428)

    assert result == {
        "verified_buyer": False,
        "repeat_buyer": False,
        "high_value_buyer": False,
    }
    assert cursor.params == (7489120428, None, None, None, None)
    assert "%s::BIGINT IS NULL OR profile.creator_profile_id=%s" in cursor.sql
    assert "%s::BIGINT IS NULL OR profile.fanvue_account_id=%s" in cursor.sql
