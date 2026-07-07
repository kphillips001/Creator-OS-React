from app.repositories.memory_repository import (
    get_user_memory_row,
    create_user_memory_row,
    record_subscriber_send,
)
from app.services.subscriber_send_rules_service import SubscriberSendRulesService
from app.services.content_service import ContentService
from app.services.offer_service import OfferService
from app.services.ppv_targeting_service import PPVTargetingService
from app.services.subscriber_negotiation_service import SubscriberNegotiationService
from app.services.subscriber_reentry_service import SubscriberReentryService
from app.services.monetization_priority_service import MonetizationPriorityService


class SubscriberMonetizationService:
    def __init__(self):
        self.rules_service = SubscriberSendRulesService()
        self.content_service = ContentService()
        self.offer_service = OfferService()
        self.targeting_service = PPVTargetingService()
        self.negotiation_service = SubscriberNegotiationService()
        self.reentry_service = SubscriberReentryService()
        self.priority_service = MonetizationPriorityService()

    def _select_subscriber_content(self, user_memory: dict):
        active_persona = user_memory.get("active_persona", "ava")

        selected_content = self.content_service.get_content(
            offer_type="vip_offer",
            persona=active_persona,
            user_memory=user_memory,
        )

        return selected_content

    def _calculate_subscriber_price(
        self,
        user_memory: dict,
        selected_content: dict,
    ):
        base_price = selected_content.get("price", 0)

        final_price = self.offer_service.determine_dynamic_price(
            offer_type="vip_offer",
            base_price=base_price,
            memory=user_memory,
        )

        return base_price, final_price

    def get_targets(
        self,
        fanvue_account_id: int,
        limit: int = 100,
    ):
        return self.targeting_service.get_subscriber_monetization_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

    def run(
        self,
        fanvue_account_id: int,
        limit: int = 100,
    ):
        targets = self.get_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

        print("SUBSCRIBER MONETIZATION TARGETS:", targets)

        results = {
            "target_count": len(targets),
            "processed_count": 0,
            "sent_count": 0,
            "skipped_count": 0,
            "targets": [],
        }

        for target in targets:
            user_id = target["id"]
            username = target.get("username")

            outcome = self.process_subscriber_send(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=user_id,
            )

            results["processed_count"] += 1

            if outcome.get("success"):
                results["sent_count"] += 1
            else:
                results["skipped_count"] += 1

            results["targets"].append(
                {
                    "fanvue_user_id": user_id,
                    "username": username,
                    "status": outcome.get("action"),
                    "reason": outcome.get("reason"),
                    "content_tag": outcome.get("content_tag"),
                    "base_price": outcome.get("base_price"),
                    "final_price": outcome.get("final_price"),
                }
            )

        return results

    def process_price_resistance(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        offered_price: int,
        user_message: str,
    ) -> dict:
        user_memory = get_user_memory_row(fanvue_account_id, fanvue_user_id)

        if not user_memory:
            user_memory = create_user_memory_row(fanvue_account_id, fanvue_user_id)

        print("\n====== SUBSCRIBER NEGOTIATION DEBUG ======")
        print(f"user_id: {fanvue_user_id}")
        print(f"user_message: {user_message}")
        print(f"offered_price: {offered_price}")
        print(f"price_resistance_count(before): {user_memory.get('price_resistance_count')}")
        print(f"discount_used_flag(before): {user_memory.get('discount_used_flag')}")
        print(f"last_offer_price(before): {user_memory.get('last_offer_price')}")

        result = self.negotiation_service.process_negotiation_turn(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            user_memory=user_memory,
            offered_price=offered_price,
            user_message=user_message,
        )

        updated_memory = get_user_memory_row(fanvue_account_id, fanvue_user_id)

        print("\nNEGOTIATION RESULT:")
        print(result)

        print("\nMEMORY AFTER NEGOTIATION:")
        print(f"price_resistance_count(after): {updated_memory.get('price_resistance_count')}")
        print(f"discount_used_flag(after): {updated_memory.get('discount_used_flag')}")
        print(f"last_offer_price(after): {updated_memory.get('last_offer_price')}")
        print("====== END NEGOTIATION DEBUG ======\n")

        action = result.get("action")
        new_price = result.get("new_price")

        simulated_send = None

        if action == "discount_reoffer" and new_price is not None:
            simulated_send = {
                "type": "ppv_resend",
                "price": new_price,
                "note": "Simulated NEW PPV send (Fanvue requires new message)",
            }

            print("\n🔥 DISCOUNT REOFFER TRIGGERED")
            print(f"Would SEND NEW PPV at price: ${new_price}")

        return {
            "success": True,
            "action": action,
            "reason": result.get("reason"),
            "offered_price": result.get("offered_price"),
            "new_price": new_price,
            "memory_updates": result.get("memory_updates"),
            "execution": simulated_send,
        }

    def process_subscriber_send(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> dict:
        print("\n====== SUBSCRIBER SEND DEBUG ======")
        print(f"user_id: {fanvue_user_id}")

        user_memory = get_user_memory_row(fanvue_account_id, fanvue_user_id)

        if not user_memory:
            user_memory = create_user_memory_row(fanvue_account_id, fanvue_user_id)

        print("USER MEMORY SNAPSHOT:")
        print(f"is_subscriber: {user_memory.get('is_subscriber')}")
        print(f"relationship_status: {user_memory.get('relationship_status')}")
        print(f"offer_state: {user_memory.get('offer_state')}")
        print(f"post_offer_nudge_count: {user_memory.get('post_offer_nudge_count')}")
        print(f"subscriber_profile: {user_memory.get('subscriber_profile')}")
        print(f"user_value_tier: {user_memory.get('user_value_tier')}")
        print(f"intent_score: {user_memory.get('intent_score')}")

        memory_is_subscriber = bool(user_memory.get("is_subscriber", False))
        relationship_status = (user_memory.get("relationship_status") or "").lower()

        is_subscriber = (
            memory_is_subscriber
            or relationship_status == "subscriber"
        )

        # 🔴 8C HARD GUARD: non-subscribers must never flow into subscriber monetization
        if not is_subscriber:
            print(
                f"\n[SUBSCRIBER MONETIZATION SKIP] non_subscriber_detected "
                f"user={fanvue_user_id} "
                f"memory_is_subscriber={memory_is_subscriber} "
                f"relationship_status={relationship_status}"
            )
            print("====== END DEBUG ======\n")

            return {
                "success": False,
                "action": "skip",
                "reason": "non_subscriber_detected",
            }

        # 🔴 8D HARD GUARD: active offer / nudge users must not receive new subscriber sends
        if self.priority_service.has_active_offer_or_nudge(user_memory):
            print(
                f"\n[SUBSCRIBER MONETIZATION SKIP] active_offer_or_nudge "
                f"user={fanvue_user_id} "
                f"offer_state={user_memory.get('offer_state')} "
                f"post_offer_nudge_count={user_memory.get('post_offer_nudge_count')}"
            )
            print("====== END DEBUG ======\n")

            return {
                "success": False,
                "action": "skip",
                "reason": "active_offer_or_nudge",
            }

        reentry_result = self.reentry_service.process_reentry(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            user_memory=user_memory,
        )

        print("\nREENTRY CHECK:")
        print(reentry_result)

        if reentry_result.get("rewarm_required"):
            print("\nFINAL ACTION: REWARM ENGAGEMENT")
            print("reason: subscriber_rewarm_required")

            rewarm_message = "hey stranger… where have you been 😏"

            print(f"rewarm_message: {rewarm_message}")
            print("====== END DEBUG ======\n")

            return {
                "success": True,
                "action": "rewarm_engagement",
                "reason": "subscriber_rewarm_required",
                "message_type": "soft_rewarm",
                "message": rewarm_message,
                "reentry_result": reentry_result,
            }

        selected_content = self._select_subscriber_content(user_memory)

        print("\nCONTENT SELECTION:")
        if selected_content:
            print(f"tag: {selected_content.get('tag')}")
            print(f"type: {selected_content.get('type')}")
            print(f"tier: {selected_content.get('tier')}")
            print(f"persona: {selected_content.get('persona')}")
            print(f"base_price: {selected_content.get('price')}")
        else:
            print("No content selected")

        if not selected_content:
            print("\nFINAL ACTION: SKIPPED")
            print("reason: no_content_selected")
            print("====== END DEBUG ======\n")
            return {
                "success": False,
                "action": "skip",
                "reason": "no_content_selected",
            }

        content_tag = selected_content.get("tag")
        base_price, final_price = self._calculate_subscriber_price(
            user_memory=user_memory,
            selected_content=selected_content,
        )

        print("\nPRICING:")
        print(f"base_price: {base_price}")
        print(f"final_price: {final_price}")

        result = self.rules_service.can_send_to_subscriber(
            user_memory=user_memory,
            content_tag=content_tag,
        )

        print("\nELIGIBILITY CHECK:")
        print(f"eligible: {result['eligible']}")
        print(f"reason: {result['reason']}")

        if not result["eligible"]:
            print("\nFINAL ACTION: SKIPPED")
            print(f"content_tag: {content_tag}")
            print("====== END DEBUG ======\n")
            return {
                "success": False,
                "action": "skip",
                "reason": result["reason"],
                "content_tag": content_tag,
                "selected_content": selected_content,
                "base_price": base_price,
                "final_price": final_price,
            }

        updated_memory = record_subscriber_send(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_tag=content_tag,
        )

        print("\nFINAL ACTION: SENT")
        print(f"content_tag: {content_tag}")
        print("====== END DEBUG ======\n")

        return {
            "success": True,
            "action": "recorded_send",
            "reason": "subscriber_send_recorded",
            "content_tag": content_tag,
            "selected_content": selected_content,
            "base_price": base_price,
            "final_price": final_price,
            "memory": updated_memory,
        }