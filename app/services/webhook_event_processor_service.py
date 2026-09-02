import logging
from uuid import uuid4

from app.repositories.webhook_event_repository import (
    claim_due_items, renew_claim, complete_claim, fail_claim,
    ignore_claim, quarantine_claim,
)

from app.services.webhook_event_router_service import (
    WebhookEventRouterService,
)


class WebhookEventProcessorService:
    """
    STEP 11.7 + 11.8 + 11.15 + 11.16

    Background processor for persisted webhook events.

    Responsibilities:
    - fetch new/retryable webhook events
    - mark event as processing
    - route each event to the correct internal pipeline
    - mark successfully handled events as processed
    - mark failed events retryable
    """

    def __init__(self, worker_instance_id: str | None = None, router=None):
        self.router = router or WebhookEventRouterService()
        self.worker_instance_id = worker_instance_id or f"webhook-processor-{uuid4()}"
        self.logger = logging.getLogger("webhook-event-processor")

    def process_pending_events(self, *, limit: int = 25):
        events = claim_due_items(worker_instance_id=self.worker_instance_id, limit=limit)

        self.logger.info(
            "event=webhook_batch_claimed pending_count=%s", len(events)
        )

        processing_results = []

        for event in events:
            result = self._process_single_event(event)
            processing_results.append(result)

        return processing_results

    def _process_single_event(self, event):
        webhook_event_id = event["id"]
        event_type = event["event_type"]

        self.logger.info(
            "event=webhook_processing_started webhook_event_id=%s "
            "event_type=%s",
            webhook_event_id,
            event_type,
        )

        try:
            if not renew_claim(webhook_event_id, worker_instance_id=self.worker_instance_id):
                return {"success": False, "error": "claim_not_owned"}

            route_result = self.router.route_event(event)
            outcome = route_result.get("outcome", "SUCCEEDED") if isinstance(route_result, dict) else "TERMINAL_FAILED"
            if outcome == "IGNORED":
                ignore_claim(webhook_event_id, worker_instance_id=self.worker_instance_id,
                             reason=route_result.get("reason", "ignored"))
            elif outcome == "QUARANTINED":
                quarantine_claim(webhook_event_id, worker_instance_id=self.worker_instance_id,
                                 reason=route_result.get("reason", "quarantined"))
            elif outcome == "RETRYABLE":
                fail_claim(webhook_event_id=webhook_event_id,
                           worker_instance_id=self.worker_instance_id,
                           error_message=str(route_result.get("result") or "retryable"))
            elif outcome == "SUCCEEDED":
                complete_claim(webhook_event_id, worker_instance_id=self.worker_instance_id)
            else:
                quarantine_claim(webhook_event_id, worker_instance_id=self.worker_instance_id,
                                 reason=route_result.get("reason", "terminal_failed"))

            self.logger.info(
                "event=webhook_processing_completed webhook_event_id=%s "
                "event_type=%s",
                webhook_event_id,
                event_type,
            )

            return route_result

        except Exception as e:
            fail_claim(
                webhook_event_id=webhook_event_id,
                worker_instance_id=self.worker_instance_id,
                error_message=type(e).__name__,
            )
            self.logger.exception(
                "event=webhook_processing_failed webhook_event_id=%s "
                "event_type=%s error_type=%s",
                webhook_event_id,
                event_type,
                type(e).__name__,
            )

            return {
                "success": False,
                "error": type(e).__name__,
            }
