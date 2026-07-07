from datetime import datetime, timezone
import random

from app.repositories.content_repository import (
    get_tease_content_for_user,
    log_content_usage,
)

from app.services.content_caption_service import (
    generate_tease_caption_from_content,
    generate_text_outreach_opener,
)

class OutreachService:
    def __init__(
        self,
        outreach_cooldown_hours: int = 48,
        recent_activity_hours: int = 24,
        max_outreach_attempts: int = 3,
    ):
        self.outreach_cooldown_hours = outreach_cooldown_hours
        self.recent_activity_hours = recent_activity_hours
        self.max_outreach_attempts = max_outreach_attempts

    def is_user_eligible_for_outreach(self, user_memory: dict) -> tuple[bool, str]:
        """
        Determines whether a user is eligible for proactive outreach.

        Returns:
            (is_eligible: bool, reason: str)
        """

        if not user_memory:
            return False, "No user memory found."

        # 9A. Subscriber Outreach Suppression Layer
        # Subscribers should not receive generic cold outreach.
        is_subscriber = user_memory.get("is_subscriber") is True
        relationship_status = (user_memory.get("relationship_status") or "").lower()
        subscriber_profile = (user_memory.get("subscriber_profile") or "").upper()

        if (
            is_subscriber
            or relationship_status == "subscriber"
            or subscriber_profile in ("ACTIVE_SUBSCRIBER", "HIGH_VALUE_SUBSCRIBER")
        ):
            print(
                "[OUTREACH SKIP] subscriber_detected | "
                f"fanvue_user_id={user_memory.get('fanvue_user_id')} | "
                f"username={user_memory.get('username')} | "
                f"relationship_status={relationship_status} | "
                f"subscriber_profile={subscriber_profile}"
            )
            return False, "subscriber_detected"

        outreach_status = (user_memory.get("outreach_status") or "eligible").lower()

        if outreach_status in ("responded", "engaged"):
            return False, "User already responded to outreach."

        if outreach_status == "exhausted":
            return False, "User is exhausted from outreach attempts."

        if user_memory.get("is_whale") is True:
            return False, "User is a whale."

        offer_state = (user_memory.get("offer_state") or "none").lower()
        if offer_state != "none":
            return False, f"User is in active offer flow: {offer_state}"

        post_offer_nudge_count = user_memory.get("post_offer_nudge_count", 0) or 0
        last_nudge_timestamp = user_memory.get("last_nudge_timestamp")
        if post_offer_nudge_count > 0 and last_nudge_timestamp is not None:
            return False, "User is currently in post-offer nudge flow."

        outreach_attempts = user_memory.get("outreach_attempts", 0) or 0
        if outreach_attempts >= self.max_outreach_attempts:
            print(
                "[OUTREACH EXHAUSTED] "
                f"fanvue_user_id={user_memory.get('fanvue_user_id')} | "
                f"username={user_memory.get('username')} | "
                f"outreach_attempts={outreach_attempts} | "
                f"max_attempts={self.max_outreach_attempts}"
            )
            return False, "User reached max outreach attempts."

        last_outreach_at = user_memory.get("last_outreach_at")
        if last_outreach_at is not None:
            adaptive_cooldown = self.get_adaptive_outreach_cooldown_hours(user_memory)

            if self._hours_since(last_outreach_at) < adaptive_cooldown:
                print(
                    "[OUTREACH COOLDOWN] "
                    f"fanvue_user_id={user_memory.get('fanvue_user_id')} | "
                    f"username={user_memory.get('username')} | "
                    f"cooldown_hours={adaptive_cooldown} | "
                    f"outreach_attempts={outreach_attempts} | "
                    f"outreach_ignore_count={user_memory.get('outreach_ignore_count', 0) or 0}"
                )
                return False, f"User is still in outreach cooldown ({adaptive_cooldown}h)."

        last_inbound_at = user_memory.get("last_inbound_at")
        if last_inbound_at is not None:
            if self._hours_since(last_inbound_at) < self.recent_activity_hours:
                return False, "User was recently active."

        if not self._is_valid_outreach_target(user_memory):
            return False, "User is not a valid outreach target."

        return True, "User is eligible for outreach."
    
    
    def is_user_eligible_for_subscriber_contextual_outreach(
        self,
        user_memory: dict
    ) -> tuple[bool, str]:
        """
        Determines whether a subscriber is eligible for soft/contextual outreach.

        This is NOT cold outreach.
        This is subscriber-safe engagement.
        """

        if not user_memory:
            return False, "No user memory found."

        is_subscriber = user_memory.get("is_subscriber") is True
        relationship_status = (user_memory.get("relationship_status") or "").lower()
        subscriber_profile = (user_memory.get("subscriber_profile") or "").upper()

        subscriber_detected = (
            is_subscriber
            or relationship_status == "subscriber"
            or subscriber_profile in (
                "NEW_SUBSCRIBER",
                "ACTIVE_SUBSCRIBER",
                "LAPSED_SUBSCRIBER",
                "HIGH_VALUE_SUBSCRIBER",
            )
        )

        if not subscriber_detected:
            return False, "not_subscriber"

        if user_memory.get("subscriber_rewarm_required") is True:
            return False, "subscriber_rewarm_required"

        if user_memory.get("is_whale") is True:
            return False, "whale_protection"

        offer_state = (user_memory.get("offer_state") or "none").lower()
        if offer_state != "none":
            return False, f"active_offer_flow:{offer_state}"

        post_offer_nudge_count = user_memory.get("post_offer_nudge_count", 0) or 0
        last_nudge_timestamp = user_memory.get("last_nudge_timestamp")
        if post_offer_nudge_count > 0 and last_nudge_timestamp is not None:
            return False, "post_offer_nudge_flow"

        last_inbound_at = user_memory.get("last_inbound_at")
        if last_inbound_at is not None:
            if self._hours_since(last_inbound_at) < self.recent_activity_hours:
                return False, "subscriber_recently_active"

        last_outreach_at = user_memory.get("last_outreach_at")
        if last_outreach_at is not None:
            if self._hours_since(last_outreach_at) < self.outreach_cooldown_hours:
                return False, "subscriber_contextual_outreach_cooldown"

        print(
            "[OUTREACH MODE] subscriber_contextual | "
            f"fanvue_user_id={user_memory.get('fanvue_user_id')} | "
            f"username={user_memory.get('username')} | "
            f"subscriber_profile={subscriber_profile}"
        )

        return True, "subscriber_contextual_outreach_eligible"
    
    def generate_subscriber_contextual_opener(self, user_memory: dict) -> str:
        """
        Generates a subscriber-safe contextual outreach opener.

        This should feel like a relationship-based check-in,
        not cold outreach and not a sales message.
        """

        subscriber_profile = (user_memory.get("subscriber_profile") or "").upper()

        if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            return "You’ve been a little quiet… I was starting to wonder where you disappeared to."

        if subscriber_profile == "LAPSED_SUBSCRIBER":
            return "I feel like you vanished on me a little… what have you been up to?"

        if subscriber_profile == "NEW_SUBSCRIBER":
            return "I was wondering when you were going to come say hi properly."

        return "You’ve been a little quiet lately… what are you up to?"
    
    
    def calculate_outreach_priority_score(self, user_memory: dict) -> tuple[int, list[str]]:
        """
        Calculates outreach priority for follower/cold-user outreach.

        Higher score = better outreach target.
        Used for 9C targeting refinement.
        """

        score = 0
        reasons = []

        outreach_status = (user_memory.get("outreach_status") or "eligible").lower()
        user_type = (user_memory.get("user_type") or "").lower()
        relationship_status = (user_memory.get("relationship_status") or "").lower()
        user_value_tier = (user_memory.get("user_value_tier") or "cold").lower()

        outreach_attempts = user_memory.get("outreach_attempts", 0) or 0
        outreach_ignore_count = user_memory.get("outreach_ignore_count", 0) or 0
        outreach_response_count = user_memory.get("outreach_response_count", 0) or 0

        last_outreach_at = user_memory.get("last_outreach_at")
        last_inbound_at = user_memory.get("last_inbound_at")
        last_content_sent_at = user_memory.get("last_content_sent_at")

        # Prioritize follower / cold users
        if user_type == "follower" or relationship_status == "follower":
            score += 30
            reasons.append("follower_target")

        if user_value_tier in ("cold", "low"):
            score += 25
            reasons.append("low_value_or_cold")

        # Prioritize users who ignored outreach before,
        # but do not over-prioritize heavy ignores.
        if outreach_ignore_count == 1:
            score += 15
            reasons.append("single_ignore_retry_candidate")
        elif outreach_ignore_count == 2:
            score += 5
            reasons.append("second_ignore_lower_priority")
        elif outreach_ignore_count >= 3:
            score -= 30
            reasons.append("too_many_ignores")

        # Fresh untouched users are good targets
        if outreach_attempts == 0:
            score += 20
            reasons.append("fresh_outreach_target")

        # Users who responded before should not be cold-outreached aggressively
        if outreach_response_count > 0:
            score -= 25
            reasons.append("already_responded_before")

        # Recently active users should be lower priority
        if last_inbound_at is not None:
            score -= 20
            reasons.append("recent_or_prior_inbound_activity")

        # Recently monetized users should be lower priority
        if last_content_sent_at is not None:
            score -= 20
            reasons.append("recent_content_send_detected")

        # Recently outreached users should be lower priority
        if last_outreach_at is not None:
            score -= 10
            reasons.append("prior_outreach_detected")

        return score, reasons
    
    def get_adaptive_outreach_cooldown_hours(self, user_memory: dict) -> int:
        """
        Returns adaptive cooldown hours based on outreach attempts and ignores.

        More ignores / attempts = longer delay before next outreach.
        """

        outreach_attempts = user_memory.get("outreach_attempts", 0) or 0
        outreach_ignore_count = user_memory.get("outreach_ignore_count", 0) or 0

        pressure_count = max(outreach_attempts, outreach_ignore_count)

        if pressure_count <= 0:
            return self.outreach_cooldown_hours

        if pressure_count == 1:
            return max(self.outreach_cooldown_hours, 12)

        if pressure_count == 2:
            return max(self.outreach_cooldown_hours, 24)

        return max(self.outreach_cooldown_hours, 48)
    
    def evaluate_user_value_upgrade(self, user_memory: dict) -> tuple[str | None, list[str]]:
        """
        Determines if a user should be upgraded in value tier
        based on engagement behavior.

        Returns:
            (new_value_tier, reasons)
        """

        current_tier = (user_memory.get("user_value_tier") or "cold").lower()

        inbound_count = user_memory.get("inbound_message_count", 0) or 0
        response_count = user_memory.get("outreach_response_count", 0) or 0

        reasons = []
        new_tier = None

        # Cold → Low
        if current_tier == "cold" and (inbound_count >= 1 or response_count >= 1):
            new_tier = "low"
            reasons.append("initial_engagement_detected")

        # Low → Medium
        elif current_tier == "low" and (inbound_count >= 3 or response_count >= 2):
            new_tier = "medium"
            reasons.append("repeat_engagement_detected")

        # Medium → High
        elif current_tier == "medium" and inbound_count >= 6:
            new_tier = "high"
            reasons.append("strong_engagement_detected")

        return new_tier, reasons

    def evaluate_outreach_candidate(self, user_memory: dict) -> dict:
        """
        Returns a structured outreach decision for one user.
        """

        if not user_memory:
            return {
                "eligible": False,
                "reason": "No user memory found.",
                "recommended_status": "ineligible",
                "user_type": "unknown",
                "user_value_tier": "unknown",
                "attention_tier": "unknown",
            }

        eligible, reason = self.is_user_eligible_for_outreach(user_memory)

        user_type = (user_memory.get("user_type") or "unknown").lower()
        user_value_tier = (user_memory.get("user_value_tier") or "cold").lower()
        attention_tier = (user_memory.get("attention_tier") or "medium").lower()

        if eligible:
            recommended_status = "eligible"
        else:
            recommended_status = self._derive_recommended_status(reason)

        return {
            "eligible": eligible,
            "reason": reason,
            "recommended_status": recommended_status,
            "user_type": user_type,
            "user_value_tier": user_value_tier,
            "attention_tier": attention_tier,
        }

    def should_attempt_outreach(self, user_memory: dict) -> bool:
        """
        Lightweight yes/no wrapper for outreach execution.
        """
        decision = self.evaluate_outreach_candidate(user_memory)
        return decision["eligible"]

    def filter_eligible_outreach_targets(self, user_memories: list[dict]) -> list[dict]:
        """
        Returns only the users eligible for outreach.
        Each returned item includes the original user_memory plus decision metadata.
        """
        eligible_users = []

        for user_memory in user_memories:
            decision = self.evaluate_outreach_candidate(user_memory)

            if decision["eligible"]:
                enriched_user = {
                    **user_memory,
                    "outreach_decision": decision,
                }
                eligible_users.append(enriched_user)

        return eligible_users

    def evaluate_outreach_batch(self, user_memories: list[dict]) -> dict:
        """
        Evaluates a batch of users and returns both eligible and ineligible groups.
        """
        eligible = []
        ineligible = []

        for user_memory in user_memories:
            decision = self.evaluate_outreach_candidate(user_memory)

            enriched_user = {
                **user_memory,
                "outreach_decision": decision,
            }

            if decision["eligible"]:
                eligible.append(enriched_user)
            else:
                ineligible.append(enriched_user)

        return {
            "eligible": eligible,
            "ineligible": ineligible,
            "summary": {
                "total": len(user_memories),
                "eligible_count": len(eligible),
                "ineligible_count": len(ineligible),
            },
        }

    def get_outreach_opener(self, user_memory: dict) -> dict:
        """
        Returns outreach message payload.
        Can be:
        - text only
        - tease image + caption
        """

        fanvue_account_id = user_memory.get("fanvue_account_id")
        fanvue_user_id = user_memory.get("fanvue_user_id")

        use_tease = random.random() < 0.3  # 30%

        # ---------- TEASE MODE ----------
        if use_tease:
            tease_content = get_tease_content_for_user(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )

            if tease_content:
                print("[OUTREACH MODE] TEASE CONTENT")

                caption = generate_tease_caption_from_content(
                    content=tease_content,
                    user_memory=user_memory,
                )

                from app.repositories.content_repository import log_content_usage

                log_content_usage(
                    content_item_id=tease_content["id"],
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=fanvue_user_id,
                    usage_type="outreach_tease",
                    pipeline="outreach",
                    classification="TEASE",
                    message_text=caption,
                    price=0,
                    metadata={"source": "outreach_tease"},
                )

                return {
                    "type": "tease",
                    "message": caption,
                    "content": tease_content,
                }

            print("[OUTREACH MODE] TEASE FALLBACK → TEXT")

        # ---------- TEXT MODE ----------
        print("[OUTREACH MODE] TEXT ONLY")

        user_type = (user_memory.get("user_type") or "unknown").lower()
        attention_tier = (user_memory.get("attention_tier") or "medium").lower()
        outreach_attempts = user_memory.get("outreach_attempts", 0) or 0

        if outreach_attempts == 0:
            if user_type == "follower":
                message = "hey, how’s your day going?"
            elif attention_tier == "low":
                message = "hey 🙂 what are you up to today?"
            else:
                message = "hey, how’s your day going?"

        elif outreach_attempts == 1:
            if attention_tier == "low":
                message = "hey, how’s your week going so far?"
            else:
                message = "hey, what are you up to tonight?"

        else:
            message = "hey stranger 🙂 how’ve you been?"

        # ---------- TEXT MODE ----------
        print("[OUTREACH MODE] TEXT ONLY")

        message = generate_text_outreach_opener(user_memory)

        return {
            "type": "text",
            "message": message,
            "content": None,
        }

    def build_outreach_preview(self, user_memory: dict) -> dict:
        """
        Builds a safe outreach preview for a single user.
        Does not send anything.
        """

        decision = self.evaluate_outreach_candidate(user_memory)

        preview = {
            "eligible": decision["eligible"],
            "reason": decision["reason"],
            "recommended_status": decision["recommended_status"],
            "user_type": decision["user_type"],
            "user_value_tier": decision["user_value_tier"],
            "attention_tier": decision["attention_tier"],
            "suggested_opener": None,
        }

        if decision["eligible"]:
            outreach_payload = self.get_outreach_opener(user_memory)

            preview["suggested_opener"] = outreach_payload.get("message")
            preview["outreach_payload"] = outreach_payload
            preview["outreach_mode"] = outreach_payload.get("type")
            preview["selected_content"] = outreach_payload.get("content")

        return preview
    
    def generate_tease_caption(self, tease_content: dict) -> str:
        """
        Generates a lightweight dynamic caption from TEASE content metadata.
        This is simple for now. Later we can upgrade this to GPT-generated captions.
        """

        tags = tease_content.get("suggested_tags") or []
        themes = tease_content.get("detected_themes") or []

        # Defensive handling in case JSONB comes back as a string
        if isinstance(tags, str):
            tags = [tags]

        if isinstance(themes, str):
            themes = [themes]

        combined = [str(item).lower() for item in tags + themes]

        if any("cleavage" in item for item in combined):
            return "be honest… would this get your attention? 👀"

        if any("lingerie" in item for item in combined):
            return "I wasn’t going to send this… but I changed my mind 😏"

        if any("jeans" in item or "crop top" in item for item in combined):
            return "this outfit feels dangerously casual… what do you think? 👀"

        if any("posing" in item or "model" in item for item in combined):
            return "I need an honest opinion… is this a good look on me?"

        return "what are you doing… I feel like you’d like this 👀"

    def _derive_recommended_status(self, reason: str) -> str:
        """
        Converts ineligibility reason into a simple outreach status.
        """

        reason = (reason or "").lower()

        if "exhausted" in reason:
            return "exhausted"

        if "cooldown" in reason:
            return "cooldown"

        if "recently active" in reason:
            return "recently_active"

        if "whale" in reason:
            return "excluded"

        if "nudge flow" in reason or "offer flow" in reason:
            return "busy"

        if "max outreach attempts" in reason:
            return "exhausted"

        if "not a valid outreach target" in reason:
            return "ineligible"

        return "ineligible"

    def _is_valid_outreach_target(self, user_memory: dict) -> bool:
        """
        Initial Outreach Engine targeting rules:
        - followers are eligible
        - low-value / cold users are eligible
        - low-value subscribers are eligible
        - whales are excluded earlier
        """

        user_type = (user_memory.get("user_type") or "unknown").lower()
        user_value_tier = (user_memory.get("user_value_tier") or "cold").lower()
        attention_tier = (user_memory.get("attention_tier") or "medium").lower()
        silent_buyer_tier = (user_memory.get("silent_buyer_tier") or "none").lower()

        if user_type == "follower":
            return True

        if user_type == "subscriber" and user_value_tier in {"cold", "low"}:
            return True

        if user_value_tier in {"cold", "low"}:
            return True

        if attention_tier in {"low", "medium"} and silent_buyer_tier in {"none", "low"}:
            return True

        return False

    def _hours_since(self, dt_value) -> float:
        """
        Safely calculate hours since a datetime value.
        Supports timezone-aware datetimes from PostgreSQL.
        """
        now = datetime.now(timezone.utc)

        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)

        delta = now - dt_value
        return delta.total_seconds() / 3600.0
    
    def handle_outreach_response(self, user_memory: dict) -> dict:
        """
        Handles a user response after outreach.

        Outreach handoff behavior:
        - Marks user as responded / engaged
        - Increments response count
        - Stops future cold outreach
        - Allows DecisionEngine / chat flow to take over
        """

        current_response_count = user_memory.get("outreach_response_count", 0) or 0

        updated_fields = {
            "outreach_status": "engaged",
            "outreach_response_count": current_response_count + 1,
            "last_outreach_response_at": "NOW()",
            "current_route": "chat",
            "last_route": "outreach",
        }

        print(
            "[OUTREACH HANDOFF] "
            f"user={user_memory.get('fanvue_user_id')} "
            f"username={user_memory.get('username')} "
            "status=engaged route=chat"
        )

        return updated_fields
    
    def should_trigger_outreach_handoff(self, user_memory: dict) -> bool:
        """
        Determines if an inbound message should trigger outreach → chat handoff.
        More resilient to missing or partial memory.
        """

        outreach_status = (user_memory.get("outreach_status") or "").lower()
        last_route = (user_memory.get("last_route") or "").lower()

        # Trigger if user was recently in outreach flow
        if outreach_status in ("sent", "eligible") or last_route == "outreach":
            return True

        return False