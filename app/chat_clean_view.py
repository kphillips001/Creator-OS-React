from app.main import start_app

def run_clean_chat():
    decision_engine = start_app()

    print("\n💬 CLEAN CHAT MODE (no logs)\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit"]:
            break

        result = decision_engine.process_message(user_input)

        response = result.get("response", "")

        print(f"Bot: {response}\n")


if __name__ == "__main__":
    run_clean_chat()