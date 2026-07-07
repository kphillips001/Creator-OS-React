import json
import time
import hmac
import hashlib
import requests

from app.config import FANVUE_WEBHOOK_SIGNING_SECRET


WEBHOOK_URL = "http://127.0.0.1:8000/webhooks/fanvue"

WEBHOOK_SECRET = FANVUE_WEBHOOK_SIGNING_SECRET


payload = {
    "event_type": "message_received",
    "event_id": "test_event_033",
    "fanvue_user_id": "229f1ce4-a843-4192-bdfd-14aa67f8bd2e",
    "fanvue_account_id": 1,
    "created_at": "2026-05-08T19:00:00Z",
    "data": {
        "message": {
            "text": "hey babe 😘"
        },
        "thread_id": "11111111-1111-1111-1111-111111111777",
    }
}


def generate_signature(raw_body: str):
    """
    STEP 11.5
    Simulate Fanvue webhook signing process.
    """

    timestamp = str(int(time.time()))

    signed_payload = f"{timestamp}.{raw_body}"

    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"t={timestamp},v0={signature}"


def run_test():
    print("\n===================================")
    print(" TESTING 11.5 SIGNATURE VERIFICATION ")
    print("===================================\n")

    raw_body = json.dumps(payload)

    signature = generate_signature(raw_body)

    response = requests.post(
        WEBHOOK_URL,
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Fanvue-Signature": signature,
        }
    )

    print(f"STATUS CODE: {response.status_code}")

    print("\nRESPONSE JSON:")
    print(response.json())

    if response.status_code == 200:
        print("\n✅ 11.5 SIGNATURE TEST PASSED")
    else:
        print("\n❌ 11.5 SIGNATURE TEST FAILED")

    print("\n===================================\n")


if __name__ == "__main__":
    run_test()