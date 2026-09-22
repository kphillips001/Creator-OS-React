from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.sexual_sales_opportunity_service import SexualSalesOpportunityService


NOW = datetime(2026, 9, 17, 18, tzinfo=timezone.utc)


def intent(status, hours_ago, *, message_id=1):
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
        presented_at=NOW - timedelta(hours=hours_ago),
        telegram_message_id=message_id,
    )


class Intents:
    def __init__(self, rows=()): self.rows = rows
    def list_confirmed_presentations_for_buyer(self, **_): return self.rows


def project(rows=(), message="I want you naked", now=NOW, **kwargs):
    service = SexualSalesOpportunityService(
        intents=Intents(rows), cooldown=timedelta(hours=72),
        max_opportunities=3, episode_separation=timedelta(hours=6),
    )
    return service.project(
        creator_profile_id=1, fanvue_account_id=2, telegram_user_id=3,
        latest_message=message, now=now, **kwargs,
    )


def test_compliment_is_not_escalation():
    value = project(message="you look so sexy")
    assert value["sexualSignalClass"] == "SEXUAL_ATTRACTIVE_COMPLIMENT"
    assert value["sexualSalesOpportunityEligible"] is False


def test_zero_prior_new_escalation_is_opportunity_one():
    value = project()
    assert value["sexualSalesOpportunityEligible"] is True
    assert value["sexualSalesOpportunityNumber"] == 1


def test_joseph_current_turn_is_material_sexual_escalation():
    value = project(message=(
        "If you lay down on your bed with your sexy legs hanging off then I will "
        "kiss and lick your inner thighs up to your sweet puss"
    ))
    assert value["sexualSignalClass"] == "SEXUAL_ESCALATION"


@pytest.mark.parametrize("count,number", [(1, 2), (2, 3)])
def test_later_missed_presentations_advance_distinct_opportunities(count, number):
    rows = [intent("EXPIRED", 24 * (index + 1), message_id=index)
            for index in range(count)]
    value = project(rows)
    assert value["sexualSalesOpportunityEligible"] is True
    assert value["sexualSalesOpportunityNumber"] == number


def test_same_burst_is_not_second_opportunity():
    value = project([intent("EXPIRED", 2)])
    assert value["sexualSalesOpportunityEligible"] is False
    assert value["sexualSalesSuppressionReason"] == "SAME_SEXUAL_SALES_EPISODE"


def test_topic_reset_can_establish_new_episode():
    value = project([intent("EXPIRED", 2)], ordinary_topic_after_last_offer=True)
    assert value["sexualSalesOpportunityEligible"] is True


def test_active_presentation_prevents_duplicate_intent():
    value = project([intent("PRESENTED", 24)])
    assert value["sexualSalesOpportunityEligible"] is False
    assert value["activeUnresolvedPresentation"] is True


def test_three_misses_enter_72_hour_cooldown():
    rows = [intent("EXPIRED", value) for value in (4, 30, 60)]
    value = project(rows)
    assert value["sexualSalesOpportunitiesUsed"] == 3
    assert value["sexualSalesCooldownActive"] is True
    assert value["sexualSalesEligibilityReason"] == "SEXUAL_SALES_COOLDOWN_ACTIVE"


def test_cooldown_does_not_block_ordinary_conversation():
    rows = [intent("EXPIRED", value) for value in (4, 30, 60)]
    value = project(rows, message="how was your day?")
    assert value["sexualSignalClass"] == "NONE"
    assert value["sexualSalesOpportunityEligible"] is False


def test_cooldown_expiry_grants_one_renewed_opportunity_without_reset():
    rows = [intent("EXPIRED", value) for value in (80, 110, 140)]
    value = project(rows)
    assert value["sexualSalesOpportunitiesUsed"] == 3
    assert value["postCooldownRenewal"] is True
    assert value["sexualSalesOpportunityEligible"] is True
    assert value["sexualSalesOpportunityNumber"] == 3


def test_renewed_miss_reenters_cooldown():
    rows = [intent("EXPIRED", value) for value in (2, 80, 110, 140)]
    value = project(rows)
    assert value["sexualSalesCooldownActive"] is True
    assert value["unsuccessfulPresentationCount"] == 4


def test_current_commercial_signal_is_independent_override():
    rows = [intent("EXPIRED", value) for value in (2, 30, 60)]
    value = project(rows, message="how much is your content?", commercial_signal=True)
    assert value["sexualSignalClass"] == "CURRENT_COMMERCIAL_INTEREST"
    assert value["commercialSignalOverride"] is True


def test_purchase_exits_nonbuyer_opportunity_logic():
    value = project([intent("PURCHASED", 24)])
    assert value["sexualSalesOpportunityEligible"] is False
    assert value["sexualSalesEligibilityReason"] == "BUYER_LIFECYCLE_AUTHORITATIVE"


def test_created_only_or_deleted_boundary_is_not_a_presentation():
    value = project([])
    assert value["confirmedPresentationCount"] == 0
    assert value["sexualSalesOpportunityNumber"] == 1


def test_diagnostics_are_complete():
    value = project()
    assert {
        "sexualSignalClass", "sexualSalesEpisodeId",
        "sexualSalesOpportunityEligible", "sexualSalesOpportunitiesUsed",
        "sexualSalesOpportunityNumber", "sexualSalesCooldownActive",
        "sexualSalesCooldownUntil", "sexualSalesEligibilityReason",
        "sexualSalesSuppressionReason", "commercialSignalOverride",
    } <= value.keys()
