MOCK_CONTENT_CATALOG = [
    {
        "tag": "tease_preview_01",
        "type": "tease",
        "persona": "default",
        "category": "soft",
    },
    {
        "tag": "tease_preview_02",
        "type": "tease",
        "persona": "default",
        "category": "soft",
    },
    {
        "tag": "vip_lingerie_set_01",
        "type": "vip",
        "persona": "default",
        "category": "flirty",
    },
    {
        "tag": "vip_lingerie_set_02",
        "type": "vip",
        "persona": "default",
        "category": "flirty",
    },
    {
        "tag": "premium_tension_set_01",
        "type": "premium",
        "persona": "default",
        "category": "tension",
    },
    {
        "tag": "premium_tension_set_02",
        "type": "premium",
        "persona": "default",
        "category": "tension",
    },
]


def select_content_tag(
    offer_type: str,
    persona: str,
    subscriber_engagement_mode: str,
    content_catalog: list,
    previously_sent_tags: list = None,
) -> str:
    """
    7D.3 — Personalized content tag selection

    Selects actual content based on:
    - offer_type
    - persona
    - engagement mode
    - previously sent content

    Avoids repeating previously sent content when possible.
    """

    if previously_sent_tags is None:
        previously_sent_tags = []

    if offer_type == "none":
        return "none"

    preferred_category = "soft"

    if subscriber_engagement_mode == "flirty":
        preferred_category = "flirty"

    if subscriber_engagement_mode == "tension":
        preferred_category = "tension"

    # First pass: exact match, excluding previously sent content
    for content in content_catalog:
        if (
            content.get("type") == offer_type
            and content.get("persona") == persona
            and content.get("category") == preferred_category
            and content.get("tag") not in previously_sent_tags
        ):
            return content.get("tag")

    # Second pass: match offer type + persona, excluding previously sent content
    for content in content_catalog:
        if (
            content.get("type") == offer_type
            and content.get("persona") == persona
            and content.get("tag") not in previously_sent_tags
        ):
            return content.get("tag")

    # Third pass: if everything has already been sent, allow reuse as fallback
    for content in content_catalog:
        if (
            content.get("type") == offer_type
            and content.get("persona") == persona
        ):
            return content.get("tag")

    return "none"


if __name__ == "__main__":
    test_cases = [
        {
            "name": "No offer returns none",
            "offer_type": "none",
            "persona": "default",
            "mode": "casual",
            "previously_sent_tags": [],
            "expected": "none",
        },
        {
            "name": "First tease content selected",
            "offer_type": "tease",
            "persona": "default",
            "mode": "casual",
            "previously_sent_tags": [],
            "expected": "tease_preview_01",
        },
        {
            "name": "Second tease selected when first was already sent",
            "offer_type": "tease",
            "persona": "default",
            "mode": "casual",
            "previously_sent_tags": ["tease_preview_01"],
            "expected": "tease_preview_02",
        },
        {
            "name": "Second VIP selected when first VIP was already sent",
            "offer_type": "vip",
            "persona": "default",
            "mode": "flirty",
            "previously_sent_tags": ["vip_lingerie_set_01"],
            "expected": "vip_lingerie_set_02",
        },
        {
            "name": "Second premium selected when first premium was already sent",
            "offer_type": "premium",
            "persona": "default",
            "mode": "tension",
            "previously_sent_tags": ["premium_tension_set_01"],
            "expected": "premium_tension_set_02",
        },
        {
            "name": "Fallback allows reuse if all matching content was already sent",
            "offer_type": "premium",
            "persona": "default",
            "mode": "tension",
            "previously_sent_tags": [
                "premium_tension_set_01",
                "premium_tension_set_02",
            ],
            "expected": "premium_tension_set_01",
        },
        {
            "name": "Missing persona returns none",
            "offer_type": "premium",
            "persona": "ava",
            "mode": "tension",
            "previously_sent_tags": [],
            "expected": "none",
        },
    ]

    for case in test_cases:
        tag = select_content_tag(
            case["offer_type"],
            case["persona"],
            case["mode"],
            MOCK_CONTENT_CATALOG,
            case["previously_sent_tags"],
        )

        print("\n==============================")
        print(case["name"])
        print("==============================")
        print(
            f"offer_type={case['offer_type']} | persona={case['persona']} | "
            f"mode={case['mode']} | previously_sent={case['previously_sent_tags']} | "
            f"content_tag={tag}"
        )

        assert tag == case["expected"], (
            f"FAILED: {case['name']} expected {case['expected']} but got {tag}"
        )

    print("\n✅ 7D.3 PASSED — content personalization avoids repeats")