from app.services.content_caption_service import generate_text_outreach_opener


def main():
    print("\n=== 13D OUTREACH OPENER PROMPT TEST ===\n")

    samples = []

    for i in range(5):
        opener = generate_text_outreach_opener(
            {
                "user_type": "follower",
                "user_value_tier": "low",
                "attention_tier": "medium",
                "outreach_attempts": i % 3,
                "outreach_ignore_count": i % 2,
            }
        )
        samples.append(opener)
        print(f"{i + 1}. {opener}")

    bad_terms = [
        "buy",
        "unlock",
        "ppv",
        "subscribe",
        "subscription",
        "uploaded",
        "content",
    ]

    for opener in samples:
        lower = opener.lower()

        for term in bad_terms:
            if term in lower:
                raise AssertionError(
                    f"Bad outreach opener contained sales term '{term}': {opener}"
                )

        word_count = len(opener.split())
        if word_count > 14:
            raise AssertionError(
                f"Outreach opener is too long ({word_count} words): {opener}"
            )

    print("\n✅ 13D OUTREACH OPENER PROMPT TEST PASSED\n")


if __name__ == "__main__":
    main()