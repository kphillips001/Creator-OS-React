class MockMemoryService:
    def __init__(self):
        self.store = {}

    def get_user_memory(self, user_id):
        return self.store.get(user_id, {})

    def set_field(self, user_id, field, value):
        if user_id not in self.store:
            self.store[user_id] = {}
        self.store[user_id][field] = value

    def increment_inbound_message(self, user_id):
        if user_id not in self.store:
            self.store[user_id] = {}

        current = self.store[user_id].get("message_count", 0)
        current += 1
        self.store[user_id]["message_count"] = current
        return self.store[user_id]


class TestDecisionEngine:
    def __init__(self, memory_service):
        self.memory = memory_service

    def generate_response(self, message: str, mode: str):
        """
        🔥 Simulated GPT behavior based on mode
        """

        if mode == "casual":
            return f"haha yeah, just chilling 😌 what about you?"

        elif mode == "flirty":
            return f"mmm depends… what would you want me to be doing? 😏"

        elif mode == "tension":
            return f"careful… you might not be ready for that 😈"

        return "interesting..."

    def process_message(self, user_id: str, message: str):
        user_memory = self.memory.get_user_memory(user_id)

        # 🔥 Conversation Streak
        conversation_streak = user_memory.get("conversation_streak", 0) or 0
        conversation_streak += 1
        conversation_streak = min(conversation_streak, 100)
        self.memory.set_field(user_id, "conversation_streak", conversation_streak)

        # 🔥 Engagement Depth
        engagement_depth_score = user_memory.get("engagement_depth_score", 0) or 0
        word_count = len(message.split())

        if word_count > 8:
            engagement_depth_score += 2
        elif word_count > 3:
            engagement_depth_score += 1

        engagement_depth_score = min(engagement_depth_score, 50)
        self.memory.set_field(user_id, "engagement_depth_score", engagement_depth_score)

        # 🔥 Engagement Tier
        if engagement_depth_score >= 5 or conversation_streak >= 5:
            engagement_tier = "HIGH"
        elif engagement_depth_score >= 2 or conversation_streak >= 3:
            engagement_tier = "MEDIUM"
        else:
            engagement_tier = "LOW"

        self.memory.set_field(user_id, "engagement_tier", engagement_tier)

        # 🔥 Mode Assignment
        if engagement_tier == "LOW":
            mode = "casual"
        elif engagement_tier == "MEDIUM":
            mode = "flirty"
        else:
            mode = "tension"

        self.memory.set_field(user_id, "subscriber_engagement_mode", mode)

        # 🔥 Simulated GPT Response
        response = self.generate_response(message, mode)

        print(
            f"[TEST] msg='{message}' | words={word_count} | depth={engagement_depth_score} | "
            f"streak={conversation_streak} | tier={engagement_tier} | mode={mode}"
        )

        print(f"👉 RESPONSE: {response}\n")

        self.memory.increment_inbound_message(user_id)


# 🔥 RUN TEST
if __name__ == "__main__":
    memory = MockMemoryService()
    engine = TestDecisionEngine(memory)

    user_id = "1:1"

    messages = [
        "hey",
        "what are you doing tonight",
        "I was thinking about what you said earlier and honestly I kind of want something more exclusive",
        "so what do you offer",
        "tell me more about it",
    ]

    for msg in messages:
        engine.process_message(user_id, msg)