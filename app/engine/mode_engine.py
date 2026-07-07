class ModeEngine:
    def determine_mode(self, intent_score: int) -> str:
        if intent_score >= 60:
            return "conversion"
        if intent_score >= 35:
            return "tension"
        if intent_score >= 15:
            return "flirty"
        return "casual"