"""Backend-only Video Studio orchestration API."""
from dataclasses import asdict
from fastapi import APIRouter,Header,HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse,Response
from pathlib import Path
from pydantic import BaseModel,Field
from app.api.background_operations import _context
from app.models.video_studio import VideoProviderCapabilityService
from app.services.video_studio_service import VideoStudioService
from app.services.generated_media_service import GeneratedMediaService

router=APIRouter(prefix="/api/v1/video-studio",tags=["video-studio"])

def _raise_video_error(error: Exception, stage: str):
    try:
        from psycopg.errors import UndefinedTable
        if isinstance(error,UndefinedTable):
            raise HTTPException(status_code=503,detail="Video Studio database schema is unavailable. Apply the required Video Studio migrations.") from error
    except ImportError: pass
    message=str(error)
    if isinstance(error,KeyError) and "GROK_API_KEY" in message:
        raise HTTPException(status_code=503,detail="Video Studio creative intelligence is not configured.") from error
    if stage=="source" and isinstance(error,(KeyError,ValueError,FileNotFoundError)):
        raise HTTPException(status_code=422,detail=message or "The selected source could not be resolved.") from error
    if stage in {"analysis","concepts"} and isinstance(error,(ValueError,RuntimeError,FileNotFoundError)):
        raise HTTPException(status_code=502,detail=f"Creator_OS could not complete {stage}. The source and session were preserved for retry.") from error
    raise error

class Settings(BaseModel):
    desired_runtime:int=Field(ge=4,le=3600); aspect_ratio:str="9:16"; resolution:str="720p"; generate_audio:bool=True; video_provider:str="wavespeed_seedance_2_0"
class CreateSession(BaseModel):
    source_type:str; source_id:str; settings:Settings; parent_session_id:str|None=None; parent_video_id:str|None=None
class SettingsPatch(BaseModel):
    desired_runtime:int|None=Field(None,ge=4,le=3600); aspect_ratio:str|None=None; resolution:str|None=None; generate_audio:bool|None=None; video_provider:str|None=None
class Guidance(BaseModel): idea:str=Field(min_length=1,max_length=4000)

def _service_session(session_id):
    creator_id,_=_context(); service=VideoStudioService(); session=service.repository.get_session(session_id,creator_id)
    if not session: raise KeyError("Video Studio session not found.")
    return service,session
def _json(value):
    from datetime import date,datetime
    from uuid import UUID
    if isinstance(value,dict): return {k:_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json(v) for v in value]
    if isinstance(value,(datetime,date)): return value.isoformat()
    if isinstance(value,UUID): return str(value)
    return value

@router.get("/providers")
def providers(): return {"providers":[_json(asdict(v)) for v in VideoProviderCapabilityService().list()]}
@router.post("/sessions")
def create_session(body:CreateSession):
    creator,account=_context()
    try: return _json(VideoStudioService().create(creator_profile_id=creator,account_id=account,source_type=body.source_type,source_id=body.source_id,settings=body.settings.model_dump(),parent_session_id=body.parent_session_id,parent_video_id=body.parent_video_id))
    except Exception as error: _raise_video_error(error,"source")
@router.get("/sessions")
def list_sessions():
    creator,account=_context(); service=VideoStudioService()
    try: return {"sessions":_json(service.repository.list_sessions(creator,account))}
    except Exception as error: _raise_video_error(error,"sessions")
@router.get("/sessions/{session_id}")
def get_session(session_id:str):
    try: _,session=_service_session(session_id); return _json(session)
    except KeyError as error: return JSONResponse(status_code=404,content={"error":str(error)})
@router.patch("/sessions/{session_id}/settings")
def patch_settings(session_id:str,body:SettingsPatch): service,session=_service_session(session_id); return _json(service.update_settings(session,body.model_dump(exclude_none=True)))
@router.post("/sessions/{session_id}/analysis")
def analyze(session_id:str):
    service,session=_service_session(session_id)
    try: return {"visualSceneIntelligence":_json(service.analyze(session))}
    except Exception as error: _raise_video_error(error,"analysis")
@router.post("/sessions/{session_id}/concepts")
def concepts(session_id:str):
    service,session=_service_session(session_id)
    try: return {"concepts":_json(service.concepts(session))}
    except Exception as error: _raise_video_error(error,"concepts")
@router.post("/sessions/{session_id}/concepts/guided")
def guided(session_id:str,body:Guidance):
    service,session=_service_session(session_id)
    try: return {"concepts":_json(service.concepts(session,body.idea))}
    except Exception as error: _raise_video_error(error,"concepts")
@router.post("/sessions/{session_id}/concepts/{concept_id}/select")
def select(session_id:str,concept_id:str): service,session=_service_session(session_id); return _json(service.select(session,concept_id))
@router.post("/sessions/{session_id}/plan")
def plan(session_id:str): service,session=_service_session(session_id); return {"plan":_json(service.plan(session))}
@router.post("/sessions/{session_id}/generation-runs")
def generate(session_id:str): service,session=_service_session(session_id); return {"operation":_json(service.operations.payload(service.start_generation(session)))}
@router.post("/sessions/{session_id}/extensions")
def extend(session_id:str,body:SettingsPatch):
    service,parent=_service_session(session_id); creator,account=_context(); settings={**parent["settings"],**body.model_dump(exclude_none=True)}
    media_id=parent.get("final_generated_media_id")
    if not media_id: return JSONResponse(status_code=409,content={"error":"Session has no completed generated video to extend."})
    return _json(service.create(creator_profile_id=creator,account_id=account,source_type="generated_video",source_id=str(media_id),settings=settings,parent_session_id=str(parent["session_id"]),parent_video_id=str(media_id)))

@router.post("/sessions/{session_id}/alternates")
def alternate(session_id:str):
    service,parent=_service_session(session_id); creator,account=_context()
    if not parent.get("final_generated_media_id"): raise HTTPException(status_code=409,detail="Session has no completed video to alternate.")
    return _json(service.create(creator_profile_id=creator,account_id=account,source_type=parent["source_type"],source_id=str(parent["source_id"]),settings=parent["settings"],parent_session_id=str(parent["session_id"]),parent_video_id=str(parent["final_generated_media_id"])))

@router.get("/media/{media_id}")
def media_file(media_id:str,range_header:str|None=Header(None,alias="Range")):
    creator,_=_context(); record=GeneratedMediaService().get(media_id,creator)
    if not record: return JSONResponse(status_code=404,content={"error":"Generated media not found."})
    path=Path(record["media_path"]); size=path.stat().st_size
    # FastAPI cannot inject the Range header into a parameter named `range`;
    # this query-compatible route is retained for tests while Starlette's
    # FileResponse handles normal full responses.
    if not range_header: return FileResponse(path,media_type="video/mp4",headers={"Accept-Ranges":"bytes"})
    value=range_header.removeprefix("bytes="); start_text,end_text=value.split("-",1); start=int(start_text or 0); end=min(int(end_text) if end_text else size-1,size-1)
    if start>end or start>=size: return Response(status_code=416,headers={"Content-Range":f"bytes */{size}"})
    with path.open("rb") as stream: stream.seek(start); data=stream.read(end-start+1)
    return Response(data,status_code=206,media_type="video/mp4",headers={"Accept-Ranges":"bytes","Content-Range":f"bytes {start}-{end}/{size}","Content-Length":str(len(data))})

@router.get("/media/{media_id}/poster")
def media_poster(media_id:str):
    creator,_=_context(); record=GeneratedMediaService().get(media_id,creator)
    if not record or not record.get("poster_path") or not Path(record["poster_path"]).exists():
        return Response(status_code=404)
    return FileResponse(record["poster_path"],media_type="image/jpeg")
