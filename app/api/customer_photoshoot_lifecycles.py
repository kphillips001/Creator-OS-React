"""Protected read-only Photoshoot Sales Opportunity diagnostics."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.api.asset_library import _creator_profile
from app.api.developer_authorization import require_developer_authorization
from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
from app.repositories.autonomous_sales_progression_repository import AutonomousSalesProgressionRepository
from app.services.photoshoot_session_runtime_service import (
    PhotoshootSessionRuntimeService,
    PhotoshootSessionRuntimeUnavailable,
)

router=APIRouter(prefix='/api/v1/developer/customer-photoshoots',tags=['developer-customer-photoshoot-diagnostics'],dependencies=[Depends(require_developer_authorization)])

@router.get('/{customer_profile_id}/{photoshoot_id}')
def diagnostic(customer_profile_id:UUID,photoshoot_id:str,creator_profile_id:int=Depends(_creator_profile)):
    creator_id=int(creator_profile_id["id"] if isinstance(creator_profile_id,dict) else creator_profile_id)
    try:
        runtime=PhotoshootSessionRuntimeService().evaluate(creator_profile_id=creator_id,customer_commerce_profile_id=customer_profile_id,photoshoot_session_id=photoshoot_id)
    except KeyError as error: raise HTTPException(404,str(error)) from error
    except PhotoshootSessionRuntimeUnavailable as error: raise HTTPException(409,str(error)) from error
    service=CustomerPhotoshootLifecycleService(); lifecycle=service.repository.get(creator_profile_id=creator_id,customer_commerce_profile_id=customer_profile_id,photoshoot_id=photoshoot_id)
    if lifecycle is None:
        return {'customerProfileId':str(customer_profile_id),'photoshootId':photoshoot_id,'status':'NOT_STARTED','sessionRuntime':runtime.to_context()}
    value=service.diagnostics(lifecycle); coverage=value['coverage']; progression=AutonomousSalesProgressionRepository(); assets=progression.ordered_assets(creator_profile_id=creator_id,customer_commerce_profile_id=customer_profile_id,photoshoot_id=photoshoot_id)
    return {'opportunityId':str(lifecycle.lifecycle_id),'customerProfileId':str(customer_profile_id),'photoshootId':lifecycle.photoshoot_id,'status':lifecycle.status.value,'sessionRuntime':runtime.to_context(),'expiresAt':lifecycle.expires_at,'closedAt':lifecycle.closed_at,'finaleDecision':lifecycle.finale_decision.value,'orderedSellableAssets':[{'assetId':a.asset_id,'position':a.position,'role':a.role.value,'owned':a.owned,'presented':a.presented,'offeringId':str(a.offering_id) if a.offering_id else None} for a in assets],'presentedAssetIds':list(coverage['presented_asset_ids']),'purchasedAssetIds':list(coverage['purchased_asset_ids']),'remainingAssetIds':list(coverage['remaining_asset_ids']),'currentPosition':runtime.current_position,'finaleVideoEligible':any(a.role.value=='FINALE_VIDEO' and not a.owned and a.delivery_url for a in assets),'lastActivityAt':lifecycle.last_activity_at,'selectedOfferingId':str(lifecycle.selected_offering_id) if lifecycle.selected_offering_id else None,'lastSalesSessionId':str(lifecycle.last_sales_session_id) if lifecycle.last_sales_session_id else None,'recommendationReason':lifecycle.recommendation_reason,'history':list(value['history']),'recentActions':list(progression.recent_actions(creator_profile_id=creator_id,customer_commerce_profile_id=customer_profile_id))}
