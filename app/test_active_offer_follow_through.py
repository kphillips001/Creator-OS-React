from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.purchase_intent import PurchaseIntentStatus
from app.services.active_offer_follow_through_service import ActiveOfferFollowThroughService

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def intent(**changes):
    values = dict(status=PurchaseIntentStatus.PRESENTED,
        presented_at=NOW-timedelta(hours=25), expires_at=NOW+timedelta(days=1),
        purchased_at=None, provider_transaction_order_id=None,
        provider_payment_id=None, provider_event_id=None)
    values.update(changes)
    return SimpleNamespace(**values)


def test_timed_policy_is_identity_neutral_and_preserves_24h_cadence():
    result = ActiveOfferFollowThroughService().evaluate(
        intent=intent(), now=NOW, nudge_delay=timedelta(hours=24))
    assert result.eligible and result.mode == "TIMED"


def test_contextual_progression_precedes_timer():
    result = ActiveOfferFollowThroughService().evaluate(
        intent=intent(presented_at=NOW), now=NOW, nudge_delay=timedelta(hours=24),
        fresh_direct_intent=True)
    assert result.eligible and result.mode == "CONTEXTUAL"

def test_four_meaningful_turns_after_45_minutes_are_engagement_eligible():
    result = ActiveOfferFollowThroughService().evaluate(
        intent=intent(presented_at=NOW-timedelta(minutes=45)), now=NOW,
        nudge_delay=timedelta(hours=24), meaningful_turns_after_presentation=4)
    assert result.eligible and result.mode == "ENGAGEMENT"

def test_fewer_than_four_turns_are_not_engagement_eligible():
    result = ActiveOfferFollowThroughService().evaluate(
        intent=intent(presented_at=NOW-timedelta(hours=1)), now=NOW,
        nudge_delay=timedelta(hours=24), meaningful_turns_after_presentation=3)
    assert not result.eligible


def test_unpresented_settled_expired_and_rejected_are_ineligible():
    service = ActiveOfferFollowThroughService()
    cases = [intent(presented_at=None), intent(purchased_at=NOW),
             intent(expires_at=NOW), intent(status=PurchaseIntentStatus.ABANDONED)]
    assert all(not service.evaluate(intent=item, now=NOW,
        nudge_delay=timedelta(hours=24)).eligible for item in cases)
    assert not service.evaluate(intent=intent(), now=NOW,
        nudge_delay=timedelta(hours=24), rejected=True).eligible
