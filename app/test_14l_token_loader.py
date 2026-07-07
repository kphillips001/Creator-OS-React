from app.services.fanvue_oauth_service import FanvueOAuthService


def run_test():
    print("\n=== 14L TOKEN LOADER / AUTO REFRESH TEST ===\n")

    service = FanvueOAuthService()
    access_token = service.get_valid_access_token()

    print("Access token loaded:", bool(access_token))
    print("Access token preview:", access_token[:25] + "...")


if __name__ == "__main__":
    run_test()