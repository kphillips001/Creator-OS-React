from datetime import datetime, timezone

from app.database import get_db_connection

from app.repositories.mass_ppv_campaign_repository import (
    fetch_pending_campaigns,
    create_mass_ppv_queue_entry,
    update_campaign_status,
    get_campaign_status,
)

from app.services.mass_ppv_targeting_service import (
    MassPPVTargetingService,
)


class MassPPVSchedulerService:
    """
    Mass PPV Scheduler Service

    PURPOSE:
    Turns pending/scheduled Mass PPV campaigns into queue items.

    IMPORTANT:
    This service DOES NOT decide buyer intelligence itself.

    FLOW:
    pending campaign
    -> fetch candidate users
    -> use existing MassPPVTargetingService
    -> create mass_ppv_queue entries
    -> update campaign status
    -> worker processes queue later
    """

    def __init__(self):
        self.targeting_service = MassPPVTargetingService()

    def schedule_pending_campaigns(
        self,
        target_limit: int = 250,
    ):
        campaigns = fetch_pending_campaigns()

        print(
            f"[MASS PPV SCHEDULER] "
            f"pending_campaigns={len(campaigns)}"
        )

        results = []

        for campaign in campaigns:
            if not self._campaign_is_due(campaign):
                print(
                    f"[MASS PPV SCHEDULER SKIP] "
                    f"campaign_id={campaign['id']} "
                    f"reason=not_due"
                )

                results.append(
                    {
                        "success": True,
                        "campaign_id": campaign["id"],
                        "status": "skipped",
                        "reason": "not_due",
                    }
                )

                continue

            result = self.schedule_campaign(
                campaign=campaign,
                target_limit=target_limit,
            )

            results.append(result)

        return results

    def schedule_campaign(
        self,
        campaign: dict,
        target_limit: int = 250,
    ):
        campaign_id = campaign["id"]
        fanvue_account_id = campaign["fanvue_account_id"]
        content_id = campaign["content_id"]

        print(
            f"\n[MASS PPV SCHEDULER START] "
            f"campaign_id={campaign_id}"
        )

        update_campaign_status(
            campaign_id=campaign_id,
            status="scheduling",
        )

        candidates = self._fetch_candidate_targets(
            fanvue_account_id=fanvue_account_id,
            limit=target_limit,
        )

        queued = []
        skipped = []

        for candidate in candidates:
            fanvue_user = candidate["fanvue_user"]
            memory = candidate["memory"]

            eligible, reason = (
                self.targeting_service
                .is_user_eligible_for_mass_ppv(
                    fanvue_user=fanvue_user,
                    memory=memory,
                    content_tag=str(content_id),
                )
            )

            if not eligible:
                skipped.append(
                    {
                        "fanvue_user_id": fanvue_user.get("id"),
                        "username": fanvue_user.get("username"),
                        "reason": reason,
                    }
                )
                continue

            queue_id = create_mass_ppv_queue_entry(
                campaign_id=campaign_id,
                fanvue_user_id=fanvue_user.get("id"),
            )

            queued.append(
                {
                    "queue_id": queue_id,
                    "fanvue_user_id": fanvue_user.get("id"),
                    "username": fanvue_user.get("username"),
                    "reason": reason,
                }
            )

        final_status = (
            "queued"
            if queued
            else "no_eligible_targets"
        )

        update_campaign_status(
            campaign_id=campaign_id,
            status=final_status,
        )

        campaign_status = get_campaign_status(
            campaign_id=campaign_id,
        )

        result = {
            "success": True,
            "campaign_id": campaign_id,
            "status": final_status,
            "candidate_count": len(candidates),
            "queued_count": len(queued),
            "skipped_count": len(skipped),
            "queued": queued,
            "skipped": skipped,
            "campaign_status": campaign_status,
        }

        print("\n[MASS PPV SCHEDULER COMPLETE]")
        print(result)

        return result

    def _fetch_candidate_targets(
        self,
        fanvue_account_id: int,
        limit: int,
    ):
        """
        Fetch broad candidates only.

        Final eligibility is handled by MassPPVTargetingService.
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        fu.id,
                        fu.fanvue_user_uuid,
                        fu.username,
                        fu.display_name,
                        fu.relationship_status,
                        fu.is_follower,
                        fu.is_subscriber,

                        um.fanvue_user_id AS memory_fanvue_user_id,
                        um.user_value_tier,
                        um.buyer_tier,
                        um.is_whale,
                        um.current_route,
                        um.last_route,
                        um.offer_state,
                        um.buyer_session_active,
                        um.subscriber_rewarm_required,
                        um.relationship_status AS memory_relationship_status,
                        um.is_subscriber AS memory_is_subscriber,
                        um.is_follower AS memory_is_follower

                    FROM fanvue_users fu
                    LEFT JOIN user_memory um
                        ON um.fanvue_account_id = fu.fanvue_account_id
                        AND um.fanvue_user_id::text = fu.id::text
                    WHERE fu.fanvue_account_id = %s
                    ORDER BY fu.username ASC
                    LIMIT %s;
                    """,
                    (
                        fanvue_account_id,
                        limit,
                    ),
                )

                rows = cur.fetchall()

        targets = []

        for row in rows:
            fanvue_user_id = row.get("id")

            fanvue_user_uuid = str(
                row.get("fanvue_user_uuid")
            )

            fanvue_user = {
                "id": fanvue_user_id,
                "fanvue_user_id": fanvue_user_id,
                "fanvue_user_uuid": fanvue_user_uuid,
                "username": row.get("username"),
                "display_name": row.get("display_name"),
                "relationship_status": row.get(
                    "relationship_status"
                ),
                "is_follower": row.get("is_follower"),
                "is_subscriber": row.get("is_subscriber"),
            }

            memory = {
                "fanvue_user_id": fanvue_user_id,
                "fanvue_user_uuid": fanvue_user_uuid,
                "username": row.get("username"),
                "relationship_status": (
                    row.get("memory_relationship_status")
                    or row.get("relationship_status")
                ),
                "is_subscriber": (
                    row.get("memory_is_subscriber")
                    or row.get("is_subscriber")
                ),
                "is_follower": (
                    row.get("memory_is_follower")
                    or row.get("is_follower")
                ),
                "user_value_tier": row.get("user_value_tier"),
                "buyer_tier": row.get("buyer_tier"),
                "is_whale": row.get("is_whale"),
                "current_route": row.get("current_route"),
                "last_route": row.get("last_route"),
                "offer_state": row.get("offer_state"),
                "buyer_session_active": row.get(
                    "buyer_session_active"
                ),
                "subscriber_rewarm_required": row.get(
                    "subscriber_rewarm_required"
                ),
            }

            targets.append(
                {
                    "fanvue_user": fanvue_user,
                    "memory": memory,
                }
            )

        return targets

    def _campaign_is_due(
        self,
        campaign: dict,
    ) -> bool:
        scheduled_for = campaign.get("scheduled_for")

        if not scheduled_for:
            return True

        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(
                tzinfo=timezone.utc,
            )

        return scheduled_for <= datetime.now(timezone.utc)