from fastapi import APIRouter,HTTPException,Query
from app.api.background_operations import _context
from app.api.video_studio import _json
from app.services.video_gallery_service import VideoGalleryService

router=APIRouter(prefix="/api/v1/video-gallery",tags=["video-gallery"])

@router.get("")
def list_videos(page:int=Query(1,ge=1),page_size:int=Query(24,ge=1,le=100),sort:str=Query("newest",pattern="^(newest|oldest)$"),provider_id:str|None=None,search:str|None=None):
    creator,_=_context(); items,total=VideoGalleryService().list(creator,page=page,page_size=page_size,sort=sort,provider_id=provider_id,search=search)
    return {"items":_json(items),"page":page,"pageSize":page_size,"total":total,"totalPages":max(1,(total+page_size-1)//page_size)}

@router.get("/{media_id}")
def video_detail(media_id:str):
    creator,_=_context(); item=VideoGalleryService().get(media_id,creator)
    if not item: raise HTTPException(status_code=404,detail="Completed video not found.")
    return _json(item)
