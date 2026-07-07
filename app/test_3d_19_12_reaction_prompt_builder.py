from app.services.reaction_intelligence_expansion_service import (
    ReactionIntelligenceExpansionService,
)

from app.services.reaction_prompt_builder_service import (
    ReactionPromptBuilderService,
)


def main():
    intelligence_service = (
        ReactionIntelligenceExpansionService()
    )

    prompt_builder = (
        ReactionPromptBuilderService()
    )

    print(
        "\n=== 3D.19.12 REACTION PROMPT BUILDER TEST ===\n"
    )

    safe_intelligence = (
        intelligence_service.build_reaction_intelligence(
            monetization_event={
                "event_type": "purchase_received",
            },
            buyer_memory={
                "buyer_tier": "NON_BUYER",
            },
        )
    )

    safe_prompt = prompt_builder.build_reaction_prompt(
        monetization_event={
            "event_type": "purchase_received",
        },
        reaction_intelligence=safe_intelligence,
    )

    assert safe_prompt["success"] is True
    assert safe_prompt["provider"] == "openai"
    assert safe_prompt["prompt_mode"] == "safe_emotional"
    assert safe_prompt["adult_generation_allowed"] is False
    assert safe_prompt["send_allowed"] is False
    assert safe_prompt["generation_allowed"] is False
    assert "Do not be explicit" in safe_prompt["system_prompt"]

    premium_intelligence = (
        intelligence_service.build_reaction_intelligence(
            monetization_event={
                "event_type": "unlock_confirmation",
            },
            runtime_state={
                "heat_score": 95,
                "sexual_intensity": 85,
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    premium_prompt = prompt_builder.build_reaction_prompt(
        monetization_event={
            "event_type": "unlock_confirmation",
        },
        reaction_intelligence=premium_intelligence,
    )

    assert premium_prompt["success"] is True
    assert premium_prompt["provider"] == "grok"
    assert premium_prompt["prompt_mode"] == "premium_intimacy"
    assert premium_prompt["adult_generation_allowed"] is True
    assert premium_prompt["send_allowed"] is False
    assert premium_prompt["generation_allowed"] is False
    assert "private premium creator reply" in premium_prompt["system_prompt"]

    fallback_prompt = prompt_builder.build_reaction_prompt(
        monetization_event={
            "event_type": "purchase_received",
        },
        reaction_intelligence={
            "buyer_tier": "NON_BUYER",
            "premium_intimacy_routing": {
                "route": "safe_chat_only",
            },
            "realtime_reaction_llm_routing": {
                "llm_provider": "grok",
                "prompt_mode": "premium_intimacy",
                "adult_generation_allowed": True,
            },
        },
    )

    assert fallback_prompt["success"] is True
    assert fallback_prompt["provider"] == "openai"
    assert fallback_prompt["prompt_mode"] == "safe_emotional"
    assert fallback_prompt["adult_generation_allowed"] is False

    whale_intelligence = (
        intelligence_service.build_reaction_intelligence(
            monetization_event={
                "event_type": "purchase_received",
            },
            spend_profile={
                "buyer_tier": "WHALE",
            },
        )
    )

    whale_prompt = prompt_builder.build_reaction_prompt(
        monetization_event={
            "event_type": "purchase_received",
        },
        reaction_intelligence=whale_intelligence,
    )

    assert whale_prompt["success"] is True
    assert whale_prompt["provider"] == "grok"
    assert whale_prompt["generation_style"] == "exclusive_whale_retention"
    assert "Do not pressure the buyer" in whale_prompt["system_prompt"]

    print(
        "✅ 3D.19.12 reaction prompt builder passed"
    )


if __name__ == "__main__":
    main()