"""Deterministic progression, momentum, finale, and bridge policy."""
from datetime import datetime,timezone
from app.models.autonomous_sales_progression import *
from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus


class BuyingMomentumService:
    def assess(self,e:BuyingMomentumEvidence)->BuyingMomentumAssessment:
        factors={'purchases':e.purchases,'rapidPurchases':e.rapid_purchases,'explicitMore':e.explicit_more,'declined':e.declined,'expiredIntents':e.expired_intents,'consecutiveNoResponse':e.consecutive_no_response,'activeIntent':e.active_intent,'cooldown':e.cooldown,'runtimeSuppressed':e.runtime_suppressed,'recentSpendMinor':e.recent_spend_minor,**dict(e.factors)}
        if e.runtime_suppressed: return BuyingMomentumAssessment(BuyingMomentumState.STOPPED,-100,factors,'Runtime or operator controls suppress selling.')
        if e.cooldown: return BuyingMomentumAssessment(BuyingMomentumState.COOLDOWN,-50,factors,'Authoritative purchase cooldown is active.')
        score=min(e.purchases,3)*2+min(e.rapid_purchases,3)*2+(4 if e.explicit_more else 0)-(4 if e.declined else 0)-min(e.expired_intents,2)*2-min(e.consecutive_no_response,3)*2
        state=BuyingMomentumState.HIGH if score>=8 else BuyingMomentumState.MODERATE if score>=4 else BuyingMomentumState.LOW if score<0 else BuyingMomentumState.UNKNOWN
        return BuyingMomentumAssessment(state,score,factors,f'Deterministic momentum score {score} from authoritative commerce and conversation factors.')

class AutonomousSalesProgressionService:
    def __init__(self,momentum_service=None,clock=lambda:datetime.now(timezone.utc)): self.momentum_service=momentum_service or BuyingMomentumService(); self.clock=clock
    @staticmethod
    def canonical_order(assets): return tuple(sorted(assets,key=lambda a:(a.position,a.asset_id)))
    @staticmethod
    def next_core(assets):
        # Presentation is not progression.  The first unpaid chapter remains
        # current until it is purchased or the opportunity terminates.
        return next((a for a in AutonomousSalesProgressionService.canonical_order(assets) if a.role in {ProgressionAssetRole.CORE_SESSION,ProgressionAssetRole.FINALE_IMAGE} and not a.owned and not a.rejected),None)
    @staticmethod
    def finale_video(assets): return next((a for a in AutonomousSalesProgressionService.canonical_order(assets) if a.role is ProgressionAssetRole.FINALE_VIDEO and not a.owned and not a.presented and not a.rejected and a.offering_id and a.publication_id and a.delivery_url),None)
    @staticmethod
    def bridge_asset(assets):
        eligible=[a for a in AutonomousSalesProgressionService.canonical_order(assets) if not a.owned and not a.rejected]
        return next((a for a in eligible if a.role is ProgressionAssetRole.DISCOVERY),eligible[0] if eligible else None)
    def decide(self,*,customer_profile_id,lifecycle=None,assets=(),momentum_evidence=BuyingMomentumEvidence(),active_purchase_intent_id=None,sales_session_id=None,target_lifecycle=None,target_assets=(),bridge_recent=False,selling_authorized=True,finale_required=False):
        momentum=self.momentum_service.assess(momentum_evidence); trace=[]; now=self.clock()
        base={'customer_profile_id':customer_profile_id,'buying_momentum':momentum,'evaluated_at':now,'active_lifecycle_id':getattr(lifecycle,'lifecycle_id',None),'current_photoshoot_id':getattr(lifecycle,'photoshoot_id',None),'sales_session_id':sales_session_id,'purchase_intent_id':active_purchase_intent_id}
        ordered=self.canonical_order(assets); core=tuple(a for a in ordered if a.role in {ProgressionAssetRole.CORE_SESSION,ProgressionAssetRole.FINALE_IMAGE}); remaining=tuple(a for a in core if not a.owned); position=sum(a.owned for a in core)
        counts={'current_position':position,'total_sellable_assets':len(core),'remaining_sellable_assets':len(remaining)}
        if not selling_authorized or momentum.state is BuyingMomentumState.STOPPED: return NextSalesAction(NextSalesActionType.STOP_SELLING,reason='Selling is suppressed by an authoritative control.',decision_trace=('runtime_suppression',),**base,**counts)
        if active_purchase_intent_id: return NextSalesAction(NextSalesActionType.REUSE_ACTIVE_INTENT,reason='An existing Purchase Intent must resolve before another offer.',decision_trace=('active_purchase_intent',),**base,**counts)
        if momentum.state is BuyingMomentumState.COOLDOWN: return NextSalesAction(NextSalesActionType.PAUSE_PHOTOSHOOT,reason='Purchase cooldown overrides continuation.',decision_trace=('purchase_cooldown',),**base,**counts)
        status=getattr(lifecycle,'status',None)
        if status in {CustomerPhotoshootStatus.COMPLETED,CustomerPhotoshootStatus.CLOSED,CustomerPhotoshootStatus.DECLINED}:
            return NextSalesAction(NextSalesActionType.CHAT_ONLY,reason='The Photoshoot Sales Opportunity is terminal and cannot resume automatically.',decision_trace=('opportunity_terminal',status.value),**base,**counts)
        if status is CustomerPhotoshootStatus.OBJECTION:
            return NextSalesAction(NextSalesActionType.HANDLE_OBJECTION,reason='The protected Photoshoot is in limited objection recovery.',decision_trace=('opportunity_objection',),**base,**counts)
        if lifecycle is not None:
            next_asset=self.next_core(ordered)
            if next_asset and momentum.state in {BuyingMomentumState.MODERATE,BuyingMomentumState.HIGH}:
                return NextSalesAction(NextSalesActionType.OFFER_NEXT_IMAGE,reason='The next Session Sales Strategy asset is eligible and momentum supports continuation.',selected_asset_id=next_asset.asset_id,selected_offering_id=next_asset.offering_id,publication_id=next_asset.publication_id,delivery_url=next_asset.delivery_url,decision_trace=('active_lifecycle','session_sales_strategy_order','momentum_sufficient'),metadata={'session_sales_strategy':dict(next_asset.strategy)},**base,**counts)
            if next_asset:
                action=NextSalesActionType.STALL_PHOTOSHOOT if momentum_evidence.expired_intents or momentum_evidence.consecutive_no_response else NextSalesActionType.PAUSE_PHOTOSHOOT
                return NextSalesAction(action,reason='Momentum is below the continuation threshold.',decision_trace=('next_core_available','momentum_insufficient'),**base,**counts)
            finale=self.finale_video(ordered)
            if finale and momentum.state in {BuyingMomentumState.MODERATE,BuyingMomentumState.HIGH}:
                return NextSalesAction(NextSalesActionType.OFFER_FINALE_VIDEO,reason='Core progression is complete and an eligible premium finale exists.',selected_asset_id=finale.asset_id,selected_offering_id=finale.offering_id,publication_id=finale.publication_id,delivery_url=finale.delivery_url,decision_trace=('core_complete','finale_video_eligible'),**base,**counts)
            if remaining or finale_required or finale: return NextSalesAction(NextSalesActionType.PAUSE_PHOTOSHOOT,reason='Required progression or the optional finale decision remains unresolved.',decision_trace=('opportunity_incomplete',),**base,**counts)
        if target_lifecycle and momentum.state in {BuyingMomentumState.MODERATE,BuyingMomentumState.HIGH} and not bridge_recent:
            bridge=self.bridge_asset(target_assets)
            if bridge: return NextSalesAction(NextSalesActionType.BRIDGE_TO_PHOTOSHOOT,reason='Current progression is exhausted and the Session Sales Strategy entry is eligible.',target_photoshoot_id=target_lifecycle.photoshoot_id,selected_asset_id=bridge.asset_id,selected_offering_id=bridge.offering_id,publication_id=bridge.publication_id,delivery_url=bridge.delivery_url,decision_trace=tuple(trace+['momentum_sufficient','session_strategy_entry_selected']),metadata={'session_sales_strategy':dict(bridge.strategy)},**base,**counts)
        if lifecycle is None and target_lifecycle:
            bridge=self.bridge_asset(target_assets)
            if bridge: return NextSalesAction(NextSalesActionType.INTRODUCE_PHOTOSHOOT,reason='No active lifecycle exists; introduce the persisted Session Sales Strategy entry.',target_photoshoot_id=target_lifecycle.photoshoot_id,selected_asset_id=bridge.asset_id,selected_offering_id=bridge.offering_id,publication_id=bridge.publication_id,delivery_url=bridge.delivery_url,decision_trace=('new_photoshoot','session_strategy_introduction'),metadata={'session_sales_strategy':dict(bridge.strategy)},**base,**counts)
        if lifecycle and not remaining and not finale_required: return NextSalesAction(NextSalesActionType.COMPLETE_PHOTOSHOOT,reason='All paid chapters are owned and the optional finale decision is resolved.',decision_trace=tuple(trace+['opportunity_complete']),**base,**counts)
        return NextSalesAction(NextSalesActionType.CHAT_ONLY,reason='No authorized Photoshoot sale is appropriate.',decision_trace=('no_sale_action',),**base,**counts)
