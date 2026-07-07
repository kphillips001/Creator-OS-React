from app.services.conversation_context_builder import ConversationContextBuilder


def run_test():
    print("\n=== 14AC-4: CONTEXT BUILDER TEST ===\n")

    # ✅ FIXED thread_id (correct value from previous step)
    thread_id = "thread_dedf82b76f"

    builder = ConversationContextBuilder()

    context = builder.build_context(
        thread_id=thread_id,
        limit=20
    )

    print("\n--- GPT CONTEXT ---\n")

    if not context:
        print("⚠️ No messages found. Check thread_id or DB data.\n")
    else:
        for i, msg in enumerate(context, start=1):
            print(f"{i}. {msg}")

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()