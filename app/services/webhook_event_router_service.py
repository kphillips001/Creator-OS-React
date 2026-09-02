from app.services.realtime_buyer_update_service import (
    RealtimeBuyerUpdateService,
)

from app.services.realtime_message_event_service import (
    RealtimeMessageEventService,
)

from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


class WebhookEventRouterService:
    """
    STEP 11.8 + 11.9 + 3D.1–3D.3

    Central webhook routing layer.

    Determines which internal pipeline
    should handle each Fanvue event.

    Responsibilities:
    - route webhook event types
    - trigger realtime services
    - launch downstream processing pipelines

    Future:
    - realtime chat sync
    - buyer intelligence updates
    - spend tracking
    - subscription lifecycle handling
    - dashboard refresh events
    - monetization continuation logic
    """

    def __init__(self):
        self.realtime_buyer_service = (
            RealtimeBuyerUpdateService()
        )

        self.realtime_monetization_service = (
            RealtimeMonetizationEventService()
        )
        from app.services.commerce_signal_service import CommerceSignalService
        self.commerce_signal_service = CommerceSignalService()

    def route_event(self, event: dict):
        event_type = event["event_type"]

        print("\n[ROUTING EVENT]")
        print(f"event_type={event_type}")

        #
        # MESSAGE EVENTS
        #

        if event_type == "message_received":
            return self._route_message_received(event)

        #
        # MONETIZATION EVENTS
        #

        elif event_type in (
            "purchase_received",
            "purchase_created",
            "unlock_confirmation",
            "tip_received",
            "subscription_created",
            "subscription_cancelled",
        ):
            return self._route_monetization_event(
                event
            )

        elif event_type in ("purchase_new", "creator_payment_succeeded"):
            result = self.commerce_signal_service.process_webhook(event)
            return {
                "pipeline": "commerce_signal_pipeline",
                "result": result,
                "outcome": "SUCCEEDED" if result.get("success") else "RETRYABLE",
            }

        #
        # UNKNOWN
        #

        else:
            print("[UNHANDLED EVENT TYPE]")
            return {"pipeline": "ignored", "outcome": "IGNORED",
                    "reason": f"known_or_unsupported_event:{event_type}"}

    #
    # ROUTES
    #

    def _route_message_received(self, event: dict):
        print("[MESSAGE RECEIVED ROUTE]")

        service = RealtimeMessageEventService()

        result = service.process_message_received(
            event
        )

        return {
            "pipeline": "message_pipeline",
            "result": result,
            "outcome": "SUCCEEDED" if result.get("success") else "RETRYABLE",
        }

    def _route_monetization_event(
        self,
        event: dict,
    ):
        print("[MONETIZATION EVENT ROUTE]")

        result = (
            self.realtime_monetization_service
            .process_event(event)
        )

        print(
            f"monetization_event_result={result}"
        )

        return {
            "pipeline": (
                "monetization_event_pipeline"
            ),
            "result": result,
            "outcome": "SUCCEEDED" if result.get("success") else "RETRYABLE",
        }
