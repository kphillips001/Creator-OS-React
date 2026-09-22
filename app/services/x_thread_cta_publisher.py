"""Canonical publication boundary for direct and delayed X thread CTAs."""
from __future__ import annotations

from typing import Any

from app.providers.social.x_provider import XPublishingProvider
from app.repositories.x_link_performance_repository import XLinkPerformanceRepository
from app.repositories.x_thread_cta_delivery_repository import XThreadCtaDeliveryRepository


class XThreadCtaPublisher:
    def __init__(self, *, provider=None, attributions=None, deliveries=None):
        self.provider = provider or XPublishingProvider()
        self.attributions = attributions or XLinkPerformanceRepository()
        self.deliveries = deliveries or XThreadCtaDeliveryRepository()

    def publish(self, *, creator_profile_id: int, fanvue_account_id: int,
                publish_operation_id: str, x_account_name: str,
                primary_x_post_id: str, x_link_attribution_id: str,
                timing: str, cta_text: str, cta_url: str) -> dict[str, Any]:
        parent_id = str(primary_x_post_id or "").strip()
        if not parent_id:
            raise ValueError("X Thread CTA requires an authoritative parent X post ID.")
        caption = "\n".join((str(cta_text or "").strip(),
                              str(cta_url or "").strip())).strip()
        if not caption:
            raise ValueError("X Thread CTA content is required.")
        delivery = self.deliveries.claim_once(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            publish_operation_id=publish_operation_id,
            x_account_name=x_account_name,
            primary_x_post_id=parent_id,
            x_link_attribution_id=x_link_attribution_id,
            timing=timing,
            cta_text=str(cta_text or "").strip(),
            cta_url=str(cta_url or "").strip(),
        )
        if delivery["state"] == "POSTED":
            reply_id = str(delivery.get("resulting_x_reply_id") or "").strip()
            if reply_id:
                self.attributions.attach_cta_post(x_link_attribution_id, reply_id)
            return delivery
        if delivery["state"] != "DELIVERING" or not delivery.get("_claim_acquired"):
            raise RuntimeError(f"X CTA delivery cannot continue from state {delivery['state']}.")
        try:
            result = self.provider.publish_reply(
                caption=caption,
                in_reply_to_tweet_id=parent_id,
                account_name=x_account_name,
            )
            reply_id = str(result.provider_post_id or "").strip()
            if not reply_id:
                raise RuntimeError("X CTA provider returned no reply post ID.")
        except Exception as error:
            self.deliveries.mark_uncertain(
                str(delivery["delivery_id"]), f"{type(error).__name__}: {error}"
            )
            raise
        try:
            posted = self.deliveries.mark_posted(
                str(delivery["delivery_id"]), reply_id=reply_id,
                output_url=result.provider_output_url,
            )
        except Exception as error:
            try:
                self.deliveries.mark_uncertain(
                    str(delivery["delivery_id"]),
                    f"POST_PUBLISH_PERSISTENCE_{type(error).__name__}: {error}",
                )
            finally:
                raise
        self.attributions.attach_cta_post(x_link_attribution_id, reply_id)
        return posted
