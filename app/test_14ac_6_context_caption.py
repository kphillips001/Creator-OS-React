from app.services.conversation_context_builder import ConversationContextBuilder
from app.services.ppv_caption_service import PPVCaptionService


def run_test():
    print("\n=== 14AC-6: CONTEXT-AWARE PPV CAPTION TEST ===\n")

    thread_id = "thread_dedf82b76f"

    builder = ConversationContextBuilder()
    caption_service = PPVCaptionService()

    context = builder.build_context(
        thread_id=thread_id,
        limit=20,
    )

    if not context:
        print("\n❌ No context found. Stop here.")
        return

    content_metadata = {
        "classification": "VIP",
        "tier": "vip_offer",
        "tags": ["tight outfit", "mirror", "tease", "curves"],
        "summary": "Creator is posing in a tight outfit with a teasing mirror-style vibe.",
    }

    caption = caption_service.generate_context_aware_caption(
        chat_history=context,
        content_metadata=content_metadata,
    )

    print("\n--- FINAL PPV CAPTION ---")
    print(caption)

    print("\n=== TEST COMPLETE ===\n")

if __name__ == "__main__":
    run_test()