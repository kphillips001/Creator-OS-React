"""Authenticated Business Queue API for delayed X CTA jobs."""
from fastapi import APIRouter, HTTPException

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.x_thread_cta_job_repository import XThreadCtaJobRepository
from app.services.x_thread_cta_queue_service import XThreadCtaQueueService

router=APIRouter(prefix="/api/v1/business/queue/x-cta",tags=["business-queue"])

def _scope():
    account_id=int(_current_account_id() or 0)
    profile=get_active_creator_profile(str(account_id)) if account_id else None
    if not account_id or not profile: raise HTTPException(status_code=401,detail="Authenticated creator account required.")
    return int(profile["id"]),account_id
def _view(row):
    def value(item): return item.isoformat() if hasattr(item,"isoformat") else str(item) if item is not None else None
    return {"jobId":str(row["job_id"]),"state":row["state"],"accountName":row["x_account_name"],"primaryXPostId":row["primary_x_post_id"],"primaryPublishedAt":value(row["primary_published_at"]),"assetReference":row.get("asset_reference"),"thumbnailReference":row.get("thumbnail_reference"),"captionPreview":row["caption_preview"],"ctaText":row["cta_text"],"ctaUrl":row["cta_url"],"sampledDelaySeconds":row["sampled_delay_seconds"],"scheduledAt":value(row["scheduled_at"]),"createdAt":value(row["created_at"]),"attemptCount":row["attempt_count"],"resultingXReplyId":row.get("resulting_x_reply_id"),"sentAt":value(row.get("sent_at")),"failureReason":row.get("failure_reason")}
@router.get("")
def list_jobs():
    creator,account=_scope(); repo=XThreadCtaJobRepository()
    return {"upcoming":[_view(r) for r in repo.list(creator_profile_id=creator,fanvue_account_id=account,history=False)],"history":[_view(r) for r in repo.list(creator_profile_id=creator,fanvue_account_id=account,history=True)]}
@router.get("/{job_id}")
def get_job(job_id:str):
    creator,account=_scope(); row=XThreadCtaJobRepository().get(job_id,creator_profile_id=creator,fanvue_account_id=account)
    if not row: raise HTTPException(status_code=404,detail="X CTA job not found.")
    return _view(row)
@router.post("/{job_id}/post-now")
def post_now(job_id:str):
    creator,account=_scope()
    try: return _view(XThreadCtaQueueService().post_now(job_id,creator_profile_id=creator,fanvue_account_id=account))
    except KeyError as error: raise HTTPException(status_code=404,detail=str(error)) from error
    except ValueError as error: raise HTTPException(status_code=409,detail=str(error)) from error
@router.post("/{job_id}/cancel")
def cancel(job_id:str):
    creator,account=_scope(); row=XThreadCtaJobRepository().cancel(job_id,creator_profile_id=creator,fanvue_account_id=account,actor="authenticated-operator")
    if not row: raise HTTPException(status_code=409,detail="Only a scheduled, unsent X CTA job can be canceled.")
    return _view(row)
