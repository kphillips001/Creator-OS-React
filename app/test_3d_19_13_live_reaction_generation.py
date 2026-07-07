from dotenv import load_dotenv

load_dotenv()

from app.services.reaction_intelligence_expansion_service import (
    ReactionIntelligenceExpansionService,
)

from app.services.reaction_prompt_builder_service import (
    ReactionPromptBuilderService,
)

from app.services.reaction_llm_generation_service import (
    ReactionLLMGenerationService,
)


def main():
    intelligence_service = (
        ReactionIntelligenceExpansionService()
    )

    prompt_builder = ReactionPromptBuilderService()
    generator = ReactionLLMGenerationService()

    print(
        "\n=== 3D.19.13 LIVE GPT/GROK GENERATION PREVIEW ===\n"
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

    safe_result = (
        generator.generate_reaction_preview(
            safe_prompt
        )
    )

    print("\n--- OPENAI SAFE PREVIEW ---\n")
    print(safe_result)

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

    premium_prompt = (
        prompt_builder.build_reaction_prompt(
            monetization_event={
                "event_type": "unlock_confirmation",
            },
            reaction_intelligence=(
                premium_intelligence
            ),
        )
    )

    premium_result = (
        generator.generate_reaction_preview(
            premium_prompt
        )
    )

    print("\n--- GROK PREMIUM PREVIEW ---\n")
    print(premium_result)

    assert safe_result["send_allowed"] is False
    assert premium_result["send_allowed"] is False

    assert safe_result["queue_write_allowed"] is False
    assert premium_result["queue_write_allowed"] is False

    assert safe_result["preview_only"] is True
    assert premium_result["preview_only"] is True

    print(
        "\n✅ 3D.19.13 live reaction generation preview passed\n"
    )


if __name__ == "__main__":
    main()