from app.repositories.mass_ppv_campaign_repository import (
    fetch_pending_mass_ppv_queue,
    fetch_retryable_mass_ppv_queue,
    fetch_campaign,
    fetch_mass_ppv_user_for_queue,
    mark_mass_ppv_processing,
    mark_mass_ppv_completed,
    mark_mass_ppv_failed,
    reset_mass_ppv_failed_item,
)

from app.services.mass_ppv_send_service import (
    MassPPVSendService,
)


class MassPPVWorkerService:
    """
    Mass PPV Worker Service

    PURPOSE:
    Executes queued Mass PPV sends safely.

    FLOW:
    pending queue
    -> load campaign
    -> resolve local user ID into Fanvue UUID
    -> build one-user target list
    -> call existing MassPPVSendService
    -> mark completed/failed
    """

    def __init__(self):
        self.send_service = MassPPVSendService()

    def process_pending_queue(
        self,
        limit: int = 25,
    ):
        queue_items = fetch_pending_mass_ppv_queue(
            limit=limit,
        )

        print(
            f"[MASS PPV WORKER] "
            f"pending_items={len(queue_items)}"
        )

        results = []

        for queue_item in queue_items:
            result = self.process_queue_item(
                queue_item=queue_item,
            )

            results.append(result)

        return results
    
    def process_retryable_queue(
        self,
        limit: int = 25,
    ):
        retry_items = (
            fetch_retryable_mass_ppv_queue(
                limit=limit,
            )
        )

        print(
            f"[MASS PPV RETRY WORKER] "
            f"retry_items={len(retry_items)}"
        )

        results = []

        for queue_item in retry_items:
            queue_id = queue_item["id"]

            print(
                f"[MASS PPV RETRY] "
                f"queue_id={queue_id}"
            )

            reset_mass_ppv_failed_item(
                queue_id=queue_id,
            )

            refreshed_queue_item = dict(queue_item)

            refreshed_queue_item["status"] = (
                "pending"
            )

            result = self.process_queue_item(
                queue_item=refreshed_queue_item,
            )

            results.append(result)

        return results
    
    def process_all_available_queue(
        self,
        pending_limit: int = 25,
        retry_limit: int = 10,
    ):
        print(
            "\n[MASS PPV ALL QUEUE PROCESSING]"
        )

        pending_results = (
            self.process_pending_queue(
                limit=pending_limit,
            )
        )

        retry_results = (
            self.process_retryable_queue(
                limit=retry_limit,
            )
        )

        return {
            "success": True,
            "pending_processed": len(
                pending_results
            ),
            "retry_processed": len(
                retry_results
            ),
            "pending_results": pending_results,
            "retry_results": retry_results,
        }

    def process_queue_item(
        self,
        queue_item: dict,
    ):
        queue_id = queue_item["id"]

        try:
            mark_mass_ppv_processing(
                queue_id=queue_id,
            )

            campaign = fetch_campaign(
                campaign_id=queue_item["campaign_id"],
            )

            if not campaign:
                raise Exception("campaign_not_found")

            fanvue_user_id = queue_item["fanvue_user_id"]

            print(
                f"[MASS PPV WORKER] "
                f"queue_id={queue_id} "
                f"user={fanvue_user_id}"
            )

            fanvue_user = fetch_mass_ppv_user_for_queue(
                fanvue_user_id=fanvue_user_id,
            )

            if not fanvue_user:
                raise Exception(
                    f"fanvue_user_not_found:{fanvue_user_id}"
                )

            fanvue_user_uuid = str(
                fanvue_user["fanvue_user_uuid"]
            )

            target = {
                "id": fanvue_user["id"],
                "fanvue_user_id": fanvue_user["id"],
                "fanvue_user_uuid": fanvue_user_uuid,
                "user_uuid": fanvue_user_uuid,
                "uuid": fanvue_user_uuid,
                "username": fanvue_user.get("username"),
                "display_name": fanvue_user.get("display_name"),
                "relationship_status": fanvue_user.get(
                    "relationship_status"
                ),
                "is_follower": fanvue_user.get("is_follower"),
                "is_subscriber": fanvue_user.get(
                    "is_subscriber"
                ),

                # ==================================================
                # IMPORTANT:
                # Some existing MassPPVSendService logic expects
                # nested fanvue_user payload structure.
                # ==================================================
                "fanvue_user": {
                    "id": fanvue_user["id"],
                    "fanvue_user_id": fanvue_user["id"],
                    "fanvue_user_uuid": (
                        fanvue_user_uuid
                    ),
                    "user_uuid": (
                        fanvue_user_uuid
                    ),
                    "uuid": (
                        fanvue_user_uuid
                    ),
                    "username": fanvue_user.get(
                        "username"
                    ),
                    "display_name": fanvue_user.get(
                        "display_name"
                    ),
                    "relationship_status": (
                        fanvue_user.get(
                            "relationship_status"
                        )
                    ),
                    "is_follower": fanvue_user.get(
                        "is_follower"
                    ),
                    "is_subscriber": fanvue_user.get(
                        "is_subscriber"
                    ),
                },

                "memory": {
                    "fanvue_user_id": (
                        fanvue_user["id"]
                    ),
                    "fanvue_user_uuid": (
                        fanvue_user_uuid
                    ),
                    "username": fanvue_user.get(
                        "username"
                    ),
                    "relationship_status": (
                        fanvue_user.get(
                            "relationship_status"
                        )
                    ),
                    "is_follower": fanvue_user.get(
                        "is_follower"
                    ),
                    "is_subscriber": fanvue_user.get(
                        "is_subscriber"
                    ),
                },
            }

            content_item = {
                "id": campaign["content_id"],
            }

            send_result = (
                self.send_service.send_mass_ppv_campaign(
                    fanvue_account_id=campaign[
                        "fanvue_account_id"
                    ],
                    targets=[target],
                    content_item=content_item,
                    caption=campaign["caption"],
                    price=float(campaign["price"]),
                    dry_run=True,
                )
            )

            if send_result.get("success"):
                mark_mass_ppv_completed(
                    queue_id=queue_id,
                    fanvue_message_id=(
                        send_result.get(
                            "message_uuid"
                        )
                        or send_result.get(
                            "fanvue_message_id"
                        )
                    ),
                )

                return {
                    "success": True,
                    "queue_id": queue_id,
                    "status": "completed",
                    "send_result": send_result,
                }

            failure_reason = send_result.get(
                "reason",
                "unknown_send_failure",
            )

            mark_mass_ppv_failed(
                queue_id=queue_id,
                failure_reason=failure_reason,
            )

            return {
                "success": False,
                "queue_id": queue_id,
                "status": "failed",
                "reason": failure_reason,
                "send_result": send_result,
            }

        except Exception as e:
            mark_mass_ppv_failed(
                queue_id=queue_id,
                failure_reason=str(e),
            )

            return {
                "success": False,
                "queue_id": queue_id,
                "status": "exception",
                "reason": str(e),
            }