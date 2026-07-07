import uuid

from app.services.mass_ppv_targeting_service import (
    MassPPVTargetingService,
)
from app.services.payload_builder_service import (
    PayloadBuilderService,
)
from app.services.fanvue_api_service import (
    FanvueAPIService,
)
from app.services.content_delivery_guard_service import (
    ContentDeliveryGuardService,
)
from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)
from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)
from app.repositories.content_usage_repository import (
    log_content_usage,
)


class MassPPVSendService:
    def __init__(
        self,
        fanvue_account_id: int,
    ):
        self.fanvue_account_id = fanvue_account_id

        self.targeting_service = MassPPVTargetingService()

        self.payload_builder = PayloadBuilderService()

        self.fanvue_api = FanvueAPIService(
            fanvue_account_id=self.fanvue_account_id,
        )

        self.content_guard = ContentDeliveryGuardService()

        self.global_safety = GlobalAutomationSafetyService()

        self.execution_guard = GlobalSendExecutionGuardService()

    def send_mass_ppv_campaign(
        self,
        fanvue_account_id: int,
        targets: list[dict],
        content_item: dict,
        caption: str,
        price: float,
        dry_run: bool = True,
    ) -> dict:
        """
        15H-2 Mass PPV Send Engine.

        3E HARDENED FLOW:

        Target list
        → Campaign-level global safety check
        → Target eligibility check
        → ContentDeliveryGuardService validation
        → Payload Builder
        → GlobalSendExecutionGuardService validation
        → Dry Run or Fanvue Send
        → Usage Logging
        """

        if fanvue_account_id != self.fanvue_account_id:
            return {
                "success": False,
                "status": "blocked",
                "reason": "fanvue_account_id_mismatch",
                "service_account_id": self.fanvue_account_id,
                "requested_account_id": fanvue_account_id,
            }

        campaign_id = str(uuid.uuid4())

        print("\n[MASS PPV CAMPAIGN START]")
        print(f"campaign_id={campaign_id}")
        print(f"target_count={len(targets)}")
        print(f"content_id={content_item.get('id')}")
        print(f"price={price}")
        print(f"dry_run={dry_run}")

        safety_result = self.global_safety.can_send_mass_ppv()

        if not dry_run and not safety_result.get("allowed"):
            print("[MASS PPV CAMPAIGN BLOCKED]")
            print(safety_result)

            return {
                "success": False,
                "blocked": True,
                "status": "blocked",
                "reason": safety_result.get("reason"),
                "safety_result": safety_result,
                "campaign_id": campaign_id,
                "target_count": len(targets),
                "sent_count": 0,
                "dry_run_count": 0,
                "skipped_count": len(targets),
                "failed_count": 0,
                "results": [],
            }

        results = []

        sent_count = 0
        skipped_count = 0
        failed_count = 0
        dry_run_count = 0

        for target in targets:
            fanvue_user = target.get("fanvue_user", {})
            memory = target.get("memory", {})

            user_id = fanvue_user.get("id")
            username = fanvue_user.get("username")
            fanvue_user_uuid = (
                fanvue_user.get("fanvue_user_uuid")
                or fanvue_user.get("uuid")
                or fanvue_user.get("fanvue_uuid")
            )

            print("\n[MASS PPV TARGET]")
            print(f"user_id={user_id}")
            print(f"username={username}")
            print(f"user_uuid={fanvue_user_uuid}")

            if not fanvue_user_uuid:
                print("[MASS PPV SKIP] missing_user_uuid")

                skipped_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "skipped",
                    "reason": "missing_user_uuid",
                })
                continue

            eligible, reason = (
                self.targeting_service
                .is_user_eligible_for_mass_ppv(
                    fanvue_user=fanvue_user,
                    memory=memory,
                )
            )

            if not eligible:
                print(f"[MASS PPV SKIP] {reason}")

                skipped_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "skipped",
                    "reason": reason,
                })
                continue

            content_guard_result = (
                self.content_guard.can_deliver_content(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=user_id,
                    content_record=content_item,
                    requested_delivery="chat_ppv",
                )
            )

            if not content_guard_result.get("allowed"):
                print("[MASS PPV SKIP] content_guard_blocked")
                print(content_guard_result)

                skipped_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "skipped",
                    "reason": content_guard_result.get("reason"),
                    "content_guard_result": content_guard_result,
                    "safety_result": safety_result,
                })
                continue

            sending_message_uuid = str(uuid.uuid4())

            payload = self.payload_builder.build_paid_ppv_payload(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_uuid=fanvue_user_uuid,
                content_item=content_item,
                caption=caption,
                price=price,
                sending_message_uuid=sending_message_uuid,
            )

            if payload is None:
                print("[MASS PPV SKIP] duplicate_content")

                skipped_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "skipped",
                    "reason": "duplicate_content",
                    "content_guard_result": content_guard_result,
                    "safety_result": safety_result,
                })
                continue

            execution_guard_result = (
                self.execution_guard.validate_execution(
                    execution_type="mass_ppv",
                    safety_result=safety_result,
                    content_guard_result=content_guard_result,
                    buyer_state_result=None,
                    dry_run=dry_run,
                )
            )

            if not execution_guard_result.get("allowed"):
                print("[MASS PPV SKIP] execution_guard_blocked")
                print(execution_guard_result)

                skipped_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "skipped",
                    "reason": execution_guard_result.get("reason"),
                    "execution_guard_result": execution_guard_result,
                    "content_guard_result": content_guard_result,
                    "safety_result": safety_result,
                })
                continue

            if dry_run:
                print("[MASS PPV DRY RUN] payload ready, send skipped")

                dry_run_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": True,
                    "status": "dry_run_payload_ready",
                    "reason": reason,
                    "payload": payload,
                    "sending_message_uuid": sending_message_uuid,
                    "execution_guard_result": execution_guard_result,
                    "content_guard_result": content_guard_result,
                    "safety_result": safety_result,
                })
                continue

            send_result = self.fanvue_api.send_chat_message(
                user_uuid=fanvue_user_uuid,
                payload=payload,
            )

            if not send_result.get("success"):
                print("[MASS PPV SEND FAILED]")

                failed_count += 1
                results.append({
                    "user_id": user_id,
                    "username": username,
                    "success": False,
                    "status": "failed",
                    "reason": "fanvue_send_failed",
                    "fanvue_result": send_result,
                    "payload": payload,
                    "sending_message_uuid": sending_message_uuid,
                    "execution_guard_result": execution_guard_result,
                    "content_guard_result": content_guard_result,
                    "safety_result": safety_result,
                })
                continue

            print("[MASS PPV SEND SUCCESS]")

            try:
                log_content_usage(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=user_id,
                    content_item_id=content_item.get("id"),
                    send_source="mass_ppv",
                    fanvue_message_id=send_result.get("message_uuid"),
                    caption_used=caption,
                    price=price,
                    usage_type="send",
                    pipeline="mass_ppv",
                )
            except Exception as e:
                print("[MASS PPV USAGE LOG FAILED]", str(e))

            sent_count += 1
            results.append({
                "user_id": user_id,
                "username": username,
                "success": True,
                "status": "sent",
                "reason": reason,
                "fanvue_result": send_result,
                "payload": payload,
                "sending_message_uuid": sending_message_uuid,
                "execution_guard_result": execution_guard_result,
                "content_guard_result": content_guard_result,
                "safety_result": safety_result,
            })

        summary = {
            "success": True,
            "campaign_id": campaign_id,
            "status": "complete",
            "target_count": len(targets),
            "sent_count": sent_count,
            "dry_run_count": dry_run_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "safety_result": safety_result,
            "results": results,
        }

        print("\n[MASS PPV CAMPAIGN COMPLETE]")
        print(summary)

        return summary