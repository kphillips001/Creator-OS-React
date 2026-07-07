from app.services.grok_caption_service import GrokCaptionService


def run_test():
    print("\n=== 14AC-8: GROK MASS PPV IMAGE-AWARE CAPTION TEST ===\n")

    service = GrokCaptionService()

    content_metadata = {
        "classification": "VIP",
        "tier": "vip_offer",
        "tags": ["mirror", "tight outfit", "curves", "tease"],
        "summary": "Creator is posing in a tight outfit with a teasing mirror-style vibe.",
    }

    # Replace this with a real publicly accessible image URL.
    image_url = "https://i.imgur.com/SqYGtrx.jpeg"

    caption = service.generate_mass_ppv_caption(
        content_metadata=content_metadata,
        image_url=image_url,
    )

    print("\n--- GROK MASS PPV CAPTION ---")
    print(caption)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()