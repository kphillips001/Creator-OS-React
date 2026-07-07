import os
import requests
from dotenv import load_dotenv

from app.services.fanvue_oauth_service import FanvueOAuthService

load_dotenv()


FANVUE_API_BASE_URL = os.getenv("FANVUE_API_BASE_URL", "https://api.fanvue.com")


def fanvue_get(endpoint: str):
    oauth = FanvueOAuthService()
    access_token = oauth.get_valid_access_token()

    url = f"{FANVUE_API_BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "X-Fanvue-API-Version": "2025-06-26",
    }

    print(f"\n[CALLING] {url}")

    response = requests.get(url, headers=headers, timeout=30)

    print(f"[STATUS] {response.status_code}")

    if response.status_code >= 400:
        print("[ERROR RESPONSE]")
        print(response.text[:1000])
        return None

    return response.json()

def print_user_uuids(label: str, data):
    print(f"\n========== {label.upper()} ==========")

    if not data or "data" not in data:
        print("No users found.")
        return

    users = data["data"]

    print(f"\nTotal Users Returned: {len(users)}\n")

    for user in users:
        uuid = user.get("uuid")
        username = user.get("handle") or user.get("displayName")

        print(f"UUID: {uuid} | Username: {username}")

def run_test():
    print("\n=== 14N-1: OFFICIAL FANVUE FOLLOWERS API TEST ===")

    followers = fanvue_get("/followers")

    print("\n========== FOLLOWERS ==========")
    print_user_uuids("followers", followers)

    print("\n=== TEST COMPLETE — NO DB WRITES PERFORMED ===\n")

if __name__ == "__main__":
    run_test()