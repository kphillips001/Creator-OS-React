from datetime import datetime, timedelta, timezone

import pytest

from app.services.ordinary_reply_retry_policy import OrdinaryReplyRetryPolicy as Policy

NOW=datetime(2026,9,18,18,0,tzinfo=timezone.utc)


@pytest.mark.parametrize("reason,category",[
    ("availability_deferred","AVAILABILITY"),
    ("quality_corrective_retry_scheduled","QUALITY_CORRECTIVE"),
    ("global_delivery_readiness_deferred","GLOBAL_READINESS"),
    ("DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.",
     "DECISION_ENGINE_EXCEPTION"),
    ("EMPTY_GENERATION: Automatic reply could not be completed.","EMPTY_GENERATION"),
    ("GENERATION_FAILURE:RuntimeError: unavailable","GENERATION_FAILURE"),
])
def test_canonical_retry_taxonomy(reason,category):
    assert Policy.category(reason)==category


def decision(**changes):
    values=dict(state="RETRYABLE",reason="DECISION_ENGINE_EXCEPTION: failure",
      next_retry_at=NOW,generation_attempts=1,max_generation_attempts=5,
      send_attempts=0,has_response_payload=False,
      outbound_telegram_message_id=None,sent_confirmed_at=None,has_active_claim=False)
    values.update(changes);return Policy.evaluate(**values)


def test_due_safe_engine_failure_is_scheduler_eligible():
    value=decision();assert value.scheduler_eligible and value.due(NOW)


@pytest.mark.parametrize("change",[
    {"send_attempts":1},{"has_response_payload":True},
    {"outbound_telegram_message_id":7},{"sent_confirmed_at":NOW},
    {"has_active_claim":True},{"generation_attempts":5},
    {"state":"SEND_UNCERTAIN"},{"reason":"arbitrary"},
])
def test_unsafe_or_exhausted_shapes_fail_closed(change):
    assert not decision(**change).scheduler_eligible


def test_future_retry_waits_until_due():
    value=decision(next_retry_at=NOW+timedelta(seconds=30))
    assert value.scheduler_eligible and not value.due(NOW)
