from app.repositories.webhook_event_repository import (
    get_unprocessed_webhook_events,
    mark_webhook_event_processing,
    mark_webhook_event_processed,
    mark_webhook_event_failed,
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

    def __init__(self):
        self.router = WebhookEventRouterService()

    def process_pending_events(self):
        events = get_unprocessed_webhook_events()

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
            mark_webhook_event_processing(webhook_event_id)

            route_result = self.router.route_event(event)

            print(f"route_result={route_result}")

            mark_webhook_event_processed(webhook_event_id)

            print("[EVENT PROCESSED]")

            return route_result

        except Exception as e:
            print("\n[EVENT PROCESSING FAILED]")
            print(str(e))

            import traceback

            traceback_text = traceback.format_exc()
            print(traceback_text)

            mark_webhook_event_failed(
                webhook_event_id=webhook_event_id,
                error_message=str(e),
            )

            print("[EVENT MARKED FAILED]")

            return {
                "success": False,
                "error": str(e),
                "traceback": traceback_text,
            }