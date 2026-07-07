import logging
import traceback

from app.repositories.delayed_message_queue_repository import (
    fetch_due_delayed_messages,
    mark_delayed_message_processing,
    mark_delayed_message_completed,
    mark_delayed_message_failed,
)

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
    ):
        self.logger = logging.getLogger(__name__)

        self.fanvue_account_id = fanvue_account_id

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    def process_due_messages(
        self,
        fanvue_account_id: int | None = None,
        limit: int = 25,
    ):
        results = []

        active_account_id = (
            fanvue_account_id
            or self.fanvue_account_id
        )

        due_messages = (
            fetch_due_delayed_messages(
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
                mark_delayed_message_processing(
                    queue_id=queue_id,
                    fanvue_account_id=row_account_id,
                )

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

                    mark_delayed_message_failed(
                        queue_id=queue_id,
                        fanvue_account_id=row_account_id,
                        failure_reason=(
                            "Delayed followup blocked "
                            "by automation safety"
                        ),
                    )

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

                mark_delayed_message_completed(
                    queue_id=queue_id,
                    fanvue_account_id=row_account_id,
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

                mark_delayed_message_failed(
                    queue_id=queue_id,
                    fanvue_account_id=row_account_id,
                    failure_reason=str(e),
                )

                results.append({
                    "queue_id": queue_id,
                    "fanvue_account_id": row_account_id,
                    "status": "failed",
                    "error": str(e),
                })

        return results