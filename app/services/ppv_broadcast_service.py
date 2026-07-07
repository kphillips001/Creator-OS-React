import random
from datetime import datetime, timezone

from app.repositories.ppv_broadcast_repository import log_broadcast_send
from app.services.ppv_targeting_service import PPVTargetingService
from app.services.content_service import ContentService
from app.services.memory_service import MemoryService
from app.services.monetization_priority_service import MonetizationPriorityService


class PPVBroadcastService:
    def __init__(self):
        self.targeting_service = PPVTargetingService()
        self.content_service = ContentService()
        self.memory_service = MemoryService()
        self.priority_service = MonetizationPriorityService()

    def _get_follower_offer_type(self, target: dict, user_memory: dict) -> str:
        return self.content_service.determine_offer_type(user_memory)

    def _skip_active_offer_or_nudge(
        self,
        user_memory: dict,
        target: dict,
        results: dict,
        source: str,
    ) -> bool:
        if not self.priority_service.has_active_offer_or_nudge(user_memory):
            return False

        print(
            f"[{source} SKIP] active_offer_or_nudge "
            f"user={target['id']} "
            f"offer_state={user_memory.get('offer_state')} "
            f"post_offer_nudge_count={user_memory.get('post_offer_nudge_count')}"
        )

        results["skipped_count"] += 1
        results["targets"].append(
            {
                "fanvue_user_id": target["id"],
                "username": target.get("username"),
                "relationship_status": target.get("relationship_status"),
                "offer_state": user_memory.get("offer_state"),
                "post_offer_nudge_count": user_memory.get("post_offer_nudge_count"),
                "status": "skipped_active_offer_or_nudge",
            }
        )

        return True

    def run_basic_broadcast(
        self,
        fanvue_account_id: int,
        content_tag: str,
        campaign_type: str = "broadcast",
        cooldown_hours: int = 24,
        include_followers: bool = True,
        include_subscribers: bool = True,
        limit: int = 100,
        dry_run: bool = True,
    ):
        targets = self.targeting_service.get_basic_targets(
            fanvue_account_id=fanvue_account_id,
            content_tag=content_tag,
            cooldown_hours=cooldown_hours,
            include_followers=include_followers,
            include_subscribers=include_subscribers,
            limit=limit,
        )

        results = {
            "content_tag": content_tag,
            "campaign_type": campaign_type,
            "dry_run": dry_run,
            "target_count": len(targets),
            "sent_count": 0,
            "skipped_count": 0,
            "targets": [],
        }

        used_content_tags = set()

        for target in targets:
            user_id_str = f"{fanvue_account_id}:{target['id']}"
            user_memory = self.memory_service.get_or_create_user_memory(user_id_str)

            if self._skip_active_offer_or_nudge(
                user_memory=user_memory,
                target=target,
                results=results,
                source="PPV BROADCAST",
            ):
                continue

            content = self.content_service.get_content(
                offer_type="vip_offer",
                persona="ava",
                user_memory=user_memory,
            )

            selected_content_tag = content["tag"] if content else content_tag
            selected_content_type = content.get("type") if content else None
            selected_content_price = content.get("price") if content else None

            if selected_content_tag in used_content_tags:
                alt_content = self.content_service.get_content(
                    offer_type="vip_offer",
                    persona="ava",
                    user_memory=user_memory,
                )

                if alt_content and alt_content["tag"] not in used_content_tags:
                    selected_content_tag = alt_content["tag"]
                    selected_content_type = alt_content.get("type")
                    selected_content_price = alt_content.get("price")

            used_content_tags.add(selected_content_tag)

            target_result = {
                "fanvue_user_id": target["id"],
                "username": target.get("username"),
                "relationship_status": target.get("relationship_status"),
                "content_tag": selected_content_tag,
                "content_type": selected_content_type,
                "price": selected_content_price,
                "status": "simulated" if dry_run else "sent",
            }

            if not dry_run:
                print(
                    f"[PPV BROADCAST] Sending {selected_content_tag} to user {target['id']} "
                    f"(cooldown_hours={cooldown_hours})"
                )

                log_broadcast_send(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=target["id"],
                    content_tag=selected_content_tag,
                    campaign_type=campaign_type,
                    metadata={
                        "username": target.get("username"),
                        "relationship_status": target.get("relationship_status"),
                        "selected_content_tag": selected_content_tag,
                        "content_type": selected_content_type,
                        "price": selected_content_price,
                    },
                )

                current_ppv_sent_count = self.memory_service.get_field(
                    user_id_str,
                    "ppv_sent_count",
                    0,
                ) or 0

                current_content_send_count = self.memory_service.get_field(
                    user_id_str,
                    "content_send_count",
                    0,
                ) or 0

                self.memory_service.update_user_memory(
                    user_id_str,
                    {
                        "ppv_sent_count": current_ppv_sent_count + 1,
                        "content_send_count": current_content_send_count + 1,
                        "last_ppv_sent_at": datetime.now(timezone.utc),
                        "last_content_tag": selected_content_tag,
                        "last_offer_type": "vip_offer",
                        "last_content_sent_at": datetime.now(timezone.utc),
                    },
                )

            results["targets"].append(target_result)
            results["sent_count"] += 1

        return results

    def run_follower_broadcast(
        self,
        fanvue_account_id: int,
        campaign_type: str = "follower_monetization",
        limit: int = 100,
        dry_run: bool = True,
    ):
        targets = self.targeting_service.get_follower_monetization_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

        results = {
            "campaign_type": campaign_type,
            "dry_run": dry_run,
            "target_count": len(targets),
            "sent_count": 0,
            "skipped_count": 0,
            "targets": [],
        }

        used_content_tags = set()

        for target in targets:
            user_id_str = f"{fanvue_account_id}:{target['id']}"
            user_memory = self.memory_service.get_or_create_user_memory(user_id_str)

            user_memory["outreach_status"] = target.get("outreach_status")
            user_memory["user_value_tier"] = target.get("user_value_tier")
            user_memory["messages_since_last_offer"] = target.get("messages_since_last_offer")

            if self._skip_active_offer_or_nudge(
                user_memory=user_memory,
                target=target,
                results=results,
                source="FOLLOWER BROADCAST",
            ):
                continue

            content_send_count = user_memory.get("content_send_count", 0)
            last_sent_at = user_memory.get("last_content_sent_at")

            if last_sent_at and last_sent_at.tzinfo is None:
                last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)

            if content_send_count >= 10:
                allow_reentry = False

                if last_sent_at:
                    time_since_hours = (
                        datetime.now(timezone.utc) - last_sent_at
                    ).total_seconds() / 3600

                    if time_since_hours >= 168:
                        allow_reentry = True

                if not allow_reentry:
                    results["skipped_count"] += 1
                    results["targets"].append(
                        {
                            "fanvue_user_id": target["id"],
                            "username": target.get("username"),
                            "outreach_status": target.get("outreach_status"),
                            "user_value_tier": target.get("user_value_tier"),
                            "content_send_count": content_send_count,
                            "status": "skipped_fatigue_cap",
                        }
                    )
                    continue

            force_send = False
            if last_sent_at:
                time_since_hours = (
                    datetime.now(timezone.utc) - last_sent_at
                ).total_seconds() / 3600
                if time_since_hours >= 24:
                    force_send = True

            send_probability = 1.0

            if not force_send:
                if content_send_count <= 2:
                    send_probability = 1.0
                elif content_send_count <= 6:
                    send_probability = 0.7
                else:
                    send_probability = 0.3

            if random.random() > send_probability:
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": target["id"],
                        "username": target.get("username"),
                        "outreach_status": target.get("outreach_status"),
                        "user_value_tier": target.get("user_value_tier"),
                        "content_send_count": content_send_count,
                        "status": "skipped_frequency_control",
                    }
                )
                continue

            offer_type = self._get_follower_offer_type(target, user_memory)

            content = self.content_service.get_content(
                offer_type=offer_type,
                persona="ava",
                user_memory=user_memory,
            )

            if not content:
                results["skipped_count"] += 1
                results["targets"].append(
                    {
                        "fanvue_user_id": target["id"],
                        "username": target.get("username"),
                        "offer_type": offer_type,
                        "outreach_status": target.get("outreach_status"),
                        "user_value_tier": target.get("user_value_tier"),
                        "status": "skipped_no_content",
                    }
                )
                continue

            selected_content_tag = content["tag"]
            selected_content_type = content.get("type")
            selected_content_price = content.get("price")

            last_content_tag = user_memory.get("last_content_tag")

            if selected_content_tag == last_content_tag:
                alt_content = self.content_service.get_content(
                    offer_type=offer_type,
                    persona="ava",
                    user_memory={
                        **user_memory,
                        "seen_content_tags": (user_memory.get("seen_content_tags") or []) + [last_content_tag],
                    },
                )

                if alt_content:
                    selected_content_tag = alt_content["tag"]
                    selected_content_type = alt_content.get("type")
                    selected_content_price = alt_content.get("price")

            if selected_content_tag in used_content_tags:
                alt_content = self.content_service.get_content(
                    offer_type=offer_type,
                    persona="ava",
                    user_memory=user_memory,
                )

                if alt_content and alt_content["tag"] not in used_content_tags:
                    selected_content_tag = alt_content["tag"]
                    selected_content_type = alt_content.get("type")
                    selected_content_price = alt_content.get("price")

            used_content_tags.add(selected_content_tag)

            target_result = {
                "fanvue_user_id": target["id"],
                "username": target.get("username"),
                "offer_type": offer_type,
                "outreach_status": target.get("outreach_status"),
                "user_value_tier": target.get("user_value_tier"),
                "content_tag": selected_content_tag,
                "content_type": selected_content_type,
                "price": selected_content_price,
                "status": "simulated" if dry_run else "sent",
            }

            if not dry_run:
                print(
                    f"[FOLLOWER PPV] Sending {selected_content_tag} "
                    f"(offer_type={offer_type}) to user {target['id']}"
                )

                log_broadcast_send(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=target["id"],
                    content_tag=selected_content_tag,
                    campaign_type=campaign_type,
                    metadata={
                        "username": target.get("username"),
                        "offer_type": offer_type,
                        "outreach_status": target.get("outreach_status"),
                        "user_value_tier": target.get("user_value_tier"),
                        "selected_content_tag": selected_content_tag,
                        "content_type": selected_content_type,
                        "price": selected_content_price,
                    },
                )

                current_ppv_sent_count = self.memory_service.get_field(
                    user_id_str,
                    "ppv_sent_count",
                    0,
                ) or 0

                current_content_send_count = self.memory_service.get_field(
                    user_id_str,
                    "content_send_count",
                    0,
                ) or 0

                self.memory_service.update_user_memory(
                    user_id_str,
                    {
                        "ppv_sent_count": current_ppv_sent_count + 1,
                        "content_send_count": current_content_send_count + 1,
                        "last_ppv_sent_at": datetime.now(timezone.utc),
                        "last_content_tag": selected_content_tag,
                        "last_offer_type": offer_type,
                        "last_content_sent_at": datetime.now(timezone.utc),
                    },
                )

            results["targets"].append(target_result)
            results["sent_count"] += 1

        return results