"""Scheduling and delivery authority for delayed X CTA thread replies."""
from __future__ import annotations
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.repositories.x_thread_cta_job_repository import XThreadCtaJobRepository
from app.repositories.x_link_performance_repository import XLinkPerformanceRepository
from app.providers.social.x_provider import XPublishingProvider
from app.services.x_thread_cta_publisher import XThreadCtaPublisher

CTA_BASE_URL="https://avablackthorne.com/me"

class XThreadCtaQueueService:
    def __init__(self, *, jobs=None, attributions=None, provider=None, deliveries=None,
                 publisher=None, delay_sampler: Callable[[],int]|None=None):
        self.jobs=jobs or XThreadCtaJobRepository(); self.attributions=attributions or XLinkPerformanceRepository(); self.provider=provider or XPublishingProvider(); self.publisher=publisher or XThreadCtaPublisher(provider=self.provider,attributions=self.attributions,deliveries=deliveries); self.delay_sampler=delay_sampler or (lambda: random.SystemRandom().randint(1800,3600))
    def schedule(self, **data) -> dict[str,Any]:
        finder=getattr(self.jobs,"find_by_operation",None)
        if finder:
            existing=finder(creator_profile_id=data["creator_profile_id"],fanvue_account_id=data["fanvue_account_id"],publish_operation_id=data["publish_operation_id"],x_account_name=data["x_account_name"])
            if existing: return existing
        published_at=data["primary_published_at"]
        if isinstance(published_at,str): published_at=datetime.fromisoformat(published_at.replace("Z","+00:00"))
        attribution=self.attributions.get_or_create_attribution(attribution_token=data["attribution_token"],creator_profile_id=data["creator_profile_id"],fanvue_account_id=data["fanvue_account_id"],publish_operation_id=data["publish_operation_id"],social_queue_item_id=data["social_queue_item_id"],generation_image_id=data["generation_image_id"],primary_x_post_id=data["primary_x_post_id"],x_account_name=data["x_account_name"],primary_caption=data["primary_caption"],primary_published_at=published_at)
        delay=int(self.delay_sampler())
        return self.jobs.create_once(**{k:data.get(k) for k in ("creator_profile_id","fanvue_account_id","publish_operation_id","social_queue_item_id","generation_image_id","primary_x_post_id","x_account_name","asset_reference","thumbnail_reference","caption_preview","cta_text")},primary_published_at=published_at,x_link_attribution_id=str(attribution["x_link_attribution_id"]),cta_url=f'{CTA_BASE_URL}?p={attribution["attribution_token"]}',sampled_delay_seconds=delay,scheduled_at=datetime.now(timezone.utc)+timedelta(seconds=delay))
    def deliver_claimed(self, job: dict[str,Any]) -> dict[str,Any]:
        try:
            delivery=self.publisher.publish(creator_profile_id=job["creator_profile_id"],fanvue_account_id=job["fanvue_account_id"],publish_operation_id=job["publish_operation_id"],x_account_name=job["x_account_name"],primary_x_post_id=job["primary_x_post_id"],x_link_attribution_id=str(job["x_link_attribution_id"]),timing="DELAY_30_60",cta_text=job["cta_text"],cta_url=job["cta_url"])
        except Exception as error:
            self.jobs.mark_uncertain(str(job["job_id"]),f"{type(error).__name__}: {error}"); raise
        return self.jobs.mark_posted(str(job["job_id"]),reply_id=str(delivery["resulting_x_reply_id"]),output_url=delivery.get("provider_output_url"))
    def process_one(self, worker_id: str) -> dict[str,Any] | None:
        self.jobs.expire_claims_to_uncertain(); job=self.jobs.claim(worker_id=worker_id)
        return self.deliver_claimed(job) if job else None
    def post_now(self, job_id: str, *, creator_profile_id: int, fanvue_account_id: int, worker_id: str="operator-post-now") -> dict[str,Any]:
        existing=self.jobs.get(job_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        if not existing: raise KeyError("X CTA job not found.")
        job=self.jobs.claim(worker_id=worker_id,job_id=job_id,force=True)
        if not job: raise ValueError(f"X CTA job cannot be posted from state {existing['state']}.")
        return self.deliver_claimed(job)
