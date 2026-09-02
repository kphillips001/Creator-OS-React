from uuid import uuid4

from app.repositories.outreach_queue_repository import claim_due_items, renew_claim, release_claim, complete_claim, fail_claim

from app.services.outreach_service import (
    OutreachService,
)

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)
from app.models.customer_contact import ContactPolicyResult, ContactPurpose
from app.services.customer_contact_authority_service import CustomerContactAuthorityService


class OutreachWorkerService:

    def __init__(self, worker_instance_id: str | None = None,
                 engagement_scheduler=None):

        self.worker_instance_id = worker_instance_id or f"outreach-{uuid4()}"

        self.outreach_service = (
            OutreachService()
        )

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )
        from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
        self.customer_safety_service = CustomerInteractionSafetyService()
        if engagement_scheduler is None:
            from app.repositories.engagement_teaser_policy_repository import EngagementTeaserPolicyRepository
            from app.services.engagement_teaser_policy_service import EngagementTeaserPolicyService
            from app.services.engagement_teaser_reengagement_scheduler import EngagementTeaserReengagementScheduler
            engagement_scheduler = EngagementTeaserReengagementScheduler(
                policy_service=EngagementTeaserPolicyService(
                    repository=EngagementTeaserPolicyRepository()))
        self.engagement_scheduler = engagement_scheduler
        self.contact_authority = CustomerContactAuthorityService()

    def process_outreach_queue(
        self,
        limit: int = 25,
    ) -> dict:

        global_result = self.global_safety_service.check_global_safety()
        if not global_result.get("allowed", False):
            return {
                "success": True, "blocked": True,
                "reason": global_result.get("reason"),
                "processed_count": 0, "failed_count": 0,
                "processed": [], "failed": [],
            }

        if self.engagement_scheduler is not None:
            self.engagement_scheduler.schedule_due(limit=limit)

        queue_items = (
            claim_due_items(worker_instance_id=self.worker_instance_id, limit=limit)
        )

        processed = []
        failed = []

        for item in queue_items:

            queue_id = item["id"]

            # Telegram engagement media requires the authorized Telethon transport.
            # Keep scheduled work pending; never falsely complete it in this Fanvue
            # outreach worker's current dry-run execution boundary.
            if item.get("outreach_type") == "free_engagement_teaser_reengage":
                release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                continue

            try:

                if not renew_claim(queue_id, worker_instance_id=self.worker_instance_id):
                    continue

                customer_safety = self.customer_safety_service.decide_for_customer(
                    fanvue_account_id=int(item["fanvue_account_id"]),
                    fanvue_user_id=int(item["fanvue_user_id"]))
                if not customer_safety.allowed:
                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                    continue

                contact = self.contact_authority.decide(
                    purpose=(ContactPurpose.RE_ENGAGEMENT if str(item.get("outreach_type") or "").lower() in {"reactivation", "reengagement"}
                             else ContactPurpose.OUTREACH),
                    evidence=item,
                )
                if contact.result is not ContactPolicyResult.ALLOW:
                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                    continue

                # ==================================================
                # Outreach Safety Enforcement
                # ==================================================

                safety_result = (
                    self.global_safety_service
                    .can_send_outreach()
                )

                if not safety_result.get(
                    "allowed",
                    False,
                ):
                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                    continue

                # ==================================================
                # Existing outreach execution layer
                # will be wired into live send orchestration later.
                # ==================================================

                result = {
                    "success": True,
                }

                if not result.get(
                    "success",
                    False,
                ):
                    raise Exception(
                        result.get(
                            "reason",
                            "outreach_failed",
                        )
                    )

                completed = (
                    complete_claim(queue_id, worker_instance_id=self.worker_instance_id)
                )

                processed.append(
                    completed
                )

            except Exception as e:

                failed_item = (
                    fail_claim(
                        queue_id=queue_id,
                        worker_instance_id=self.worker_instance_id,
                        error_message=str(e),
                        retry=True,
                    )
                )

                failed.append(
                    failed_item
                )

        return {
            "success": True,
            "processed_count": len(
                processed
            ),
            "failed_count": len(
                failed
            ),
            "processed": processed,
            "failed": failed,
        }
