import os
from dotenv import load_dotenv
from openai import OpenAI

from app.services.conversation_context_builder import ConversationContextBuilder


def generate_context_aware_reply(chat_history: list) -> str:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from .env")

    client = OpenAI(api_key=api_key)

    system_prompt = """
You are replying as a Fanvue creator in a private chat.

STRICT RULES:
- Use the recent conversation context.
- Match the user's current tone.
- Keep it short and natural.
- Do NOT sound like a bot.
- Do NOT mention AI.
- Do NOT over-explain.
- Do NOT sell yet.
- Build curiosity and tension.
- 1 sentence max.
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)

    # Ask GPT to continue naturally from the latest conversation point.
    messages.append({
        "role": "user",
        "content": "Continue the conversation naturally from here."
    })

    print("\n[GPT CONTEXT INJECTED]")
    print(f"Messages sent to GPT: {len(messages)}")

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.9,
        max_tokens=80,
    )

    return completion.choices[0].message.content.strip()


def run_test():
    print("\n=== 14AC-5: GPT CONTEXT INJECTION TEST ===\n")

    thread_id = "thread_dedf82b76f"

    builder = ConversationContextBuilder()

    context = builder.build_context(
        thread_id=thread_id,
        limit=20,
    )

    print("\n--- CONTEXT SENT TO GPT ---")
    for i, msg in enumerate(context, start=1):
        print(f"{i}. {msg}")

    if not context:
        print("\n❌ No context found. Stop here.")
        return

    reply = generate_context_aware_reply(context)

    print("\n--- GPT CONTEXT-AWARE REPLY ---")
    print(reply)

    print("\n=== 14AC-5 TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()