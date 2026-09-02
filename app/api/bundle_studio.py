"""Bundle Studio workspace endpoints."""
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.bundle_studio_service import BundleStudioConflict, BundleStudioService
from app.services.bundle_studio_sale_preparation_service import BundleStudioSalePreparationService
from app.services.bundle_studio_teaser_service import BundleStudioTeaserService
from app.services.bundle_library_service import BundleLibraryService
from app.services.content_vault_bundle_caption_context import ContentVaultBundleCaptionContextBuilder
from app.services.grok_caption_service import CaptionProfile, GrokCaptionService
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService
from app.services.creator_commerce_identity_service import resolve_fanvue_account_id
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from datetime import datetime, timezone
from fastapi.responses import FileResponse


router = APIRouter(prefix="/api/v1/bundle-studio", tags=["bundle-studio"])


class CreateWorkspaceRequest(BaseModel):
    name: str = "Untitled Bundle"


class ImagesRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1)


class MoveImagesRequest(ImagesRequest):
    bundle_name: str = "Untitled Bundle"


class RenameRequest(BaseModel):
    name: str


class PrepareSaleRequest(BaseModel):
    destination: str
    price_minor: int = Field(ge=300, le=50000)

class TeaserRequest(BaseModel):
    sourceAssetId: int; maskData: str; maskWidth: int; maskHeight: int; blurStrength: int

class CaptionGenerateRequest(BaseModel):
    guidance: str | None = Field(default=None, max_length=500)
    tone: str = "CLASSY"

class CaptionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    style: str | None = Field(default=None, max_length=40)
    source: str = "MANUAL"


def _creator_id() -> int:
    profile = get_active_creator_profile(_current_account_id())
    if not profile:
        raise HTTPException(status_code=409, detail="Create a Creator Profile before using Bundle Studio.")
    return int(profile["id"])


def _creator_commerce_identity() -> tuple[int, int]:
    """Resolve commerce identity from the active Creator Profile."""
    profile = get_active_creator_profile(_current_account_id())
    if not profile:
        raise HTTPException(status_code=409, detail="Create a Creator Profile before using Bundle Studio.")
    try:
        return int(profile["id"]), resolve_fanvue_account_id(profile)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _payload(bundle):
    if bundle is None:
        return {"success": True, "workspace": None}
    value = asdict(bundle)
    value["bundle_id"] = str(bundle.bundle_id)
    value["created_at"] = bundle.created_at.isoformat()
    value["updated_at"] = bundle.updated_at.isoformat()
    for member in value["members"]:
        member["added_at"] = member["added_at"].isoformat()
        version = member.get("generation_date") or member["added_at"]
        member["thumbnail_url"] = f"/api/v1/generation-library/{member['image_id']}/thumbnail?v={version}"
        member["image_url"] = f"/api/v1/generation-library/{member['image_id']}/media?v={version}"
    return {"success": True, "workspace": value}


def _call(action):
    try:
        return _payload(action())
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'")) from error
    except (ValueError, BundleStudioConflict) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/workspace")
def get_workspace():
    return _payload(BundleStudioService().active(creator_profile_id=_creator_id()))


@router.post("/workspace")
def create_workspace(request: CreateWorkspaceRequest):
    return _call(lambda: BundleStudioService().active(
        creator_profile_id=_creator_id(), create=True, name=request.name))


@router.post("/workspace/members")
def move_members(request: MoveImagesRequest):
    return _call(lambda: BundleStudioService().move_images(
        creator_profile_id=_creator_id(), image_ids=request.image_ids,
        bundle_name=request.bundle_name))


@router.delete("/workspace/members")
def return_members(request: ImagesRequest):
    return _call(lambda: BundleStudioService().return_images(
        creator_profile_id=_creator_id(), image_ids=request.image_ids))


@router.put("/workspace/name")
def rename_workspace(request: RenameRequest):
    return _call(lambda: BundleStudioService().rename(
        creator_profile_id=_creator_id(), name=request.name))


@router.put("/workspace/order")
def reorder_workspace(request: ImagesRequest):
    return _call(lambda: BundleStudioService().reorder(
        creator_profile_id=_creator_id(), image_ids=request.image_ids))


@router.delete("/workspace")
def abandon_workspace():
    return _call(lambda: BundleStudioService().abandon(creator_profile_id=_creator_id()))


@router.get("/workspace/sale-preparation")
def inspect_sale_preparation():
    workspace = BundleStudioService().active(creator_profile_id=_creator_id())
    if workspace is None:
        raise HTTPException(status_code=404, detail="Active Bundle Studio workspace not found.")
    return _call_commerce(lambda: BundleStudioSalePreparationService().inspect(
        workspace.bundle_id, creator_profile_id=workspace.creator_profile_id))


@router.post("/workspace/sale-preparation")
def prepare_sale(request: PrepareSaleRequest, background_tasks: BackgroundTasks):
    creator_profile_id, fanvue_account_id = _creator_commerce_identity()
    workspace = BundleStudioService().active(creator_profile_id=creator_profile_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Active Bundle Studio workspace not found.")
    service = BundleStudioSalePreparationService()
    publication_ids = _call_commerce(lambda: service.stage(
        workspace.bundle_id, creator_profile_id=workspace.creator_profile_id,
        destination=request.destination, fanvue_account_id=fanvue_account_id,
        price_minor=request.price_minor))
    if publication_ids:
        background_tasks.add_task(_execute_bundle_preparation, publication_ids,
                                  workspace.creator_profile_id, fanvue_account_id)
    return service.inspect(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id)


def _execute_bundle_preparation(publication_ids, creator_profile_id, fanvue_account_id):
    BundleStudioSalePreparationService().execute_staged(
        publication_ids, creator_profile_id=creator_profile_id,
        fanvue_account_id=fanvue_account_id)


def _call_commerce(action):
    try:
        return action()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'")) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

@router.get("/workspace/teaser")
def inspect_teaser():
    workspace = BundleStudioService().active(creator_profile_id=_creator_id())
    return _call_commerce(lambda: BundleStudioTeaserService().inspect(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id))

@router.put("/workspace/teaser")
def save_teaser(request: TeaserRequest):
    workspace = BundleStudioService().active(creator_profile_id=_creator_id())
    return _call_commerce(lambda: BundleStudioTeaserService().save(workspace.bundle_id,
        creator_profile_id=workspace.creator_profile_id, source_asset_id=request.sourceAssetId,
        mask_data=request.maskData, mask_width=request.maskWidth, mask_height=request.maskHeight,
        blur_strength=request.blurStrength))

@router.get("/workspace/teaser/mask", response_class=FileResponse)
def teaser_mask():
    workspace = BundleStudioService().active(creator_profile_id=_creator_id())
    path = _call_commerce(lambda: BundleStudioTeaserService().mask_path(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id))
    return FileResponse(path, media_type="image/png", headers={"Cache-Control":"no-store"})

@router.get("/commercial-bundles")
def commercial_bundles():
    return {"bundles": BundleLibraryService().list(creator_profile_id=_creator_id())}

def _wall_context():
    workspace = BundleStudioService().active(creator_profile_id=_creator_id())
    return workspace, BundleStudioSalePreparationService().content_vault_context(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id)

def _bundle_wall_context(bundle_id):
    creator_id = _creator_id()
    return bundle_id, creator_id, BundleStudioSalePreparationService().content_vault_context(bundle_id, creator_profile_id=creator_id)

@router.post("/workspace/content-vault/captions/generate")
def generate_captions(request: CaptionGenerateRequest):
    workspace, (bundle, members, offering, _) = _call_commerce(_wall_context)
    context = ContentVaultBundleCaptionContextBuilder().build(
        title=offering.title or workspace.name, paid_asset_ids=tuple(int(item["asset_id"]) for item in members),
        price_minor=int(offering.price_minor), currency=offering.currency,
        photoshoot_session_id=str(workspace.bundle_id), photoshoot_context={"source":"BUNDLE_STUDIO","bundle_name":workspace.name},
        teaser_context=BundleStudioTeaserService().inspect(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id))
    return GrokCaptionService().generate(profile=CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
        context=context, guidance=request.guidance, tone=request.tone)

@router.put("/workspace/content-vault/caption")
def save_caption(request: CaptionRequest):
    workspace, (_, members, offering, publication) = _call_commerce(_wall_context)
    text = request.text.strip(); count = len(members)
    text = (GrokCaptionService.validate_bundle_caption(text, count) if request.source.upper() == "GROK"
            else GrokCaptionService.validate_operator_bundle_caption(text))
    if len(text) > CommerceTelegramVaultService.TELEGRAM_PHOTO_CAPTION_LIMIT: raise HTTPException(status_code=409, detail="Content Vault caption exceeds Telegram's photo caption limit.")
    metadata = dict(publication.publication_metadata or {}); metadata["content_vault_caption_draft"] = {
        "text":text,"style":request.style.upper() if request.style else None,"source":request.source.upper(),
        "updatedAt":datetime.now(timezone.utc).isoformat(),"bundleStudioBundleId":str(workspace.bundle_id),
        "offeringId":str(offering.offering_id),"paidImageCount":count}
    CommercialPublicationRepository().update_metadata(publication.publication_id, creator_profile_id=workspace.creator_profile_id, metadata=metadata)
    return BundleStudioSalePreparationService().inspect(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id)

@router.post("/workspace/content-vault/publish")
def publish_content_vault():
    workspace, (_, _, offering, _) = _call_commerce(_wall_context)
    _call_commerce(lambda: CommerceTelegramVaultService().publish(offering.offering_id, creator_profile_id=workspace.creator_profile_id))
    return BundleStudioSalePreparationService().inspect(workspace.bundle_id, creator_profile_id=workspace.creator_profile_id)

@router.post("/commercial-bundles/{bundle_id}/content-vault/captions/generate")
def generate_commercial_bundle_captions(bundle_id: str, request: CaptionGenerateRequest):
    _, creator_id, (bundle, members, offering, _) = _call_commerce(lambda: _bundle_wall_context(bundle_id))
    context = ContentVaultBundleCaptionContextBuilder().build(title=offering.title,
        paid_asset_ids=tuple(int(item["asset_id"]) for item in members), price_minor=int(offering.price_minor),
        currency=offering.currency, photoshoot_session_id=str(bundle_id),
        photoshoot_context={"source":"BUNDLE_STUDIO","bundle_name":bundle["name"]},
        teaser_context=BundleStudioTeaserService().inspect(bundle_id, creator_profile_id=creator_id))
    return GrokCaptionService().generate(profile=CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
        context=context, guidance=request.guidance, tone=request.tone)

@router.put("/commercial-bundles/{bundle_id}/content-vault/caption")
def save_commercial_bundle_caption(bundle_id: str, request: CaptionRequest):
    _, creator_id, (_, members, offering, publication) = _call_commerce(lambda: _bundle_wall_context(bundle_id))
    text=request.text.strip(); count=len(members)
    text=GrokCaptionService.validate_bundle_caption(text,count) if request.source.upper()=="GROK" else GrokCaptionService.validate_operator_bundle_caption(text)
    if len(text) > CommerceTelegramVaultService.TELEGRAM_PHOTO_CAPTION_LIMIT:
        raise HTTPException(status_code=409, detail="Content Vault caption exceeds Telegram's photo caption limit.")
    metadata=dict(publication.publication_metadata or {});metadata["content_vault_caption_draft"]={"text":text,"style":request.style.upper() if request.style else None,"source":request.source.upper(),"updatedAt":datetime.now(timezone.utc).isoformat(),"bundleStudioBundleId":bundle_id,"offeringId":str(offering.offering_id),"paidImageCount":count}
    CommercialPublicationRepository().update_metadata(publication.publication_id,creator_profile_id=creator_id,metadata=metadata)
    return BundleStudioSalePreparationService().inspect(bundle_id,creator_profile_id=creator_id)

@router.post("/commercial-bundles/{bundle_id}/content-vault/publish")
def publish_commercial_bundle(bundle_id: str):
    _, creator_id, (_,_,offering,_) = _call_commerce(lambda: _bundle_wall_context(bundle_id))
    _call_commerce(lambda: CommerceTelegramVaultService().publish(offering.offering_id,creator_profile_id=creator_id))
    return BundleStudioSalePreparationService().inspect(bundle_id,creator_profile_id=creator_id)
