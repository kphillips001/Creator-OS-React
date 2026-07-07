class ConversationEngine:
    def generate_response(self, persona: str, mode: str, user_message: str) -> str:
        persona = persona.lower().strip()

        responses = {
            "amanda": {
                "casual": "Hey you 😘 what are you getting into tonight?",
                "flirty": "Mmm I like the way you're talking to me already 😏",
                "tension": "You’re getting me a little worked up over here… 💋",
                "conversion": "I might have something a little more exclusive for you… wanna see? 😈",
            },
            "ava": {
                "casual": "Hey handsome 🙂 what are you up to tonight?",
                "flirty": "You’re kind of fun to tease already… 😘",
                "tension": "Careful… keep talking like that and I might misbehave 💋",
                "conversion": "I can show you a more private side of me… if you want it 😈",
            },
        }

        default_responses = {
            "casual": "Hey you 🙂",
            "flirty": "You’re cute when you talk like that 😏",
            "tension": "You’re making this very tempting 💋",
            "conversion": "I might have something special for you 😈",
        }

        persona_responses = responses.get(persona, default_responses)
        return persona_responses.get(mode, "Hey you 🙂")