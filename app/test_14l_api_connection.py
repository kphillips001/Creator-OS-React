import requests
from app.services.fanvue_oauth_service import FanvueOAuthService


def run_test():
    print("\n=== 14L API CONNECTION TEST ===\n")

    service = FanvueOAuthService()
    access_token = service.get_valid_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    url = "https://api.fanvue.com/users/me"

    response = requests.get(url, headers=headers)

    print("Status:", response.status_code)
    print("Response:")
    print(response.text)


if __name__ == "__main__":
    run_test()