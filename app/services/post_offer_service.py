from datetime import datetime
from typing import Optional, Dict, Any


class PostOfferService:
    """
    Post-offer follow-up / nudge engine.

    19M Phase 10:
    - No hard-coded phrase lists.
    - Uses GPT classifier output for hesitation, curiosity, rejection, and buy signals.
    """

    def __init__(self):
        self.offer_followup_window_minutes = 180
        self.min_minutes_before_first_nudge = 2
        self.min_minutes_between_nudges = 5
        self.max_nudges_per_offer = 2

    def get_timestamp(self) -> str:
        return datetime.utcnow().isoformat()

    def _parse_timestamp(self, timestamp_value) -> Optional[datetime]:
        if not timestamp_value:
            return None

        if isinstance(timestamp_value, datetime):
            return timestamp_value

        try:
            cleaned = str(timestamp_value).replace("Z", "")
            return datetime.fromisoformat(cleaned)
        except Exception:
            return None

    def _minutes_since(self, timestamp_value) -> Optional[float]:
        parsed = self._parse_timestamp(timestamp_value)
        if not parsed:
            return None

        return (datetime.utcnow() - parsed).total_seconds() / 60

    def _normalize_text(self, text: Optional[str]) -> str:
        return (text or "").strip().lower()

    def _is_gpt_confident(
        self,
        classifier_result: Dict[str, Any] | None,
        threshold: float = 0.6,
    ) -> bool:
        classifier_result = classifier_result or {}

        try:
            confidence = float(classifier_result.get("confidence", 0.0) or 0.0)
            return confidence >= threshold
        except Exception:
            return False

    def _is_blocked_route(self, memory: Dict[str, Any]) -> bool:
        route = self._normalize_text(memory.get("current_route", "chat"))
        return route in ["support", "custom_request"]

    def has_active_offer_window(self, memory: Dict[str, Any]) -> bool:
        last_offer_timestamp = memory.get("last_offer_timestamp")
        last_offer_type = memory.get("last_offer_type")

        if not last_offer_timestamp or not last_offer_type:
            return False

        minutes_since_offer = self._minutes_since(last_offer_timestamp)
        if minutes_since_offer is None:
            return False

        return minutes_since_offer <= self.offer_followup_window_minutes

    def is_offer_already_resolved(
        self,
        memory: Dict[str, Any],
        message: str = "",
        classifier_result: Dict[str, Any] | None = None,
    ) -> bool:
        """
        Determines if the current offer follow-up flow should stop.

        GPT-driven:
        - converted users resolve the offer
        - rejecting users resolve/decline the offer
        - close-ready users should NOT be nudged; they should move to close logic
        """

        offer_state = self._normalize_text(memory.get("offer_state", "none"))

        if offer_state in ["converted", "declined", "expired"]:
            return True

        classifier_result = classifier_result or {}

        if not self._is_gpt_confident(classifier_result):
            return False

        user_state = classifier_result.get("user_state")
        recommended_action = classifier_result.get("recommended_action")
        buying_intent = bool(classifier_result.get("buying_intent", False))
        close_ready = bool(classifier_result.get("close_ready", False))
        exit_ready = bool(classifier_result.get("exit_ready", False))

        if user_state == "converted":
            return True

        if user_state == "rejecting":
            return True

        if exit_ready and recommended_action == "exit":
            return True

        if buying_intent or close_ready or recommended_action == "close":
            return True

        return False

    def detect_post_offer_interest(
        self,
        memory: Dict[str, Any],
        message: str = "",
        classifier_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Detects post-offer interest signals using GPT classifier output only.
        No phrase matching.
        """

        classifier_result = classifier_result or {}

        intent_level = classifier_result.get("intent_level")
        buying_intent = bool(classifier_result.get("buying_intent", False))
        close_ready = bool(classifier_result.get("close_ready", False))
        exit_ready = bool(classifier_result.get("exit_ready", False))
        objection_type = classifier_result.get("objection_type")
        recommended_action = classifier_result.get("recommended_action")
        user_state = classifier_result.get("user_state")
        curiosity_level = classifier_result.get("curiosity_level")
        escalation_ready = bool(classifier_result.get("escalation_ready", False))

        intent_score = memory.get("intent_score", 0) or 0

        if not self._is_gpt_confident(classifier_result):
            return {
                "has_hesitation": False,
                "has_curiosity": False,
                "has_negative_signal": False,
                "has_buy_signal": False,
                "high_intent": intent_score >= 70,
            }

        has_buy_signal = (
            buying_intent
            or close_ready
            or user_state == "ready_to_buy"
            or recommended_action == "close"
        )

        has_negative_signal = (
            user_state == "rejecting"
            or (
                exit_ready
                and recommended_action == "exit"
                and user_state != "converted"
            )
        )

        has_hesitation = (
            user_state == "hesitant"
            or objection_type in ["hesitation", "price", "time", "trust"]
        )

        has_curiosity = (
            user_state in ["curious", "engaged"]
            or curiosity_level in ["medium", "high"]
            or escalation_ready
            or recommended_action in ["build_tension", "offer"]
        )

        high_intent = (
            intent_score >= 70
            or intent_level == "high"
            or buying_intent
            or close_ready
        )

        return {
            "has_hesitation": has_hesitation,
            "has_curiosity": has_curiosity,
            "has_negative_signal": has_negative_signal,
            "has_buy_signal": has_buy_signal,
            "high_intent": high_intent,
        }

    def should_send_nudge(
        self,
        memory: Dict[str, Any],
        message: str = "",
        classifier_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not self.has_active_offer_window(memory):
            return {
                "send_nudge": False,
                "reason": "No active offer follow-up window.",
            }

        if self._is_blocked_route(memory):
            return {
                "send_nudge": False,
                "reason": "Route is blocked for nudges.",
            }

        if self.is_offer_already_resolved(memory, message, classifier_result):
            return {
                "send_nudge": False,
                "reason": "Offer already resolved, declined, or ready for close.",
            }

        post_offer_nudge_count = memory.get("post_offer_nudge_count", 0) or 0
        if post_offer_nudge_count >= self.max_nudges_per_offer:
            return {
                "send_nudge": False,
                "reason": "Maximum nudges already reached.",
            }

        minutes_since_offer = self._minutes_since(memory.get("last_offer_timestamp"))
        if minutes_since_offer is None:
            return {
                "send_nudge": False,
                "reason": "Could not parse last_offer_timestamp.",
            }

        last_nudge_timestamp = memory.get("last_nudge_timestamp")
        minutes_since_nudge = (
            self._minutes_since(last_nudge_timestamp)
            if last_nudge_timestamp
            else None
        )

        if post_offer_nudge_count == 0:
            if minutes_since_offer < self.min_minutes_before_first_nudge:
                return {
                    "send_nudge": False,
                    "reason": "Too soon for first nudge.",
                }
        else:
            if (
                minutes_since_nudge is not None
                and minutes_since_nudge < self.min_minutes_between_nudges
            ):
                return {
                    "send_nudge": False,
                    "reason": "Too soon since last nudge.",
                }

        signal_result = self.detect_post_offer_interest(
            memory,
            message,
            classifier_result,
        )

        should_nudge = (
            signal_result["has_hesitation"]
            or signal_result["has_curiosity"]
            or signal_result["high_intent"]
        )

        if not should_nudge:
            return {
                "send_nudge": False,
                "reason": "No qualifying GPT post-offer interest signals detected.",
                "signal_result": signal_result,
            }

        return {
            "send_nudge": True,
            "reason": "GPT post-offer nudge conditions met.",
            "signal_result": signal_result,
        }

    def determine_nudge_type(
        self,
        memory: Dict[str, Any],
        message: str = "",
        classifier_result: Dict[str, Any] | None = None,
    ) -> str:
        signal_result = self.detect_post_offer_interest(
            memory,
            message,
            classifier_result,
        )

        is_whale = bool(memory.get("is_whale", False))
        nudge_count = memory.get("post_offer_nudge_count", 0) or 0

        if is_whale:
            return "soft_followup"

        if signal_result["has_buy_signal"]:
            return "closing_followup"

        if nudge_count == 0:
            if signal_result["high_intent"] or signal_result["has_curiosity"]:
                return "confident_followup"
            return "soft_followup"

        if nudge_count == 1:
            if signal_result["has_curiosity"] or signal_result["high_intent"]:
                return "confident_followup"
            return "last_chance_followup"

        return "last_chance_followup"

    def build_nudge_payload(
        self,
        memory: Dict[str, Any],
        message: str = "",
        classifier_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        decision = self.should_send_nudge(memory, message, classifier_result)

        if not decision["send_nudge"]:
            return {
                "send_nudge": False,
                "nudge_type": None,
                "reason": decision["reason"],
                "offer_state": memory.get("offer_state", "none"),
                "signal_result": decision.get("signal_result"),
            }

        nudge_type = self.determine_nudge_type(memory, message, classifier_result)

        return {
            "send_nudge": True,
            "nudge_type": nudge_type,
            "reason": decision["reason"],
            "offer_state": "nudged",
            "last_offer_type": memory.get("last_offer_type"),
            "last_offer_content_tag": memory.get("last_offer_content_tag"),
            "last_offer_price": memory.get("last_offer_price"),
            "post_offer_nudge_count": (memory.get("post_offer_nudge_count", 0) or 0) + 1,
            "last_nudge_timestamp": self.get_timestamp(),
            "last_nudge_type": nudge_type,
            "signal_result": decision.get("signal_result"),
        }

    def apply_nudge_update(
        self,
        memory: Dict[str, Any],
        nudge_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        updated_memory = dict(memory)

        if not nudge_payload.get("send_nudge"):
            return updated_memory

        updated_memory["offer_state"] = nudge_payload.get("offer_state", "nudged")
        updated_memory["post_offer_nudge_count"] = nudge_payload.get(
            "post_offer_nudge_count",
            updated_memory.get("post_offer_nudge_count", 0),
        )
        updated_memory["last_nudge_timestamp"] = nudge_payload.get("last_nudge_timestamp")
        updated_memory["last_nudge_type"] = nudge_payload.get("last_nudge_type")

        return updated_memory

    def mark_offer_sent(
        self,
        memory: Dict[str, Any],
        offer_type: str,
        content_tag: Optional[str] = None,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        updated_memory = dict(memory)
        updated_memory["last_offer_timestamp"] = self.get_timestamp()
        updated_memory["last_offer_type"] = offer_type
        updated_memory["last_offer_content_tag"] = content_tag
        updated_memory["last_offer_price"] = price
        updated_memory["post_offer_nudge_count"] = 0
        updated_memory["last_nudge_timestamp"] = None
        updated_memory["last_nudge_type"] = None
        updated_memory["offer_state"] = "offered"
        updated_memory["messages_since_last_offer"] = 0
        return updated_memory

    def increment_post_offer_message_count(
        self,
        memory: Dict[str, Any],
    ) -> Dict[str, Any]:
        updated_memory = dict(memory)

        if memory.get("last_offer_timestamp"):
            updated_memory["messages_since_last_offer"] = (
                (memory.get("messages_since_last_offer", 0) or 0) + 1
            )

        return updated_memory

    def mark_offer_converted(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        updated_memory = dict(memory)
        updated_memory["offer_state"] = "converted"
        return updated_memory

    def mark_offer_declined(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        updated_memory = dict(memory)
        updated_memory["offer_state"] = "declined"
        return updated_memory

    def expire_offer_if_needed(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        updated_memory = dict(memory)

        if not self.has_active_offer_window(memory) and memory.get("last_offer_timestamp"):
            current_state = self._normalize_text(memory.get("offer_state", "none"))
            if current_state not in ["converted", "declined", "expired"]:
                updated_memory["offer_state"] = "expired"

        return updated_memory