from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-6 TEST — DB MESSAGE SYNC")
    print("======================================\n")

    service = FanvueMessageSyncService()

    FANVUE_ACCOUNT_ID = 1

    TEST_USER_UUID = "705b406b-edf0-43ce-93ca-b6e7e9aa3750"

    MY_USER_UUID = "f45fdd96-8831-4ef5-8f79-0278c29dc747"

    result = service.sync_messages_to_db(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_uuid=TEST_USER_UUID,
        my_user_uuid=MY_USER_UUID,
        page=1,
        size=20,
    )

    print("\n------------- RESULT -------------")
    print(result)

    print("\n======================================")
    print("13A-6 DB MESSAGE SYNC TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()