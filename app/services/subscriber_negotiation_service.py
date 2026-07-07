from app.repositories.memory_repository import update_memory_fields


class SubscriberNegotiationService:
    """
    Subscriber negotiation / price resistance engine.

    19M Phase 10:
    - No hard-coded price resistance phrases.
    - Uses GPT classifier output only.
    """

    # -------------------------
    # Detection
    # -------------------------
    def detect_price_resistance(
        self,
        user_message: str = "",
        classifier_result: dict | None = None,
    ) -> bool:
        """
        GPT-based price resistance detection.
        No keyword fallback.
        """

        classifier_result = classifier_result or {}

        objection_type = classifier_result.get("objection_type")
        user_state = classifier_result.get("user_state")
        recommended_action = classifier_result.get("recommended_action")
        confidence = float(classifier_result.get("confidence", 0.0) or 0.0)

        if confidence < 0.6:
            return False

        return (
            objection_type == "price"
            or user_state == "hesitant"
            or (
                recommended_action == "exit"
                and objection_type in ["price", "hesitation"]
            )
        )

    # -------------------------
    # Core Logic
    # -------------------------
    def get_negotiation_action(
        self,
        user_memory: dict,
        offered_price: int,
        user_message: str = "",
        classifier_result: dict | None = None,
    ) -> dict:
        """
        Decide the next negotiation step.

        Rules:
        - first resistance => value defense
        - second resistance => value add
        - third resistance => controlled discount
        - if discount already used => stop negotiation
        """

        user_memory = user_memory or {}

        price_resistance_count = int(user_memory.get("price_resistance_count", 0) or 0)
        discount_used_flag = bool(user_memory.get("discount_used_flag", False) or False)

        resistance_detected = self.detect_price_resistance(
            user_message=user_message,
            classifier_result=classifier_result,
        )

        if not resistance_detected:
            return {
                "action": "hold_price",
                "reason": "no_price_resistance_detected",
                "offered_price": offered_price,
                "new_price": None,
                "memory_updates": {
                    "last_offer_price": offered_price,
                },
            }

        if discount_used_flag:
            return {
                "action": "stop_negotiation",
                "reason": "discount_already_used",
                "offered_price": offered_price,
                "new_price": None,
                "memory_updates": {
                    "price_resistance_count": price_resistance_count + 1,
                    "last_offer_price": offered_price,
                },
            }

        if price_resistance_count <= 0:
            return {
                "action": "value_defense",
                "reason": "first_price_resistance",
                "offered_price": offered_price,
                "new_price": None,
                "memory_updates": {
                    "price_resistance_count": 1,
                    "last_offer_price": offered_price,
                },
            }

        if price_resistance_count == 1:
            return {
                "action": "value_add",
                "reason": "second_price_resistance",
                "offered_price": offered_price,
                "new_price": None,
                "memory_updates": {
                    "price_resistance_count": 2,
                    "last_offer_price": offered_price,
                },
            }

        discounted_price = max(int(round(offered_price * 0.85)), 5)

        return {
            "action": "discount_reoffer",
            "reason": "third_price_resistance",
            "offered_price": offered_price,
            "new_price": discounted_price,
            "memory_updates": {
                "price_resistance_count": price_resistance_count + 1,
                "discount_used_flag": True,
                "last_offer_price": discounted_price,
            },
        }

    # -------------------------
    # Execution + Persistence
    # -------------------------
    def process_negotiation_turn(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        user_memory: dict,
        offered_price: int,
        user_message: str = "",
        classifier_result: dict | None = None,
    ) -> dict:
        """
        Run negotiation decision logic and persist resulting memory updates.
        """

        print("\n====== NEGOTIATION DEBUG ======")
        print(f"user_id: {fanvue_user_id}")
        print(f"message: {user_message}")
        print(f"offered_price: {offered_price}")
        print(f"classifier_result: {classifier_result}")

        result = self.get_negotiation_action(
            user_memory=user_memory,
            offered_price=offered_price,
            user_message=user_message,
            classifier_result=classifier_result,
        )

        memory_updates = result.get("memory_updates", {})

        print("\nACTION RESULT:")
        print(result)

        if memory_updates:
            print("\nAPPLYING MEMORY UPDATES:")
            print(memory_updates)

            update_memory_fields(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                data=memory_updates,
            )

        print("====== END NEGOTIATION DEBUG ======\n")

        return result