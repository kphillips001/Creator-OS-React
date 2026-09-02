from datetime import datetime
import random


class OfferService:
    OFFER_TYPE_NONE = "none"
    OFFER_TYPE_TEASE = "tease_offer"
    OFFER_TYPE_VIP = "vip_offer"
    OFFER_TYPE_PREMIUM = "premium_offer"

    def __init__(self):
        self.cooldown_minutes = 15
        self.hard_pause_after_offers = 2
        self.min_messages_after_pause = 1
        self.min_messages_for_reentry = 2

    def determine_dynamic_price(self, offer_type: str, base_price: int, memory: dict = None) -> int:
        """
        Adjust pricing based on user heat and buying signals.
        This layers dynamic pricing on top of the selected content's base price.
        """
        if not memory:
            return base_price

        intent_score = memory.get("intent_score", 0) or 0
        exclusive_interest_count = memory.get("exclusive_interest_count", 0) or 0
        offers_shown_count = memory.get("offers_shown_count", 0) or 0
        signals = memory.get("intent_signals", []) or []
        last_content_tier = memory.get("last_content_tier", "") or ""

        best_request = any(sig in signals for sig in ["best_request", "best_request_after_offer"])
        closing_intent = any(sig in signals for sig in ["closing_intent", "closing_after_offer"])

        # Keep tease simple and low-friction
        if offer_type == self.OFFER_TYPE_TEASE:
            return base_price

        # VIP pricing
        if offer_type == self.OFFER_TYPE_VIP:
            # Premium-tier content should command more
            if last_content_tier == "premium":
                if best_request and offers_shown_count >= 1:
                    return base_price + 20
                if closing_intent or intent_score >= 90:
                    return base_price + 10
                return base_price

            # High-tier content gets a moderate uplift
            if last_content_tier == "high":
                if best_request or closing_intent or intent_score >= 75:
                    return base_price + 8
                if intent_score >= 50 or exclusive_interest_count >= 2:
                    return base_price + 5
                return base_price

            # Mid / low VIP scaling
            if intent_score >= 70 or exclusive_interest_count >= 2:
                return base_price + 5
            if intent_score >= 40:
                return base_price + 2

            return base_price

        # Premium pricing
        if offer_type == self.OFFER_TYPE_PREMIUM:
            if last_content_tier == "premium":
                if best_request and offers_shown_count >= 1:
                    return base_price + 30
                if closing_intent or intent_score >= 90:
                    return base_price + 20
                if intent_score >= 75 or exclusive_interest_count >= 3:
                    return base_price + 15
                return base_price + 10

            if last_content_tier == "high":
                if best_request or closing_intent or intent_score >= 85:
                    return base_price + 20
                if intent_score >= 65 or exclusive_interest_count >= 2:
                    return base_price + 12
                return base_price + 8

            if intent_score >= 85 or exclusive_interest_count >= 3:
                return base_price + 12
            if intent_score >= 60:
                return base_price + 8

            return base_price + 5

        return base_price

    def _is_sales_eligible_route(self, memory: dict = None) -> bool:
        """
        Routes allowed to naturally continue sales logic.
        """
        if not memory:
            return True

        current_route = (memory.get("current_route", "chat") or "chat").strip().lower()
        return current_route in ["chat", "sales", "video_request"]

    def _is_support_route(self, memory: dict = None) -> bool:
        if not memory:
            return False
        return (memory.get("current_route", "") or "").strip().lower() == "support"

    def _is_custom_request_route(self, memory: dict = None) -> bool:
        if not memory:
            return False
        return (memory.get("current_route", "") or "").strip().lower() == "custom_request"

    def _is_video_request_route(self, memory: dict = None) -> bool:
        if not memory:
            return False
        return (memory.get("current_route", "") or "").strip().lower() == "video_request"

    def _is_reconnect_route(self, memory: dict = None) -> bool:
        if not memory:
            return False
        return (memory.get("current_route", "") or "").strip().lower() == "reconnect"
    
    
    def _determine_subscriber_offer_type(self, intent_tier: str, mode: str, memory: dict) -> dict:
        """
        Clean subscriber-specific offer selection logic.
        This isolates subscriber behavior from general offer logic.
        """
        
        intent_score = memory.get("intent_score", 0) or 0
        exclusive_interest = memory.get("exclusive_interest_count", 0) or 0
        closing_questions = memory.get("closing_questions_count", 0) or 0
        subscriber_profile = memory.get("subscriber_profile", "none") or "none"
        subscriber_rewarm_required = memory.get("subscriber_rewarm_required", False)

        print("\n🎯 [OFFER TYPE SELECTION]")
        print("subscriber_profile:", subscriber_profile)
        print("intent_score:", intent_score)
        print("exclusive_interest:", exclusive_interest)
        print("closing_questions:", closing_questions)
        print("rewarm_required:", subscriber_rewarm_required)

        # ---------------- REWARM REQUIRED ----------------
        # Hard block: no offers until rewarm is completed
        if subscriber_rewarm_required:
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": "Subscriber rewarm required before offers",
            }

        # ---------------- NEW SUBSCRIBER ----------------
        if subscriber_profile == "NEW_SUBSCRIBER":
            if intent_score >= 85 or closing_questions >= 2 or exclusive_interest >= 3:
                return {
                    "offer_type": self.OFFER_TYPE_TEASE,
                    "price": 10,
                    "description": "New subscriber soft tease offer",
                }
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": "Warm-up phase for new subscriber",
            }

        # ---------------- LAPSED SUBSCRIBER ----------------
        if subscriber_profile == "LAPSED_SUBSCRIBER":
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": "Lapsed subscriber requires rewarm",
            }

        # ---------------- HIGH VALUE SUBSCRIBER ----------------
        if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            return {
                "offer_type": self.OFFER_TYPE_PREMIUM,
                "price": 50,
                "description": "High-value subscriber premium offer",
            }

        # ---------------- ACTIVE / DEFAULT SUBSCRIBER ----------------
        if intent_score >= 75 or closing_questions >= 1 or exclusive_interest >= 2:
            return {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "Subscriber VIP offer",
            }

        if intent_score >= 40:
            return {
                "offer_type": self.OFFER_TYPE_TEASE,
                "price": 10,
                "description": "Subscriber tease offer",
            }

        return {
            "offer_type": self.OFFER_TYPE_NONE,
            "price": 0,
            "description": "No subscriber offer",
        }
    
    def should_clear_subscriber_rewarm(self, memory: dict) -> bool:
        """
        Determine whether a subscriber has re-engaged enough
        to clear subscriber_rewarm_required.
        """

        if not memory:
            return False

        subscriber_rewarm_required = memory.get("subscriber_rewarm_required", False)

        if not subscriber_rewarm_required:
            return False

        intent_score = memory.get("intent_score", 0) or 0
        exclusive_interest = memory.get("exclusive_interest_count", 0) or 0
        closing_questions = memory.get("closing_questions_count", 0) or 0
        message_count = memory.get("message_count", 0) or 0
        messages_since_last_offer = memory.get("messages_since_last_offer", 0) or 0

        if (
            intent_score >= 50
            or exclusive_interest >= 1
            or closing_questions >= 1
            or message_count >= 3
            or messages_since_last_offer >= 3
        ):
            return True

        return False
    
    def build_clear_subscriber_rewarm_updates(self, memory: dict) -> dict:
        """
        Build memory updates to clear subscriber rewarm state.
        This does not write to the database directly.
        """

        if not self.should_clear_subscriber_rewarm(memory):
            return {}

        return {
            "subscriber_rewarm_required": False,
            "subscriber_fatigue_flag": False,
        }
    
    def _apply_subscriber_offer_escalation(self, offer: dict, memory: dict) -> dict:
        """
        Escalate offer intelligently based on previous offer history and user behavior.
        Also prevents repeating the same offer tier too quickly.
        """
        
        if not memory or not offer:
            return offer

        last_offer_type = memory.get("last_offer_type", self.OFFER_TYPE_NONE)
        intent_score = memory.get("intent_score", 0) or 0
        exclusive_interest = memory.get("exclusive_interest_count", 0) or 0
        closing_questions = memory.get("closing_questions_count", 0) or 0
        messages_since_last_offer = memory.get("messages_since_last_offer", 0) or 0
        current_type = offer.get("offer_type", self.OFFER_TYPE_NONE)

        print("\n📈 [ESCALATION ENGINE]")
        print("last_offer_type:", last_offer_type)
        print("current_offer_type:", current_type)
        print("intent_score:", intent_score)
        print("exclusive_interest:", exclusive_interest)
        print("closing_questions:", closing_questions)
        print("messages_since_last_offer:", messages_since_last_offer)

        # ---------------- ESCALATION: TEASE → VIP ----------------
        if (
            last_offer_type == self.OFFER_TYPE_TEASE
            and current_type == self.OFFER_TYPE_TEASE
            and messages_since_last_offer >= 1
            and (
                intent_score >= 60
                or exclusive_interest >= 2
                or closing_questions >= 1
            )
        ):
            return {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "Escalated from tease to VIP",
            }

        # ---------------- ESCALATION: VIP → PREMIUM ----------------
        if (
            last_offer_type == self.OFFER_TYPE_VIP
            and current_type == self.OFFER_TYPE_VIP
            and messages_since_last_offer >= 1
            and (
                intent_score >= 85
                or exclusive_interest >= 3
                or closing_questions >= 2
            )
        ):
            return {
                "offer_type": self.OFFER_TYPE_PREMIUM,
                "price": 50,
                "description": "Escalated from VIP to premium",
            }

        # ---------------- REPETITION GUARD ----------------
        # Prevent sending the same offer tier again too quickly
        if (
            current_type == last_offer_type
            and current_type in [
                self.OFFER_TYPE_TEASE,
                self.OFFER_TYPE_VIP,
                self.OFFER_TYPE_PREMIUM,
            ]
            and messages_since_last_offer < 2
        ):
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": f"Repeated {current_type} suppressed until more engagement",
            }

        return offer
    
    def build_offer_memory_updates(self, offer: dict, memory: dict = None) -> dict:
        """
        Build memory updates after an offer is selected/sent.
        This does not write to the database directly.
        It only returns the fields that should be persisted.
        """

        if not offer or offer.get("offer_type") == self.OFFER_TYPE_NONE:
            return {}

        current_offers_shown = 0
        if memory:
            current_offers_shown = memory.get("offers_shown_count", 0) or 0

        return {
            "last_offer_type": offer.get("offer_type"),
            "last_offer_price": offer.get("price", 0),
            "last_offer_timestamp": self.get_offer_timestamp(),
            "offers_shown_count": current_offers_shown + 1,
            "messages_since_last_offer": 0,
        }

    def determine_offer(self, intent_tier: str, mode: str, memory: dict = None) -> dict:
        """
        Decide what broad offer category is appropriate.
        Actual content price/tier is selected later by ContentService.
        """
        price_questions = memory.get("price_questions_count", 0) if memory else 0
        user_value_tier = memory.get("user_value_tier", "cold") if memory else "cold"
        is_whale = memory.get("is_whale", False) if memory else False
        exclusive_interest = memory.get("exclusive_interest_count", 0) if memory else 0
        closing_questions = memory.get("closing_questions_count", 0) if memory else 0
        prior_intent_score = memory.get("intent_score", 0) if memory else 0
        offers_shown = memory.get("offers_shown_count", 0) if memory else 0
        message_score = memory.get("message_score", 0) if memory else 0
        messages_since_last_offer = memory.get("messages_since_last_offer", 0) if memory else 0
        last_offer_type = memory.get("last_offer_type", self.OFFER_TYPE_NONE) if memory else self.OFFER_TYPE_NONE
        signals = memory.get("intent_signals", []) if memory else []

        # ✅ 4E — subscriber-aware inputs
        is_subscriber = memory.get("is_subscriber", False) if memory else False
        relationship_status = (memory.get("relationship_status", "unknown") if memory else "unknown") or "unknown"
        subscriber_profile = (memory.get("subscriber_profile", "none") if memory else "none") or "none"
        behavior_config = memory.get("behavior_config", {}) if memory else {}
        subscriber_pacing_level = behavior_config.get("pacing_level", "normal")
        subscriber_pressure_level = behavior_config.get("monetization_pressure", "medium")

        normalized_signals = [s.lower().replace(" ", "_") for s in signals]

        hard_buy_reentry = any(
            sig in normalized_signals
            for sig in [
                "want_it",
                "im_ready",
                "take_it",
                "send_it_now",
            ]
        )

        # Route-aware shaping first
        if self._is_support_route(memory):
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": "Offer suppressed during support route",
            }

        if self._is_custom_request_route(memory):
            return {
                "offer_type": self.OFFER_TYPE_NONE,
                "price": 0,
                "description": "Offer suppressed during custom request intake",
            }

        # Reconnect should warm up before selling unless there is strong buying heat
        if self._is_reconnect_route(memory):
            if not (
                intent_tier == "hot"
                or prior_intent_score >= 85
                or closing_questions >= 1
                or hard_buy_reentry
            ):
                return {
                    "offer_type": self.OFFER_TYPE_NONE,
                    "price": 0,
                    "description": "Offer suppressed during reconnect warm-up",
                }

        # Video request gets sales priority but still follows buying logic
        if self._is_video_request_route(memory):
            if (
                intent_tier in ["medium", "hot"]
                or prior_intent_score >= 40
                or exclusive_interest >= 1
                or price_questions >= 1
            ):
                offer = {
                    "offer_type": self.OFFER_TYPE_VIP,
                    "price": 25,
                    "description": "Video-led VIP offer",
                }
                offer["price"] = self.determine_dynamic_price(
                    offer_type=offer["offer_type"],
                    base_price=offer["price"],
                    memory=memory,
                )
                return offer

        # ✅ NEW — centralized subscriber offer logic
        if is_subscriber:
            offer = self._determine_subscriber_offer_type(intent_tier, mode, memory)

            # ✅ NEW — apply escalation
            offer = self._apply_subscriber_offer_escalation(offer, memory)

            # Always respect subscriber logic
            if offer["offer_type"] != self.OFFER_TYPE_NONE:
                offer["price"] = self.determine_dynamic_price(
                    offer_type=offer["offer_type"],
                    base_price=offer["price"],
                    memory=memory,
                )

            return offer
        
        # Whale protection: no tease offers, premium positioning only
        if is_whale:
            offer = {
                "offer_type": self.OFFER_TYPE_PREMIUM,
                "price": 50,
                "description": "High-value premium offer for whale user",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        # Stronger buyer / closing signals = VIP path
        if (
            intent_tier == "hot"
            or user_value_tier == "buyer"
            or closing_questions >= 1
            or exclusive_interest >= 3
            or prior_intent_score >= 85
            or message_score >= 35
        ):
            offer = {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "VIP exclusive content offer",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        # Medium interest can still justify VIP if the conversation is warm enough
        if (
            intent_tier == "medium"
            and mode in ["tension", "conversion", "flirty"]
            and (exclusive_interest >= 1 or price_questions >= 1 or offers_shown >= 1)
        ):
            offer = {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "Escalated VIP offer",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        # Hard-buy re-entry after a prior offer should jump back to VIP
        if (
            offers_shown >= 1
            and last_offer_type in [self.OFFER_TYPE_VIP, self.OFFER_TYPE_TEASE, self.OFFER_TYPE_PREMIUM, self.OFFER_TYPE_NONE]
            and messages_since_last_offer >= 1
            and mode in ["flirty", "tension", "conversion"]
            and hard_buy_reentry
        ):
            offer = {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "Hard-buy re-entry VIP offer",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        # Re-entry after prior selling activity can escalate from tease to VIP sooner
        if (
            offers_shown >= 1
            and mode in ["flirty", "tension", "conversion"]
            and (exclusive_interest >= 2 or prior_intent_score >= 25)
            and messages_since_last_offer >= 1
            and last_offer_type in [self.OFFER_TYPE_VIP, self.OFFER_TYPE_TEASE, self.OFFER_TYPE_PREMIUM, self.OFFER_TYPE_NONE]
        ):
            offer = {
                "offer_type": self.OFFER_TYPE_VIP,
                "price": 25,
                "description": "Re-entry VIP offer",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        # Lower-level tease path
        if (
            intent_tier in ["low", "medium"]
            and mode in ["flirty", "tension"]
            and user_value_tier in ["cold", "warm"]
        ):
            offer = {
                "offer_type": self.OFFER_TYPE_TEASE,
                "price": 10,
                "description": "Early tease offer",
            }
            offer["price"] = self.determine_dynamic_price(
                offer_type=offer["offer_type"],
                base_price=offer["price"],
                memory=memory,
            )
            return offer

        return {
            "offer_type": self.OFFER_TYPE_NONE,
            "price": 0,
            "description": "No offer",
        }

    def build_offer_copy(self, persona_name: str, offer: dict, memory: dict = None) -> str:
        """
        Build a GPT-facing instruction string that makes the sales copy
        feel different depending on tease/VIP/premium and content tier.
        """
        offer_type = offer.get("offer_type", self.OFFER_TYPE_NONE)
        price = offer.get("price", 0)
        content = offer.get("content") or {}
        content_caption = content.get("caption", "")
        content_tier = (content.get("tier", "") or "").lower()
        content_type = (content.get("type", "") or "").lower()

        if offer_type == self.OFFER_TYPE_NONE:
            return "Do not pitch paid content in this response."

        signals = memory.get("intent_signals", []) if memory else []
        best_request = any(sig in signals for sig in ["best_request", "best_request_after_offer"])
        closing_intent = any(sig in signals for sig in ["closing_intent", "closing_after_offer"])
        exclusive_interest = memory.get("exclusive_interest_count", 0) if memory else 0
        messages_since_last_offer = memory.get("messages_since_last_offer", 0) if memory else 0
        current_route = (memory.get("current_route", "chat") if memory else "chat").strip().lower()

        # ---------- TEASE COPY ----------
        if offer_type == self.OFFER_TYPE_TEASE:
            tease_styles = [
                "playful and tempting",
                "light, flirty, and curiosity-driven",
                "softly seductive and low-pressure",
                "teasing, cheeky, and easy to say yes to",
            ]
            tease_style = random.choice(tease_styles)

            base_instruction = (
                f"You are {persona_name}. Guide the user toward a paid tease offer without stating its price. "
                f"Make it feel {tease_style}. "
                f"This should feel like a preview, a peek, or a little taste—never like the biggest or most intense thing you have. "
                f"Keep it short, seductive, and easy to unlock."
            )

            if current_route == "video_request":
                base_instruction += (
                    " The user has shown video interest, so frame the tease around a lighter video-style preview if possible."
                )

            if closing_intent or best_request:
                base_instruction += (
                    " The user is showing stronger buying curiosity, but still keep this tease smaller than a full VIP escalation."
                )

            if content_tier == "mid":
                base_instruction += (
                    " Make this tease feel a little richer and more tempting than a basic preview, but still not fully elite."
                )
            else:
                base_instruction += (
                    " Keep the tease light and entry-level, focused on building desire."
                )

            if content_caption:
                base_instruction += f" Blend this content vibe in naturally: {content_caption}"

            return base_instruction

        # ---------- VIP COPY ----------
        if offer_type == self.OFFER_TYPE_VIP:
            vip_core = (
                f"You are {persona_name}. Guide the user toward a VIP paid offer without stating its price. "
                f"Make it feel more exclusive, more personal, and more valuable than a tease."
            )

            if current_route == "video_request":
                vip_core += " The user is especially interested in video content, so lean into that angle naturally."

            if content_tier == "low":
                tier_instruction = (
                    " This is low-tier VIP: frame it as more private and more special than a tease, "
                    "but not the absolute strongest or rarest thing available. "
                    "It should feel like a meaningful step up, not the final boss."
                )
            elif content_tier == "mid":
                tier_instruction = (
                    " This is mid-tier VIP: make it feel clearly elevated, more intimate, and harder to access. "
                    "It should sound stronger than entry VIP and worth unlocking for someone who wants more."
                )
            elif content_tier == "high":
                tier_instruction = (
                    " This is high-tier VIP: make it feel intense, highly exclusive, and not something shown to just anyone. "
                    "The user should feel they are getting into much deeper territory."
                )
            elif content_tier == "premium":
                tier_instruction = (
                    " This is premium VIP: make it feel elite, rare, highest-value, and one of the strongest things on the menu. "
                    "It should sound like a top-shelf offer reserved for the boldest buyers."
                )
            else:
                tier_instruction = (
                    " Make this VIP offer feel clearly more exclusive and rewarding than a tease."
                )

            signal_instruction = ""
            if best_request:
                signal_instruction += (
                    " The user is asking for your best or strongest offer, so lean into top-tier value and confidence."
                )
            elif closing_intent:
                signal_instruction += (
                    " The user is close to buying, so make the offer feel decisive, desirable, and easy to say yes to."
                )
            elif exclusive_interest >= 2:
                signal_instruction += (
                    " The user has shown repeated interest in exclusive/private content, so emphasize access and rarity."
                )

            pacing_instruction = ""
            if messages_since_last_offer == 0:
                pacing_instruction = (
                    " Keep the pitch smooth and natural—do not sound repetitive or overly salesy."
                )
            else:
                pacing_instruction = (
                    " This is a re-entry pitch, so make it feel like a stronger continuation of the tension rather than a random new sales push."
                )

            caption_instruction = ""
            if content_caption:
                caption_instruction = f" Blend this content vibe in naturally: {content_caption}"

            return " ".join(
                part for part in [
                    vip_core,
                    tier_instruction,
                    signal_instruction,
                    pacing_instruction,
                    caption_instruction,
                ] if part
            )

        # ---------- PREMIUM COPY ----------
        if offer_type == self.OFFER_TYPE_PREMIUM:
            premium_core = (
                f"You are {persona_name}. Guide the user toward a premium paid offer without stating its price. "
                f"Make it feel elite, rare, highly desirable, and clearly above a normal VIP offer."
            )

            if current_route == "video_request":
                premium_core += (
                    " The user is especially interested in video content, so make this feel like a top-shelf, more exclusive video-style offer."
                )

            if content_tier == "premium":
                tier_instruction = (
                    " This is top-tier premium content: frame it like one of the strongest, rarest, and most exclusive offers available."
                )
            elif content_tier == "high":
                tier_instruction = (
                    " This is high-end premium content: make it feel intense, highly private, and reserved for serious buyers."
                )
            else:
                tier_instruction = (
                    " Make this offer feel clearly above normal VIP and reserved for users who want the best experience."
                )

            signal_instruction = ""
            if best_request:
                signal_instruction += (
                    " The user is explicitly asking for your best content, so confidently position this as a top-shelf premium option."
                )
            elif closing_intent:
                signal_instruction += (
                    " The user is close to buying, so make this feel decisive, luxurious, and worth unlocking right now."
                )
            elif exclusive_interest >= 2:
                signal_instruction += (
                    " The user has shown repeated interest in exclusive/private content, so emphasize rarity, intensity, and access."
                )

            pacing_instruction = ""
            if messages_since_last_offer == 0:
                pacing_instruction = (
                    " Keep the tone smooth and confident—premium, not pushy."
                )
            else:
                pacing_instruction = (
                    " This is a re-entry premium pitch, so make it feel like a stronger, more exclusive continuation of existing tension."
                )

            caption_instruction = ""
            if content_caption:
                caption_instruction = f" Blend this content vibe in naturally: {content_caption}"

            return " ".join(
                part for part in [
                    premium_core,
                    tier_instruction,
                    signal_instruction,
                    pacing_instruction,
                    caption_instruction,
                ] if part
            )

        return "Do not pitch paid content in this response."

    def _is_super_hot(self, memory: dict) -> bool:
        intent_score = memory.get("intent_score", 0) or 0
        closing_questions = memory.get("closing_questions_count", 0) or 0
        exclusive_interest = memory.get("exclusive_interest_count", 0) or 0

        return (
            intent_score >= 90
            or closing_questions >= 4
            or exclusive_interest >= 8
        )

    def _has_reentry_signal(self, memory: dict, offer: dict) -> bool:
        """
        Strong enough signal to resume selling after a pause.
        """
        intent_score = memory.get("intent_score", 0) or 0
        closing_questions = memory.get("closing_questions_count", 0) or 0
        exclusive_interest = memory.get("exclusive_interest_count", 0) or 0
        price_questions = memory.get("price_questions_count", 0) or 0
        conversation_mode = memory.get("conversation_mode", "")

        offer_type = offer.get("offer_type", self.OFFER_TYPE_NONE)

        if offer_type == self.OFFER_TYPE_PREMIUM:
            return (
                intent_score >= 75
                or closing_questions >= 2
                or exclusive_interest >= 3
                or conversation_mode in ["tension", "conversion"]
            )

        if offer_type == self.OFFER_TYPE_VIP:
            return (
                intent_score >= 60
                or closing_questions >= 1
                or exclusive_interest >= 2
                or conversation_mode in ["tension", "conversion"]
            )

        if offer_type == self.OFFER_TYPE_TEASE:
            return (
                intent_score >= 30
                or price_questions >= 1
                or exclusive_interest >= 1
                or conversation_mode in ["flirty", "tension", "conversion"]
            )

        return False

    def is_direct_confirmation(self, user_message: str = "") -> bool:
        lowered_message = (user_message or "").lower().strip()

        confirmation_phrases = [
            "send it",
            "send it over",
            "send it now",
            "send me it",
            "send me the link",
            "send the link",
            "drop the link",
            "give me the link",
            "i want it",
            "i want it now",
            "i'm ready",
            "im ready",
            "take it",
            "i'll take it",
            "ill take it",
            "yes send it",
            "yeah send it",
            "ok send it",
            "okay send it",
            "unlock it",
            "let me see",
            "lemme see",
            "show me more",
            "show me it",
            "show it to me",
            "where is it",
            "where can i find it",
            "how do i get it",
            "can i have the link",
        ]

        return any(phrase in lowered_message for phrase in confirmation_phrases)

    def determine_offer_pressure(self, memory: dict = None) -> str:
        """
        Determine how aggressively we should try to convert this user.
        This does NOT enforce behavior yet — only classifies pressure.
        """

        if not memory:
            return "medium"

        user_value_tier = memory.get("user_value_tier", "cold")
        is_whale = memory.get("is_whale", False)
        intent_score = memory.get("intent_score", 0) or 0
        message_count = memory.get("message_count", 0) or 0

        # Future-ready fields (safe defaults)
        user_type = memory.get("user_type", "follower")  # follower / subscriber
        attention_tier = memory.get("attention_tier", "medium")  # low / medium / high
        value_score = memory.get("value_score", 0) or 0

        # 🐋 Whale = lowest pressure (protect)
        if is_whale or user_value_tier == "whale":
            return "low"

        # 💎 Buyers / high value = reduced pressure
        if user_value_tier in ["buyer", "high"]:
            return "medium"

        # 🧊 Cold / follower users = higher pressure
        if user_value_tier in ["cold", "warm"]:
            if user_type == "follower":
                return "high"

        # 🧠 Very low engagement / likely time-waster
        if message_count >= 10 and intent_score < 20:
            return "max"

        return "medium"

    def should_send_offer(self, memory: dict, offer: dict, user_message: str = "") -> bool:

        print("\n🚦 [SHOULD SEND OFFER CHECK]")
        print("offer_type:", offer.get("offer_type"))
        print("user_value_tier:", user_value_tier)
        print("is_subscriber:", is_subscriber)
        print("subscriber_profile:", subscriber_profile)

        if not offer or offer.get("offer_type") == self.OFFER_TYPE_NONE:
            return False

        current_route = (memory.get("current_route", "chat") or "chat").strip().lower()
        last_offer_timestamp = memory.get("last_offer_timestamp")
        offers_shown_count = memory.get("offers_shown_count", 0) or 0
        message_count = memory.get("message_count", 0) or 0
        consecutive_offers_sent = memory.get("consecutive_offers_sent", 0) or 0
        messages_since_last_offer = memory.get("messages_since_last_offer", 0) or 0
        signals = memory.get("intent_signals", []) or []

        normalized_signals = [s.lower().replace(" ", "_") for s in signals]
        user_value_tier = memory.get("user_value_tier", "cold")
        is_whale = memory.get("is_whale", False)
        is_subscriber = memory.get("is_subscriber", False)
        subscriber_profile = memory.get("subscriber_profile", "none") or "none"

        super_hot = self._is_super_hot(memory)
        reentry_signal = self._has_reentry_signal(memory, offer)

        closing_intent_detected = any(
            sig in normalized_signals
            for sig in [
                "closing_intent",
                "best_request",
                "closing_after_offer",
                "best_request_after_offer",
            ]
        )

        direct_confirmation = self.is_direct_confirmation(user_message)

        strong_buy_signal = (
            memory.get("intent_score", 0) >= 25
            or memory.get("closing_questions_count", 0) >= 1
            or closing_intent_detected
            or any(
                sig in normalized_signals
                for sig in [
                    "want_it",
                    "im_ready",
                    "take_it",
                    "send_it_now",
                    "send_it",
                    "send_request",
                ]
            )
            or direct_confirmation
        )

        print("DEBUG current_route:", current_route)
        print("DEBUG raw signals:", signals)
        print("DEBUG normalized_signals:", normalized_signals)
        print("DEBUG closing_intent_detected:", closing_intent_detected)
        print("DEBUG strong_buy_signal:", strong_buy_signal)
        print("DEBUG messages_since_last_offer:", messages_since_last_offer)
        print("DEBUG direct_confirmation:", direct_confirmation)

        # 🔥 OFFER PRESSURE
        offer_pressure = self.determine_offer_pressure(memory)
        print("🔥 OFFER PRESSURE:", offer_pressure)

        # 🎯 Pressure-based tuning
        min_messages_required = 2
        reentry_messages_required = self.min_messages_for_reentry

        if offer_pressure == "high":
            min_messages_required = 1
            reentry_messages_required = 1

        elif offer_pressure == "max":
            min_messages_required = 0
            reentry_messages_required = 0

        elif offer_pressure == "low":
            min_messages_required = 3
            reentry_messages_required = 3

        # ---------------- ROUTE RULES ----------------

        if current_route == "support":
            print("🛑 OFFER SUPPRESSED — SUPPORT ROUTE")
            return False

        if current_route == "custom_request":
            print("🛑 OFFER SUPPRESSED — CUSTOM REQUEST ROUTE")
            return False

        if current_route == "reconnect" and not direct_confirmation and not closing_intent_detected:
            if messages_since_last_offer < 1:
                print("🛑 OFFER SUPPRESSED — RECONNECT WARM-UP")
                return False
        
        # ---------------- SUBSCRIBER PACING GUARD ----------------

        if is_subscriber:
            if (
                offers_shown_count >= 1
                and messages_since_last_offer < 1
                and not direct_confirmation
                and not closing_intent_detected
            ):
                print("🛑 SUBSCRIBER OFFER SUPPRESSED — NEED CONVERSATION BEFORE NEXT OFFER")
                return False

            if subscriber_profile in ["NEW_SUBSCRIBER", "LAPSED_SUBSCRIBER"]:
                if not direct_confirmation:
                    print("🛑 SUBSCRIBER OFFER SUPPRESSED — PROFILE REQUIRES SOFTER PACING")
                    return False

        # ---------------- WHALE PROTECTION ----------------

        if is_whale:
            if direct_confirmation:
                return True
            if closing_intent_detected and messages_since_last_offer >= 1:
                return True
            return False

        # ---------------- EARLY / FIRST OFFERS ----------------

        if offers_shown_count == 0 and message_count >= 1 and self._is_sales_eligible_route(memory):
            return True

        if user_value_tier == "cold" and messages_since_last_offer >= 1 and self._is_sales_eligible_route(memory):
            return True

        # ---------------- SAFETY GUARDS ----------------

        if offers_shown_count >= 1 and messages_since_last_offer < 1 and not direct_confirmation:
            return False

        if (
            consecutive_offers_sent >= self.hard_pause_after_offers
            and messages_since_last_offer < self.min_messages_after_pause
            and not closing_intent_detected
            and not direct_confirmation
        ):
            return False

        # ---------------- OVERRIDES ----------------

        if direct_confirmation:
            print("🔥 DIRECT BUY SIGNAL DETECTED — OVERRIDING COOLDOWN")
            return True

        if closing_intent_detected and messages_since_last_offer >= 1 and self._is_sales_eligible_route(memory):
            return True

        if strong_buy_signal and messages_since_last_offer >= 1 and self._is_sales_eligible_route(memory):
            return True

        # ---------------- COOLDOWN ----------------

        if last_offer_timestamp:
            try:
                last_sent = datetime.fromisoformat(last_offer_timestamp)
                now = datetime.utcnow()
                minutes_since = (now - last_sent).total_seconds() / 60

                if minutes_since < self.cooldown_minutes:
                    if closing_intent_detected and messages_since_last_offer >= 1:
                        return True
                    if super_hot and messages_since_last_offer >= 1:
                        return True
                    if (
                        reentry_signal
                        and messages_since_last_offer >= reentry_messages_required
                        and self._is_sales_eligible_route(memory)
                    ):
                        return True
                    return False
            except Exception:
                pass

        # ---------------- RE-ENTRY ----------------

        if reentry_signal and messages_since_last_offer >= reentry_messages_required and self._is_sales_eligible_route(memory):
            return True

        # ---------------- FINAL GATE ----------------

        if messages_since_last_offer >= min_messages_required and (reentry_signal or strong_buy_signal) and self._is_sales_eligible_route(memory):
            return True

        return False

    def get_offer_timestamp(self) -> str:
        return datetime.utcnow().isoformat()
