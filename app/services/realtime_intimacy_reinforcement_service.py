from datetime import datetime, timezone


class RealtimeIntimacyReinforcementService:
    """
    3D.10.15I + 3D.11.8

    Realtime intimacy + escalation reinforcement.

    Updates intimacy context from realtime monetization events
    while also reinforcing escalation continuity safely.
    """

    def build_updates_from_event(
        self,
        event_type: str,
        payload: dict,
        existing_memory: dict = None,
    ) -> dict:
        event_type = event_type or ""
        payload = payload or {}
        existing_memory = existing_memory or {}

        now = datetime.now(timezone.utc).isoformat()

        updates = {
            "last_intimacy_reinforced_at": now,
            "last_intimacy_event_type": event_type,
        }

        current_momentum = existing_memory.get(
            "buyer_momentum_score",
            0,
        )

        current_relationship_depth = existing_memory.get(
            "relationship_depth_score",
            0,
        )

        current_engagement_depth = existing_memory.get(
            "engagement_depth_score",
            0,
        )

        current_decay = existing_memory.get(
            "cooldown_decay_level",
            0,
        )

        # --------------------------------------------------
        # PURCHASE / UNLOCK EVENTS
        # --------------------------------------------------

        if event_type in [
            "purchase_created",
            "purchase_received",
            "unlock_confirmed",
            "content_unlocked",
        ]:
            updates.update({
                "spender_confidence": "high",
                "intimacy_tier": "premium",
                "premium_sexting_allowed": True,
                "escalation_priority": "high",
                "runtime_mode": "premium_gate",
                "last_purchase_reinforced_at": now,

                # ------------------------------------------
                # 3D.11.8 — REALTIME ESCALATION REINFORCEMENT
                # ------------------------------------------

                "buyer_momentum_score": (
                    current_momentum + 15
                ),

                "relationship_depth_score": (
                    current_relationship_depth + 10
                ),

                "engagement_depth_score": (
                    current_engagement_depth + 8
                ),

                "recent_escalation_active": True,

                "cooldown_decay_level": max(
                    0,
                    current_decay - 20,
                ),

                "post_purchase_cooldown": True,
            })

        # --------------------------------------------------
        # TIP EVENTS
        # --------------------------------------------------

        elif event_type in [
            "tip_created",
            "tip_received",
        ]:
            updates.update({
                "spender_confidence": "high",
                "intimacy_tier": "hot",
                "escalation_priority": "high",
                "runtime_mode": "premium_gate",
                "last_tip_reinforced_at": now,

                # ------------------------------------------
                # 3D.11.8 — TIP REINFORCEMENT
                # ------------------------------------------

                "buyer_momentum_score": (
                    current_momentum + 8
                ),

                "relationship_depth_score": (
                    current_relationship_depth + 5
                ),

                "recent_escalation_active": True,
            })

        # --------------------------------------------------
        # SUBSCRIPTIONS
        # --------------------------------------------------

        elif event_type in [
            "subscription_created",
            "subscription_renewed",
        ]:
            updates.update({
                "spender_confidence": "medium",
                "intimacy_tier": "warm",
                "escalation_priority": "medium",
                "runtime_mode": "tease_only",
                "last_subscription_reinforced_at": now,
            })

        # --------------------------------------------------
        # FALLBACK
        # --------------------------------------------------

        else:
            updates.update({
                "spender_confidence": "low",
                "escalation_priority": "low",
                "runtime_mode": "safe_chat",
            })

        return updates

    def merge_into_intimacy_context(
        self,
        existing_memory: dict,
        event_type: str,
        payload: dict,
    ) -> dict:
        existing_memory = existing_memory or {}

        current_context = (
            existing_memory.get(
                "intimacy_context",
                {},
            )
            or {}
        )

        updates = self.build_updates_from_event(
            event_type=event_type,
            payload=payload,
            existing_memory=current_context,
        )

        merged_context = {
            **current_context,
            **updates,
        }

        return {
            "intimacy_context": merged_context,
        }