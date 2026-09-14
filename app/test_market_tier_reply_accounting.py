from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.market_tier_reply_accounting_service import (
    MarketTierReplyAccountingService,
)
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


class Counter:
    def __init__(self, value): self.value=value; self.calls=[]
    def count_between(self, **kwargs): self.calls.append(kwargs); return self.value


def test_counter_projects_authoritative_chicago_day():
    repo=Counter(5)
    service=MarketTierReplyAccountingService(repository=repo,
        now=lambda:datetime(2026,9,13,18,tzinfo=timezone.utc))
    result=service.today(creator_profile_id=1,fanvue_account_id=2,
        telegram_user_id=3,telegram_chat_id=4)
    assert result["replies_used_today"] == 5
    assert result["business_day_start"].isoformat() == "2026-09-13T05:00:00+00:00"
    assert result["business_day_end"] == result["next_reset_at"]


def test_chicago_dst_boundaries_are_timezone_aware():
    spring = MarketTierReplyAccountingService.business_day_bounds(
        datetime(2026,3,8,18,tzinfo=timezone.utc))
    fall = MarketTierReplyAccountingService.business_day_bounds(
        datetime(2026,11,1,18,tzinfo=timezone.utc))
    assert (spring[1]-spring[0]).total_seconds() == 23*3600
    assert (fall[1]-fall[0]).total_seconds() == 25*3600


def operation(diagnostics=None):
    return SimpleNamespace(response_payload={"diagnostic_metadata":diagnostics or {}})


def test_only_ordinary_noncommercial_is_classified_for_accounting():
    assert OrdinaryChatReplyService._resource_classification(operation()) == "ORDINARY_NONCOMMERCIAL"
    excluded = [
        {"commercial_tease_delivery_pending_confirmation":True},
        {"session_proposal_delivery_pending_confirmation":True},
        {"pending_sales_progression":{"step":"TEASE"}},
        {"pending_session_proposal":{"id":"x"}},
        {"current_turn_visual_context":{"response_policy":"FIRM_EXPLICIT_BOUNDARY"}},
    ]
    assert all(OrdinaryChatReplyService._resource_classification(operation(item))
               == "EXCLUDED_NONORDINARY" for item in excluded)
