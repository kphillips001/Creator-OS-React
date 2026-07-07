from app.services.content_usage_service import ContentUsageService


def run_test():
    print("\n======================================")
    print("13B TEST — CONTENT USAGE TRACKING")
    print("======================================\n")

    service = ContentUsageService()

    USER = "test-user-123"

    # Step 1: mark content
    service.mark_content_seen(USER, "tease_001")
    service.mark_content_seen(USER, "vip_002")

    # Step 2: check seen
    print("\n--- CHECKING CONTENT ---")

    print("tease_001 seen:", service.has_seen_content(USER, "tease_001"))
    print("vip_002 seen:", service.has_seen_content(USER, "vip_002"))
    print("premium_003 seen:", service.has_seen_content(USER, "premium_003"))

    # Step 3: list all
    print("\n--- ALL SEEN CONTENT ---")
    print(service.get_seen_content(USER))

    print("\n======================================")
    print("13B TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()