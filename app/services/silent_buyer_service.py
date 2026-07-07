from app.services.memory_service import MemoryService


class SilentBuyerService:
    def __init__(self):
        self.memory_service = MemoryService()

    def calculate_silent_buyer_score(self, user_memory: dict) -> int:
        if not user_memory:
            return 0

        ppv_sent_count = user_memory.get("ppv_sent_count", 0) or 0
        ppv_open_count = user_memory.get("ppv_open_count", 0) or 0
        ppv_purchase_count = user_memory.get("ppv_purchase_count", 0) or 0
        avg_ppv_spend = user_memory.get("avg_ppv_spend", 0) or 0
        inbound_message_count = user_memory.get("inbound_message_count", 0) or 0

        score = 0

        # Opens matter
        score += ppv_open_count * 2

        # Purchases matter much more
        score += ppv_purchase_count * 10

        # Spending quality matters
        if avg_ppv_spend >= 100:
            score += 20
        elif avg_ppv_spend >= 50:
            score += 10
        elif avg_ppv_spend >= 20:
            score += 5

        # Quiet buyers should score higher if they buy without much chatting
        if inbound_message_count <= 3 and ppv_purchase_count > 0:
            score += 10
        elif inbound_message_count <= 10 and ppv_purchase_count > 0:
            score += 5

        # Prevent weird inflation if nothing was ever sent
        if ppv_sent_count == 0:
            return 0

        return score

    def determine_silent_buyer_tier(self, user_memory: dict) -> str:
        score = self.calculate_silent_buyer_score(user_memory)

        ppv_open_count = user_memory.get("ppv_open_count", 0) or 0
        ppv_purchase_count = user_memory.get("ppv_purchase_count", 0) or 0

        if ppv_purchase_count >= 5 or score >= 60:
            return "strong_buyer"

        if ppv_purchase_count >= 1 or score >= 25:
            return "buyer"

        if ppv_open_count >= 1 or score >= 10:
            return "curious"

        return "none"

    def evaluate_silent_buyer(self, user_id: str) -> dict:
        user_memory = self.memory_service.get_user_memory(user_id)

        if not user_memory:
            return {
                "silent_buyer_score": 0,
                "silent_buyer_tier": "none",
            }

        silent_buyer_score = self.calculate_silent_buyer_score(user_memory)
        silent_buyer_tier = self.determine_silent_buyer_tier(user_memory)

        self.memory_service.update_user_memory(
            user_id,
            {
                "silent_buyer_score": silent_buyer_score,
                "silent_buyer_tier": silent_buyer_tier,
            }
        )

        return {
            "silent_buyer_score": silent_buyer_score,
            "silent_buyer_tier": silent_buyer_tier,
        }