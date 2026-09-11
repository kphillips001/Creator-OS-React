import logging
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from app.api.creator_intelligence import _snapshot_scope
from app.services.ask_creator_os_service import AskCreatorOsError,AskCreatorOsService

router=APIRouter(prefix="/api/v1/ask-creator-os",tags=["ask-creator-os"])
logger=logging.getLogger("ask_creator_os")
class AskRequest(BaseModel):
    question:str=Field(min_length=1,max_length=1000)
    context:list[dict]=Field(default_factory=list,max_length=12)
    selectedPersonKey:str|None=None
@router.post("")
def ask(payload:AskRequest):
    creator,account=_snapshot_scope()
    try:return AskCreatorOsService().ask(question=payload.question,creator_profile_id=creator,fanvue_account_id=account,context=payload.context[-6:],selected_person_key=payload.selectedPersonKey)
    except AskCreatorOsError as error:raise HTTPException(status_code=422,detail=str(error)) from error
    except Exception as error:
        logger.exception("event=ask_creator_os_api success=false")
        raise HTTPException(status_code=503,detail="Creator_OS intelligence is temporarily unavailable.") from error
