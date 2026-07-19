from uuid import uuid4

from app.repositories.webhook_event_repository import claim_due_items, renew_claim, complete_claim, fail_claim

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

    def __init__(self, worker_instance_id: str | None = None):
        self.router = WebhookEventRouterService()
        self.worker_instance_id = worker_instance_id or f"webhook-processor-{uuid4()}"

    def process_pending_events(self):
        events = claim_due_items(worker_instance_id=self.worker_instance_id)

        print("\n===================================")
        print(" PROCESSING WEBHOOK EVENTS ")
        print("===================================")

        print(f"pending_events={len(events)}")

        processing_results = []

        for event in events:
            result = self._process_single_event(event)
            processing_results.append(result)

        print("===================================\n")

        return processing_results

    def _process_single_event(self, event):
        webhook_event_id = event["id"]
        event_type = event["event_type"]

        print("\n[PROCESSING EVENT]")
        print(f"id={webhook_event_id}")
        print(f"event_type={event_type}")

        try:
            if not renew_claim(webhook_event_id, worker_instance_id=self.worker_instance_id):
                return {"success": False, "error": "claim_not_owned"}

            route_result = self.router.route_event(event)

            print(f"route_result={route_result}")

            complete_claim(webhook_event_id, worker_instance_id=self.worker_instance_id)

            print("[EVENT PROCESSED]")

            return route_result

        except Exception as e:
            print("\n[EVENT PROCESSING FAILED]")
            print(str(e))

            import traceback

            traceback_text = traceback.format_exc()
            print(traceback_text)

            fail_claim(
                webhook_event_id=webhook_event_id,
                worker_instance_id=self.worker_instance_id,
                error_message=str(e),
            )

            print("[EVENT MARKED FAILED]")

            return {
                "success": False,
                "error": str(e),
                "traceback": traceback_text,
            }
