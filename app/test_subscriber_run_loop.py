from app.services.subscriber_monetization_service import SubscriberMonetizationService

FANVUE_ACCOUNT_ID = 1


def run_test():
    service = SubscriberMonetizationService()

    print("\n===== TEST: SUBSCRIBER RUN LOOP =====\n")

    result = service.run(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        limit=10,
    )

    print("RESULT:")
    print(result)

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()