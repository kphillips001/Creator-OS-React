from app.services.webhook_event_processor_service import (
    WebhookEventProcessorService
)


def run_test():
    print("\n===================================")
    print(" TESTING 11.7 WEBHOOK PROCESSOR ")
    print("===================================\n")

    processor = WebhookEventProcessorService()
    processor.process_pending_events()

    print("\n✅ 11.7 PROCESSOR TEST COMPLETE\n")


if __name__ == "__main__":
    run_test()