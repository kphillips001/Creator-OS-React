from app.repositories.fanvue_message_sync_repository import (
    get_fanvue_messages_for_thread
)


class ConversationContextBuilder:

    def build_context(
        self,
        thread_id: str,
        limit: int = 15,
    ):
        print("\n[CONTEXT BUILDER START]")

        messages = get_fanvue_messages_for_thread(
            thread_id=thread_id,
            limit=limit
        )

        print(f"[MESSAGES FETCHED] {len(messages)}")

        context = []

        for msg in messages:
            direction = msg["direction"]
            text = msg["message_text"]

            if not text:
                continue

            role = "user" if direction == "inbound" else "assistant"

            context.append({
                "role": role,
                "content": text
            })

        print(f"[CONTEXT BUILT] {len(context)} messages")

        return context