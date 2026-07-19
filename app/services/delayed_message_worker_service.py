import logging
import traceback
from uuid import uuid4

from app.repositories.delayed_message_queue_repository import claim_due_items, renew_claim, release_claim, complete_claim, fail_claim

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class DelayedMessageWorkerService:
    """
    Delayed Message Worker Service

    PURPOSE:
    Processes delayed/scheduled follow-up messages safely.

    FLOW:
    delayed_message_queue
    → fetch due messages
    → safety enforcement
    → outbound execution
    → completion/failure lifecycle

    IMPORTANT:
    Live Fanvue sends remain protected behind:
    - global automation switches
    - delayed followup switches
    - dry-run enforcement
    """

    def __init__(
        self,
        fanvue_account_id: int | None = None,
        worker_instance_id: str | None = None,
    ):
        self.logger = logging.getLogger(__name__)

        self.fanvue_account_id = fanvue_account_id
        self.worker_instance_id = worker_instance_id or f"delayed-messages-{uuid4()}"

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    def process_due_messages(
        self,
        fanvue_account_id: int | None = None,
        limit: int = 25,
    ):
        results = []

        global_result = self.global_safety_service.check_global_safety()
        if not global_result.get("allowed", False):
            self.logger.info(
                "[DELAYED WORKER IDLE] autonomous execution blocked: %s",
                global_result.get("reason"),
            )
            return results

        active_account_id = (
            fanvue_account_id
            or self.fanvue_account_id
        )

        due_messages = (
            claim_due_items(
                worker_instance_id=self.worker_instance_id,
                fanvue_account_id=active_account_id,
                limit=limit,
            )
        )

        self.logger.info(
            f"[DELAYED WORKER] "
            f"account_id={active_account_id} "
            f"Found {len(due_messages)} due messages"
        )

        for row in due_messages:
            queue_id = row["id"]
            row_account_id = row.get("fanvue_account_id")

            if not row_account_id:
                results.append({
                    "queue_id": queue_id,
                    "status": "blocked",
                    "reason": "missing_fanvue_account_id",
                })
                continue

            if active_account_id and row_account_id != active_account_id:
                results.append({
                    "queue_id": queue_id,
                    "status": "blocked",
                    "reason": "fanvue_account_id_mismatch",
                    "worker_account_id": active_account_id,
                    "row_account_id": row_account_id,
                })
                continue

            try:
                if not renew_claim(queue_id, worker_instance_id=self.worker_instance_id):
                    continue

                safety_result = (
                    self.global_safety_service
                    .can_send_delayed_followup()
                )

                if not safety_result.get(
                    "allowed",
                    False,
                ):
                    self.logger.warning(
                        f"[DELAYED WORKER BLOCKED] "
                        f"queue_id={queue_id} "
                        f"account_id={row_account_id} "
                        f"reason={safety_result}"
                    )

                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)

                    results.append({
                        "queue_id": queue_id,
                        "fanvue_account_id": row_account_id,
                        "status": "blocked",
                        "reason": safety_result,
                    })

                    continue

                self.logger.info(
                    f"[DELAYED MESSAGE DRY RUN] "
                    f"queue_id={queue_id} "
                    f"account_id={row_account_id} "
                    f"user={row['fanvue_user_id']} "
                    f"message={row['message_body']}"
                )

                """
                IMPORTANT:

                Real Fanvue send intentionally deferred.

                Final live send wiring belongs in:
                SECTION 11 — FINAL LIVE VALIDATION

                Later:
                FanvueAPIService(
                    fanvue_account_id=row_account_id,
                ).send_chat_message(...)
                """

                complete_claim(
                    queue_id=queue_id,
                    worker_instance_id=self.worker_instance_id,
                    fanvue_message_id=(
                        f"dry_run_{queue_id}"
                    ),
                )

                results.append({
                    "queue_id": queue_id,
                    "fanvue_account_id": row_account_id,
                    "status": "completed",
                })

            except Exception as e:
                self.logger.error(
                    f"[DELAYED WORKER ERROR] "
                    f"queue_id={queue_id} "
                    f"account_id={row_account_id} "
                    f"error={e}"
                )

                traceback.print_exc()

                fail_claim(
                    queue_id=queue_id,
                    worker_instance_id=self.worker_instance_id,
                    failure_reason=str(e),
                )

                results.append({
                    "queue_id": queue_id,
                    "fanvue_account_id": row_account_id,
                    "status": "failed",
                    "error": str(e),
                })

        return results
