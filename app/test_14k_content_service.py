from app.services.content_service import ContentService


def run_test():
    print("\n=== 14K STEP 4: CONTENT SERVICE CMS FETCH TEST ===\n")

    service = ContentService()

    print("\n--- TEASE CMS CONTENT ---")
    tease = service.get_tease_cms_content()
    print("TEASE result:", tease)

    print("\n--- VIP CMS CONTENT ---")
    vip = service.get_vip_cms_content()
    print("VIP result:", vip)

    print("\n--- PREMIUM CMS CONTENT ---")
    premium = service.get_premium_cms_content()
    print("PREMIUM result:", premium)


if __name__ == "__main__":
    run_test()