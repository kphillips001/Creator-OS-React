"""Deterministic Autonomous Sales Brain Phase 3 contracts."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class NextSalesActionType(str, Enum):
    CHAT_ONLY="CHAT_ONLY"; HANDLE_OBJECTION="HANDLE_OBJECTION"; INTRODUCE_PHOTOSHOOT="INTRODUCE_PHOTOSHOOT"; CONTINUE_PHOTOSHOOT="CONTINUE_PHOTOSHOOT"; OFFER_NEXT_IMAGE="OFFER_NEXT_IMAGE"; OFFER_FINALE_VIDEO="OFFER_FINALE_VIDEO"; BRIDGE_TO_PHOTOSHOOT="BRIDGE_TO_PHOTOSHOOT"; PAUSE_PHOTOSHOOT="PAUSE_PHOTOSHOOT"; STALL_PHOTOSHOOT="STALL_PHOTOSHOOT"; COMPLETE_PHOTOSHOOT="COMPLETE_PHOTOSHOOT"; STOP_SELLING="STOP_SELLING"; REUSE_ACTIVE_INTENT="REUSE_ACTIVE_INTENT"

class BuyingMomentumState(str, Enum):
    UNKNOWN="UNKNOWN"; LOW="LOW"; MODERATE="MODERATE"; HIGH="HIGH"; COOLDOWN="COOLDOWN"; STOPPED="STOPPED"

class ProgressionAssetRole(str, Enum):
    DISCOVERY="DISCOVERY"; CORE_SESSION="CORE_SESSION"; FINALE_IMAGE="FINALE_IMAGE"; FINALE_VIDEO="FINALE_VIDEO"

@dataclass(frozen=True)
class SellableProgressionAsset:
    asset_id:int; position:int; role:ProgressionAssetRole; offering_id:UUID|None=None; publication_id:UUID|None=None; delivery_url:str|None=None; price_minor:int|None=None; currency:str|None=None; owned:bool=False; presented:bool=False; rejected:bool=False; strategy:Mapping[str,Any]=field(default_factory=dict)

@dataclass(frozen=True)
class BuyingMomentumEvidence:
    purchases:int=0; rapid_purchases:int=0; explicit_more:bool=False; declined:bool=False; expired_intents:int=0; consecutive_no_response:int=0; active_intent:bool=False; cooldown:bool=False; runtime_suppressed:bool=False; recent_spend_minor:int=0; factors:Mapping[str,Any]=field(default_factory=dict)

@dataclass(frozen=True)
class BuyingMomentumAssessment:
    state:BuyingMomentumState; score:int; factors:Mapping[str,Any]; explanation:str

@dataclass(frozen=True)
class NextSalesAction:
    action:NextSalesActionType; customer_profile_id:UUID; buying_momentum:BuyingMomentumAssessment; reason:str; evaluated_at:datetime
    active_lifecycle_id:UUID|None=None; current_photoshoot_id:str|None=None; target_photoshoot_id:str|None=None; selected_asset_id:int|None=None; selected_offering_id:UUID|None=None; publication_id:UUID|None=None; delivery_url:str|None=None; current_position:int=0; total_sellable_assets:int=0; remaining_sellable_assets:int=0; sales_session_id:UUID|None=None; purchase_intent_id:UUID|None=None; decision_trace:tuple[str,...]=(); metadata:Mapping[str,Any]=field(default_factory=dict)

    def to_context(self):
        return {'action':self.action.value,'customer_profile_id':str(self.customer_profile_id),'active_lifecycle_id':str(self.active_lifecycle_id) if self.active_lifecycle_id else None,'current_photoshoot_id':self.current_photoshoot_id,'target_photoshoot_id':self.target_photoshoot_id,'selected_asset_id':self.selected_asset_id,'selected_offering_id':str(self.selected_offering_id) if self.selected_offering_id else None,'publication_id':str(self.publication_id) if self.publication_id else None,'delivery_url':self.delivery_url,'current_position':self.current_position,'total_sellable_assets':self.total_sellable_assets,'remaining_sellable_assets':self.remaining_sellable_assets,'buying_momentum':self.buying_momentum.state.value,'momentum_score':self.buying_momentum.score,'momentum_factors':dict(self.buying_momentum.factors),'momentum_explanation':self.buying_momentum.explanation,'reason':self.reason,'decision_trace':list(self.decision_trace),'sales_session_id':str(self.sales_session_id) if self.sales_session_id else None,'purchase_intent_id':str(self.purchase_intent_id) if self.purchase_intent_id else None,'evaluated_at':self.evaluated_at.isoformat(),'metadata':dict(self.metadata)}

    @classmethod
    def from_context(cls,value):
        uuid_value=lambda key: UUID(str(value[key])) if value.get(key) else None
        momentum=BuyingMomentumAssessment(BuyingMomentumState(value['buying_momentum']),int(value.get('momentum_score',0)),dict(value.get('momentum_factors') or {}),str(value.get('momentum_explanation') or value.get('reason') or ''))
        return cls(action=NextSalesActionType(value['action']),customer_profile_id=UUID(str(value['customer_profile_id'])),buying_momentum=momentum,reason=str(value['reason']),evaluated_at=datetime.fromisoformat(value['evaluated_at']),active_lifecycle_id=uuid_value('active_lifecycle_id'),current_photoshoot_id=value.get('current_photoshoot_id'),target_photoshoot_id=value.get('target_photoshoot_id'),selected_asset_id=value.get('selected_asset_id'),selected_offering_id=uuid_value('selected_offering_id'),publication_id=uuid_value('publication_id'),delivery_url=value.get('delivery_url'),current_position=int(value.get('current_position',0)),total_sellable_assets=int(value.get('total_sellable_assets',0)),remaining_sellable_assets=int(value.get('remaining_sellable_assets',0)),sales_session_id=uuid_value('sales_session_id'),purchase_intent_id=uuid_value('purchase_intent_id'),decision_trace=tuple(value.get('decision_trace') or ()),metadata=dict(value.get('metadata') or {}))
