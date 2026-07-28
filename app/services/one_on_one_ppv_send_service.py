import uuid
from datetime import datetime

from app.services.conversation_context_builder import (
    ConversationContextBuilder,
)
from app.services.ppv_caption_service import (
    PPVCaptionService,
)
from app.services.payload_builder_service import (
    PayloadBuilderService,
)
from app.services.fanvue_api_service import (
    FanvueAPIService,
)
from app.services.hot_buyer_detection_service import (
    HotBuyerDetectionService,
)
from app.services.buyer_session_service import (
    BuyerSessionService,
)
from app.services.engagement_service import (
    EngagementService,
)
from app.services.content_delivery_guard_service import (
    ContentDeliveryGuardService,
)
from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)
from app.repositories.memory_repository import (
    get_user_memory_row,
    update_memory_fields,
)
from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


class OneOnOnePPVSendService:
    def __init__(
        self,
        fanvue_account_id: int,
    ):
        self.fanvue_account_id = fanvue_account_id

        self.context_builder = ConversationContextBuilder()

        self.caption_service = PPVCaptionService()

        self.payload_builder = PayloadBuilderService()

        self.fanvue_api = FanvueAPIService(
            fanvue_account_id=self.fanvue_account_id,
        )

        self.hot_buyer_service = HotBuyerDetectionService()

        self.buyer_session_service = BuyerSessionService()

        self.engagement_service = EngagementService()

        self.content_guard = ContentDeliveryGuardService()

        self.global_safety = GlobalAutomationSafetyService()

        self.global_execution_guard = (
            GlobalSendExecutionGuardService()
        )

    def send_ppv_to_user(
        self,
        fanvue_account_id: int,
        fanvue_user_uuid: int,
        thread_id: str,
        content_item: dict,
        price: float,
        dry_run: bool = True,
    ) -> dict:
        """
        3E hardened one-on-one PPV send flow.

        Flow:
        PPV Safety Gate
        → Execution Guard
        → User Memory
        → Pricing
        → Context
        → Hot Buyer / Session Logic
        → Content Delivery Guard
        → Payload Builder
        → Dry Run or Fanvue Send
        """

        if fanvue_account_id != self.fanvue_account_id:
            return {
                "success": False,
                "status": "blocked",
                "reason": "fanvue_account_id_mismatch",
                "service_account_id": self.fanvue_account_id,
                "requested_account_id": fanvue_account_id,
            }

        sending_message_uuid = str(uuid.uuid4())

        print("[ONE-ON-ONE PPV SEND START]")
        print(f"user={fanvue_user_uuid}")
        print(f"dry_run={dry_run}")

        # --------------------------------------------------
        # 0. GLOBAL MONETIZATION / PPV SAFETY CHECK
        # --------------------------------------------------

        safety_result = (
            self.global_safety
            .can_send_monetization()
        )

        execution_guard_result = (
            self.global_execution_guard
            .validate_execution(
                execution_type="one_on_one_ppv",
                safety_result=safety_result,
                dry_run=dry_run,
            )
        )

        print("\n[3E.6 PPV EXECUTION GUARD]")
        print("execution_type=one_on_one_ppv")
        print(f"dry_run={dry_run}")
        print(execution_guard_result)

        if execution_guard_result.get("blocked"):
            print(
                "\n[1:1 PPV BLOCKED] "
                f"{execution_guard_result.get('reason')}"
            )

            return {
                "success": False,
                "blocked": True,
                "status": "blocked",
                "reason": execution_guard_result.get("reason"),
                "execution_guard_result": execution_guard_result,
                "safety_result": safety_result,
                "fanvue_user_uuid": fanvue_user_uuid,
                "content_item_id": content_item.get("id"),
            }

        # --------------------------------------------------
        # 1. LOAD USER MEMORY
        # --------------------------------------------------

        memory = get_user_memory_row(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,
        )

        if not memory:
            print("[PPV BLOCKED] no user memory")

            return {
                "success": False,
                "blocked": True,
                "status": "blocked",
                "reason": "no_memory",
                "execution_guard_result": execution_guard_result,
                "safety_result": safety_result,
            }

        print("[BUYER INTEL]")
        print(
            memory.get("user_value_tier"),
            memory.get("is_whale"),
            memory.get("avg_ppv_spend"),
            memory.get("ppv_purchase_count"),
        )

        # --------------------------------------------------
        # 2. SMART PRICING
        # --------------------------------------------------

        adjusted_price = price
        avg_spend = memory.get("avg_ppv_spend") or 0

        if memory.get("user_value_tier") == "low":
            adjusted_price = min(price, 9.99)
        elif memory.get("user_value_tier") == "medium":
            adjusted_price = max(price, avg_spend or price)
        elif memory.get("user_value_tier") == "high":
            adjusted_price = max(
                price,
                avg_spend * 1.2 if avg_spend else price,
            )
        elif memory.get("is_whale"):
            adjusted_price = max(
                price,
                avg_spend * 1.5 if avg_spend else price,
            )

        print(
            f"[PRICE] base={price} → adjusted={adjusted_price}"
        )

        # --------------------------------------------------
        # 3. CONTEXT
        # --------------------------------------------------

        context = self.context_builder.build_context(
            thread_id=thread_id,
            limit=20,
        )

        if not context:
            print("[WARNING] no context → fallback")
            context = [
                {
                    "role": "user",
                    "content": "hey",
                },
                {
                    "role": "assistant",
                    "content": "hey you 😏",
                },
            ]

        # --------------------------------------------------
        # 4. HOT BUYER DETECTION
        # --------------------------------------------------

        hot_result = self.hot_buyer_service.is_hot_buyer(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,
            memory=memory,
        )

        print("[HOT BUYER CHECK]")
        print(hot_result)

        if hot_result.get("is_hot"):
            self.buyer_session_service.start_or_refresh_session(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_uuid,
                memory=memory,
            )

            memory = get_user_memory_row(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_uuid,
            )

        memory = get_user_memory_row(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,
        )

        # --------------------------------------------------
        # 5. SESSION DECISION
        # --------------------------------------------------

        if hot_result.get("is_hot") or memory.get(
            "buyer_session_active"
        ):
            session_decision = (
                self.buyer_session_service
                .decide_next_action(
                    memory
                )
            )

            action = session_decision.get("action")

            print("[SESSION DECISION]")
            print(session_decision)

            if action == "wait":
                print("[SESSION ACTION] WAIT MODE")

                if self.engagement_service.should_send(memory):
                    message = (
                        self.engagement_service
                        .generate_message()
                    )

                    print("[ENGAGEMENT MESSAGE]")
                    print(message)

                    chat_safety_result = (
                        self.global_safety
                        .can_send_chat()
                    )

                    chat_execution_guard_result = (
                        self.global_execution_guard
                        .validate_execution(
                            execution_type="chat_engagement",
                            safety_result=chat_safety_result,
                            dry_run=dry_run,
                        )
                    )

                    if chat_execution_guard_result.get("blocked"):
                        print("[ENGAGEMENT BLOCKED]")
                        print(chat_execution_guard_result)

                        return {
                            "success": False,
                            "blocked": True,
                            "status": "blocked",
                            "reason": (
                                chat_execution_guard_result
                                .get("reason")
                            ),
                            "safety_result": chat_safety_result,
                            "execution_guard_result": (
                                chat_execution_guard_result
                            ),
                            "session_action": action,
                        }

                    if not dry_run:
                        send_result = (
                            self.fanvue_api
                            .send_chat_message(
                                user_uuid=fanvue_user_uuid,
                                payload={
                                    "recipientUserId": (
                                        fanvue_user_uuid
                                    ),
                                    "message": message,
                                },
                            )
                        )
                    else:
                        print("[DRY RUN] engagement not sent")
                        send_result = {
                            "success": True,
                            "status": "dry_run",
                            "sent": False,
                        }

                    update_memory_fields(
                        fanvue_account_id,
                        fanvue_user_uuid,
                        {
                            "last_engagement_at": (
                                datetime.utcnow()
                            ),
                        },
                    )

                    return {
                        "success": True,
                        "status": "engagement_sent",
                        "message": message,
                        "session_action": action,
                        "send_result": send_result,
                        "safety_result": chat_safety_result,
                        "execution_guard_result": (
                            chat_execution_guard_result
                        ),
                    }

                return {
                    "success": True,
                    "status": "skipped",
                    "reason": "waiting_after_ppv",
                    "session_action": action,
                    "safety_result": safety_result,
                    "execution_guard_result": (
                        execution_guard_result
                    ),
                }

            if action == "cooldown":
                print("[SESSION ACTION] COOLDOWN")

                return {
                    "success": True,
                    "status": "skipped",
                    "reason": "cooldown",
                    "session_action": action,
                    "safety_result": safety_result,
                    "execution_guard_result": (
                        execution_guard_result
                    ),
                }

            if action == "send_bridge_message":
                print("[SESSION ACTION] Sending bridge")

                bridge_text = (
                    self.caption_service
                    .generate_context_aware_caption(
                        chat_history=context,
                        content_metadata={
                            "classification": "TEASE",
                            "tier": "bridge",
                            "tags": ["flirty"],
                            "summary": "bridge message",
                        },
                    )
                )

                print("[BRIDGE MESSAGE]")
                print(bridge_text)

                chat_safety_result = (
                    self.global_safety.can_send_chat()
                )

                bridge_execution_guard_result = (
                    self.global_execution_guard
                    .validate_execution(
                        execution_type="chat_bridge",
                        safety_result=chat_safety_result,
                        dry_run=dry_run,
                    )
                )

                if bridge_execution_guard_result.get("blocked"):
                    print("[BRIDGE BLOCKED]")
                    print(bridge_execution_guard_result)

                    return {
                        "success": False,
                        "blocked": True,
                        "status": "blocked",
                        "reason": (
                            bridge_execution_guard_result
                            .get("reason")
                        ),
                        "safety_result": chat_safety_result,
                        "execution_guard_result": (
                            bridge_execution_guard_result
                        ),
                        "session_action": "send_bridge_message",
                    }

                if dry_run:
                    print("[DRY RUN] bridge not sent")

                    self.buyer_session_service.mark_bridge_sent(
                        fanvue_account_id,
                        fanvue_user_uuid,
                    )

                    return {
                        "success": True,
                        "status": "bridge_generated",
                        "message": bridge_text,
                        "session_action": (
                            "send_bridge_message"
                        ),
                        "safety_result": chat_safety_result,
                        "execution_guard_result": (
                            bridge_execution_guard_result
                        ),
                    }

                result = self.fanvue_api.send_chat_message(
                    user_uuid=fanvue_user_uuid,
                    payload={
                        "recipientUserId": fanvue_user_uuid,
                        "message": bridge_text,
                    },
                )

                if result.get("success"):
                    self.buyer_session_service.mark_bridge_sent(
                        fanvue_account_id,
                        fanvue_user_uuid,
                    )

                return {
                    **result,
                    "safety_result": chat_safety_result,
                    "execution_guard_result": (
                        bridge_execution_guard_result
                    ),
                    "session_action": "send_bridge_message",
                }

        # --------------------------------------------------
        # SESSION OFFER TIER ESCALATION
        # --------------------------------------------------

        session_offer = (
            self.buyer_session_service
            .get_session_offer_tier(
                memory
            )
        )

        print("[SESSION OFFER TIER]", session_offer)

        content_item["classification"] = (
            session_offer.get("classification")
        )

        price_multiplier = session_offer.get(
            "price_multiplier",
            1.0,
        )

        adjusted_price = round(
            adjusted_price * price_multiplier,
            2,
        )

        print(
            f"[SESSION PRICE ADJUST] "
            f"multiplier={price_multiplier} "
            f"→ {adjusted_price}"
        )

        content_item["session_tone"] = (
            session_offer.get("caption_tone")
        )

        caption = self.caption_service.generate_context_aware_caption(
            chat_history=context,
            content_metadata=content_item,
        )

        print("[CAPTION]")
        print(caption)

        # --------------------------------------------------
        # 6. CONTENT DELIVERY GUARD
        # --------------------------------------------------

        content_guard_result = (
            self.content_guard
            .can_deliver_content(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_uuid,
                content_record=content_item,
                requested_delivery="chat_ppv",
            )
        )

        if not content_guard_result.get("allowed"):
            print("[ONE-ON-ONE PPV CONTENT BLOCKED]")
            print(content_guard_result)

            return {
                "success": False,
                "blocked": True,
                "status": "blocked",
                "reason": content_guard_result.get("reason"),
                "content_guard_result": content_guard_result,
                "safety_result": safety_result,
                "execution_guard_result": (
                    execution_guard_result
                ),
                "fanvue_user_uuid": fanvue_user_uuid,
                "content_item_id": content_item.get("id"),
            }

        # --------------------------------------------------
        # 7. PAYLOAD
        # --------------------------------------------------

        payload = self.payload_builder.build_paid_ppv_payload(
            fanvue_account_id,
            fanvue_user_uuid,
            content_item,
            caption,
            adjusted_price,
            sending_message_uuid,
        )

        if payload is None:
            return {
                "success": False,
                "blocked": True,
                "status": "blocked",
                "reason": "duplicate",
                "content_guard_result": content_guard_result,
                "safety_result": safety_result,
                "execution_guard_result": (
                    execution_guard_result
                ),
            }

        payload["execution_guard_result"] = (
            execution_guard_result
        )

        # --------------------------------------------------
        # 8. SESSION TRACKING
        # --------------------------------------------------

        if hot_result.get("is_hot") or memory.get(
            "buyer_session_active"
        ):
            current_ppv_count = (
                memory.get("buyer_session_ppv_count", 0)
                or 0
            )

            self.buyer_session_service.mark_ppv_sent(
                fanvue_account_id,
                fanvue_user_uuid,
                current_ppv_count,
            )

            current_step = (
                memory.get("buyer_session_step")
                or 1
            )

            next_step = current_step + 1

            print(
                f"[SESSION STEP] advancing "
                f"{current_step} → {next_step}"
            )

            update_memory_fields(
                fanvue_account_id,
                fanvue_user_uuid,
                {
                    "buyer_session_step": next_step,
                    "buyer_session_last_action": "ppv",
                },
            )

            memory = get_user_memory_row(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_uuid,
            )

            self.buyer_session_service.start_wait_timer(
                fanvue_account_id,
                fanvue_user_uuid,
                memory,
            )

        # --------------------------------------------------
        # 9. SEND
        # --------------------------------------------------

        if dry_run:
            print("[PAYLOAD BUILT - PAID PPV]")
            print("[1:1 DRY RUN] payload ready")

            return {
                "success": True,
                "status": "dry_run",
                "blocked": False,
                "reason": execution_guard_result.get("reason"),
                "payload": payload,
                "execution_guard_result": (
                    execution_guard_result
                ),
                "content_guard_result": (
                    content_guard_result
                ),
                "safety_result": safety_result,
            }

        send_result = self.fanvue_api.send_chat_message(
            user_uuid=fanvue_user_uuid,
            payload=payload,
        )

        return {
            **send_result,
            "execution_guard_result": (
                execution_guard_result
            ),
            "content_guard_result": (
                content_guard_result
            ),
            "safety_result": safety_result,
        }
