from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n==============================")
    print("13D — GET FOLDER IDS")
    print("==============================\n")

    service = FanvueAPIService()

    # Try to fetch recent media
    response = service.list_vault_media(page=1, size=20)

    print("\n=== RAW RESPONSE ===\n")
    print(response)


if __name__ == "__main__":
    run_test()