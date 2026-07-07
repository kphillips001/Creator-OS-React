from app.services.conversation_context_builder import ConversationContextBuilder
from app.services.ppv_caption_service import PPVCaptionService
from app.services.grok_caption_service import GrokCaptionService


def run_test():
    print("\n=== 14AC-7: GPT VS GROK CAPTION TEST ===\n")

    thread_id = "thread_dedf82b76f"

    builder = ConversationContextBuilder()
    gpt_service = PPVCaptionService()
    grok_service = GrokCaptionService()

    context = builder.build_context(thread_id=thread_id, limit=20)

    if not context:
        print("\n❌ No context found. Stop here.")
        return

    content_metadata = {
        "classification": "VIP",
        "tier": "vip_offer",
        "tags": ["tight outfit", "mirror", "tease", "curves"],
        "summary": "Creator is posing in a tight outfit with a teasing mirror-style vibe.",
    }

    print("\n--- GENERATING GPT CAPTION ---")
    gpt_caption = gpt_service.generate_context_aware_caption(
        chat_history=context,
        content_metadata=content_metadata,
    )

    print("\n--- GENERATING GROK CAPTION ---")
    grok_caption = grok_service.generate_caption(
        chat_history=context,
        content_metadata=content_metadata,
    )

    print("\n==============================")
    print("GPT CAPTION:")
    print(gpt_caption)

    print("\nGROK CAPTION:")
    print(grok_caption)
    print("==============================\n")

    print("=== 14AC-7 TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()