import random
from datetime import datetime

from app.repositories.ppv_broadcast_repository import log_broadcast_send
from app.services.ppv_targeting_service import PPVTargetingService
from app.services.content_service import ContentService
from app.services.memory_service import MemoryService
from app.services.monetization_profile_service import MonetizationProfileService
from app.services.monetization_priority_service import MonetizationPriorityService


class FollowerMonetizationService:
    """
    Dedicated revenue engine for follower monetization.
    """

    def __init__(self):
        self.targeting_service = PPVTargetingService()
        self.content_service = ContentService()
        self.memory_service = MemoryService()
        self.monetization_profile_service = MonetizationProfileService()
        self.priority_service = MonetizationPriorityService()

    def get_targets(self, fanvue_account_id: int, limit: int = 100):
        return self.targeting_service.get_follower_monetization_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

    def run(self, fanvue_account_id: int, limit: int = 100, dry_run: bool = True):
        targets = self.get_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

        print(f"[FOLLOWER MONETIZATION SERVICE] Target count: {len(targets)}")

        results = {
            "target_count": len(targets),
            "sent_count": 0,
            "skipped_count": 0,
            "targets": [],
        }

        used_content_tags = set()

        for target in targets:
            user_id = target["id"]
            username = target.get("username")
            outreach_status = target.get("outreach_status")
            user_value_tier = target.get("user_value_tier")
            user_id_str = f"{fanvue_account_id}:{user_id}"

            user_memory = self.memory_service.get_or_create_user_memory(user_id_str)

            target_is_subscriber = bool(target.get("is_subscriber", False))
            memory_is_subscriber = bool(user_memory.get("is_subscriber", False))

            target_relationship_status = (target.get("relationship_status") or "").lower()
            memory_relationship_status = (user_memory.get("relationship_status") or "").lower()

            is_subscriber = (
                target_is_subscriber
                or memory_is_subscriber
                or target_relationship_status == "subscriber"
                or memory_relationship_status == "subscriber"
            )

            is_follower = bool(
                target.get("is_follower", False)
                or user_memory.get("is_follower", False)
            )

            user_memory["outreach_status"] = outreach_status
            user_memory["user_value_tier"] = user_value_tier
            user_memory["messages_since_last_offer"] = target.get("messages_since_last_offer")

            # 🔴 8B HARD GUARD: subscribers must never flow into follower monetization
            if is_subscriber:
                print(
                    f"[FOLLOWER MONETIZATION SKIP] subscriber_detected "
                    f"user={user_id} username={username} "
                    f"is_subscriber={is_subscriber} is_follower={is_follower} "
                    f"target_is_subscriber={target_is_subscriber} "
                    f"memory_is_subscriber={memory_is_subscriber} "
                    f"relationship_status={target_relationship_status or memory_relationship_status}"
                )

                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": None,
                        "offer_type": None,
                        "content_tag": None,
                        "status": "skipped_subscriber_detected",
                    }
                )
                continue

            priority_route = self.priority_service.determine_priority_route(
                user_memory=user_memory,
                fanvue_user=target,
            )

            print(
                f"[MONETIZATION ROUTE] user={user_id} username={username} "
                f"selected_route={priority_route} engine=follower_monetization "
                f"is_subscriber={is_subscriber} is_follower={is_follower} "
                f"relationship_status={target.get('relationship_status')} "
                f"offer_state={user_memory.get('offer_state')} "
                f"subscriber_rewarm_required={user_memory.get('subscriber_rewarm_required')}"
            )

            if priority_route != "follower_monetization":
                print(
                    f"[FOLLOWER MONETIZATION SKIP] user={user_id} "
                    f"reason=priority_route_mismatch selected_route={priority_route}"
                )

                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": None,
                        "offer_type": None,
                        "content_tag": None,
                        "status": f"skipped_priority_route_{priority_route}",
                    }
                )
                continue

            monetization_profile = self.monetization_profile_service.get_profile(user_memory)
            print(
                f"[FollowerMonetization] user={user_id} "
                f"username={username} monetization_profile={monetization_profile}"
            )

            content_send_count = user_memory.get("content_send_count", 0)
            last_sent_at = user_memory.get("last_content_sent_at")

            reentry_override = False

            if last_sent_at:
                try:
                    hours_since_last_send = (
                        datetime.utcnow() - last_sent_at
                    ).total_seconds() / 3600

                    if hours_since_last_send >= 24:
                        reentry_override = True
                except Exception:
                    reentry_override = False

            if monetization_profile == "WHALE_EXCLUDED":
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": monetization_profile,
                        "offer_type": None,
                        "content_tag": None,
                        "status": "skipped_whale_excluded",
                    }
                )
                continue

            if content_send_count >= 10:
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": monetization_profile,
                        "offer_type": None,
                        "content_tag": None,
                        "status": "skipped_fatigue_cap",
                    }
                )
                continue

            if monetization_profile == "LOW_PROBABILITY":
                send_probability = 0.50 if content_send_count <= 2 else 0.25 if content_send_count <= 6 else 0.10
            elif monetization_profile == "POTENTIAL_BUYER":
                send_probability = 1.00 if content_send_count <= 2 else 0.70 if content_send_count <= 6 else 0.30
            elif monetization_profile == "ACTIVE_BUYER":
                send_probability = 1.00 if content_send_count <= 2 else 0.85 if content_send_count <= 6 else 0.50
            elif monetization_profile == "HIGH_VALUE":
                send_probability = 0.90 if content_send_count <= 2 else 0.70 if content_send_count <= 6 else 0.40
            else:
                send_probability = 1.00 if content_send_count <= 2 else 0.70 if content_send_count <= 6 else 0.30

            if not reentry_override and random.random() > send_probability:
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": monetization_profile,
                        "offer_type": None,
                        "content_tag": None,
                        "status": "skipped_frequency_control",
                    }
                )
                continue

            if reentry_override:
                print(f"[RE-ENTRY] User {username} bypassed throttling")

            if monetization_profile == "LOW_PROBABILITY":
                offer_type = "teaser_offer"
            elif monetization_profile == "POTENTIAL_BUYER":
                if outreach_status in ["ignored", "exhausted"]:
                    offer_type = "teaser_offer"
                elif user_value_tier in ["mid", "high"]:
                    offer_type = "vip_offer"
                else:
                    offer_type = "teaser_offer"
            elif monetization_profile in ["ACTIVE_BUYER", "HIGH_VALUE"]:
                offer_type = "vip_offer"
            else:
                if outreach_status in ["exhausted", "ignored"]:
                    offer_type = "teaser_offer"
                elif user_value_tier in ["mid", "high"]:
                    offer_type = "vip_offer"
                else:
                    offer_type = "teaser_offer"

            content = self.content_service.get_content(
                offer_type=offer_type,
                persona="ava",
                user_memory=user_memory,
            )

            content_tag = content["tag"] if content else None

            if content_tag and content_tag in used_content_tags:
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": user_id,
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": monetization_profile,
                        "offer_type": offer_type,
                        "content_tag": content_tag,
                        "status": "skipped_duplicate_content",
                    }
                )
                continue

            status = "simulated" if dry_run else "sent"

            if not dry_run:
                log_broadcast_send(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=user_id,
                    content_tag=content_tag,
                    campaign_type="follower_monetization",
                    offer_type=offer_type,
                    status="sent",
                    metadata={
                        "username": username,
                        "outreach_status": outreach_status,
                        "user_value_tier": user_value_tier,
                        "monetization_profile": monetization_profile,
                        "send_probability": send_probability,
                        "offer_type": offer_type,
                        "content_tag": content_tag,
                    },
                )

            results["sent_count"] += 1

            if content_tag:
                used_content_tags.add(content_tag)

            self.memory_service.update_user_memory(
                user_id_str,
                {
                    "content_send_count": content_send_count + 1,
                    "last_content_sent_at": datetime.utcnow(),
                },
            )

            results["targets"].append(
                {
                    "fanvue_user_id": user_id,
                    "username": username,
                    "outreach_status": outreach_status,
                    "user_value_tier": user_value_tier,
                    "monetization_profile": monetization_profile,
                    "send_probability": send_probability,
                    "offer_type": offer_type,
                    "content_tag": content_tag,
                    "status": status,
                }
            )

        return results