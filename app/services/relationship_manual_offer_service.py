import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from app.services.telegram_transport_boundary import RoutedTelegramSender, TelegramInvocationUnknown
from app.models.telegram_transport_contract import TelegramRequirements, TelegramPreflightError
import os
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.commercial_offering import PrimarySalesChannel
from app.repositories.commercial_fulfillment_repository import CommercialFulfillmentRepository
from app.repositories.telegram_manual_offer_repository import TelegramManualOfferRepository
from app.repositories.telegram_business_peer_observation_repository import TelegramBusinessPeerObservationRepository
from app.services.commercial_offering_selector_service import CommercialOfferingSelectorService
from app.services.private_chat_unlock_gateway_service import PrivateChatUnlockGatewayService
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.telegram_business_commercial_transport import TelegramBusinessCommercialTransport
from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
from app.services.telegram_business_connection_service import TelegramBusinessConnectionService
from app.services.chat_commerce_inventory_service import ChatCommerceInventoryService
from app.models.chat_commerce_inventory import ChatCommerceInventoryFilter
from app.services.ownership_intelligence_service import OwnershipIntelligenceService
from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.chat_message_repository import save_chat_message


class RelationshipManualOfferError(RuntimeError):
    def __init__(self,message,status_code=409):
        super().__init__(message);self.status_code=status_code


class RelationshipManualOfferService:
    def __init__(self, *, fulfillment=None, operations=None, controls=None, peer_observations=None,
                 selector=None, intents=None, unlocks=None, deliveries=None, transport=None,
                 chat_inventory=None,ownership=None,transport_candidates=None,eligibility=None,presentations=None,
                 runtime_transport=None, resolver=None, clock=lambda:datetime.now(timezone.utc)):
        self.fulfillment=fulfillment or CommercialFulfillmentRepository()
        self.operations=operations or TelegramManualOfferRepository()
        self.controls=controls or TelegramRelationshipControlService()
        self.peers=peer_observations or TelegramBusinessPeerObservationRepository()
        self.selector=selector or CommercialOfferingSelectorService()
        self.intents=intents or PurchaseIntentService()
        self.unlocks=unlocks or PrivateChatUnlockGatewayService()
        self.deliveries=deliveries or TelegramSalesDeliveryService(
            purchase_intent_service=self.intents,conversation_message_saver=save_chat_message)
        self.runtime_transport = runtime_transport
        self.queued_dispatch = transport is None and transport_candidates is None
        from app.services.telegram_manual_transport_resolver import TelegramManualTransportResolver
        self.resolver = resolver or TelegramManualTransportResolver()
        self.transport=transport or TelegramBusinessCommercialTransport()
        self.transport_candidates=tuple(transport_candidates or (self.transport,))
        self.chat_inventory=chat_inventory or ChatCommerceInventoryService()
        self.ownership=ownership or OwnershipIntelligenceService()
        self.clock=clock
        from app.services.relationship_offer_eligibility_service import RelationshipOfferEligibilityService
        from app.services.private_ppv_presentation_service import PrivatePpvPresentationService
        self.eligibility=eligibility or RelationshipOfferEligibilityService()
        self.presentations=presentations or PrivatePpvPresentationService()

    def inventory(self, *, context, view='RECOMMENDED', offering_type=None, search='', hide_purchased=True):
        rows,_,_=self.fulfillment.list_fulfillable(creator_profile_id=context['creator_profile_id'],
            primary_sales_channel=PrimarySalesChannel.AI_CHAT.value,offering_type=None,
            provider='FANVUE',page=1,page_size=1000)
        # ChatCommerceInventoryService is an older asset-centric operational
        # projection.  It is useful as optional diagnostics/enrichment, but it
        # is not the authority for provider-ready Commercial Offerings and may
        # legitimately be empty while Commercial Fulfillment is populated.
        try:
            inventory=self.chat_inventory.build_inventory(filters=ChatCommerceInventoryFilter(
                chat_ready=True,fulfillment_ready=True),limit=1000)
            legacy_assets={item.asset_id for item in inventory.items}
        except Exception:
            legacy_assets=set()
        intents,owned=self.operations.customer_state(creator_profile_id=context['creator_profile_id'],
            fanvue_account_id=context['fanvue_account_id'],telegram_user_id=context['telegram_user_id'])
        owned|=self._owned_offerings(context)
        by_offering={}
        for intent in intents: by_offering.setdefault(str(intent['commercial_offering_id']),[]).append(intent)
        recommended_id=self._recommended_id(context)
        cards=[]
        for row in rows:
            # A SESSION photoshoot is an ordered lifecycle, not a one-off
            # offering.  Phase 3B must enter it through the canonical session
            # proposal/progression authority before it can be selectable here.
            if str(row.get('photoshoot_selling_mode') or '').upper()=='SESSION':continue
            if offering_type and not self._matches_type(row,offering_type):continue
            key=str(row['offering_id']); history=by_offering.get(key,[])
            active=next((item for item in history if item['status'] in ('CREATED','PRESENTED','CLICKED')),None)
            presentations=[item for item in history if item['presented_at'] is not None and item['confirmed_delivery']]
            is_owned=key in owned
            status='PURCHASED' if is_owned else 'ACTIVE_OFFER' if active else 'OFFERED_BEFORE' if presentations else 'AVAILABLE'
            if hide_purchased and is_owned: continue
            if search and search.lower() not in f"{row['title']} {row.get('description') or ''}".lower(): continue
            if view=='NEVER_OFFERED' and status!='AVAILABLE': continue
            if view=='PREVIOUSLY_OFFERED' and status!='OFFERED_BEFORE': continue
            if view=='RECOMMENDED' and key!=recommended_id: continue
            cards.append({'offeringId':key,'title':row['title'],'description':row.get('description'),
                'type':row['offering_type'],'priceMinor':row['price_minor'],'currency':row['currency'],
                'thumbnailUrl':f"/api/v1/assets/{row['hero_asset_id']}/thumbnail",'status':status,
                'owned':is_owned,'eligible':not is_owned and active is None,
                'presentationCount':len(presentations),'recommended':key==recommended_id,
                'lastPresentationAt':max((item['presented_at'] for item in presentations),default=None),
                'legacyChatInventoryPresent':int(row['hero_asset_id']) in legacy_assets,
                'activePurchaseIntentId':str(active['purchase_intent_id']) if active else None})
        for card in cards:
            try:
                control=self.controls.get(creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],telegram_user_id=context['telegram_user_id'],telegram_chat_id=context['telegram_chat_id'])
                self._manual_control(context,control.control_version)
                self._require_customer(context,next(r for r in rows if str(r['offering_id'])==card['offeringId']),None)
                card['eligibilityReason']=None
            except (RelationshipManualOfferError,ValueError) as error:
                card['eligible']=False;card['eligibilityReason']=str(error)
            card['ownershipEvidence']='AUTHORITATIVE_LOOKUP' if context.get('telegram_identity_mapping_id') else 'FANVUE_HISTORY_UNKNOWN'
        bot_id=int(os.getenv('TELEGRAM_BUSINESS_BOT_ID','0') or 0)
        owner_id=int(os.getenv('TELEGRAM_BUSINESS_OWNER_USER_ID','0') or 0)
        connection=(TelegramBusinessConnectionService(bot_telegram_user_id=bot_id).active(
            business_owner_telegram_user_id=owner_id) if bot_id and owner_id else None)
        return {'items':cards,'view':view,'hidePurchased':hide_purchased,
            'businessConnectionId':getattr(connection,'business_connection_id',None)}

    def prepare(self, *, context, offering_id, expected_control_version, business_connection_id):
        control=self._manual_control(context,expected_control_version)
        offering=self._offering(context,offering_id)
        self._require_customer(context,offering,business_connection_id)
        return {'offering':self._review(offering),'businessConnectionId':business_connection_id,
            'controlVersion':control.control_version,
            'defaultMessage':f"I picked this for you — {offering['title']}. Unlock it below 💋"}

    def send(self, **values):
        if not self.queued_dispatch:
            return asyncio.run(self._execute(**values))
        context = values['context']
        text = str(values['message_text'] or '').strip()
        existing = self.operations.by_key(context=context,idempotency_key=values['idempotency_key'])
        if existing:
            if str(existing['commercial_offering_id']) != str(values['offering_id']) or existing['message_text'] != text:
                raise RelationshipManualOfferError('Idempotency key was already used for a different offer.')
            return existing
        self._manual_control(context,values['expected_control_version'])
        offering = self._offering(context,values['offering_id'])
        self._require_customer(context,offering,values['business_connection_id'])
        self.presentations.validate_customer_text(text)
        if not text or len(text)>1000:
            raise RelationshipManualOfferError('Offer caption must be 1-1000 characters.',422)
        return self.operations.reserve(context=context,offering=offering,
            business_connection_id=values['business_connection_id'],idempotency_key=values['idempotency_key'],
            message_text=text,expected_control_version=values['expected_control_version'],queued=True)

    async def dispatch_pending(self):
        from app.repositories.relationships_repository import RelationshipsRepository
        self.operations.quarantine_stale_dispatches()
        count = 0
        for operation in self.operations.pending_private_dispatches():
            scope = {key:operation[key] for key in ('creator_profile_id','fanvue_account_id','telegram_user_id')}
            try:
                context = {**scope, **(RelationshipsRepository().control_context(**scope) or {})}
                await self._execute(context=context,offering_id=operation['commercial_offering_id'],
                    expected_control_version=operation['relationship_control_version'],
                    business_connection_id=operation['business_connection_id'],
                    idempotency_key=operation['idempotency_key'],message_text=operation['message_text'],
                    reserved=operation)
            except Exception as error:
                current = self.operations.get(operation['operation_id'])
                if current and current['state']=='PREPARED':
                    self.operations.finish(operation['operation_id'],'FAILED',error=error)
            count += 1
        return count

    async def _live_transport(self, context, offering):
        errors = []
        candidates = list(self.transport_candidates)
        if self.runtime_transport is not None:
            candidates.append(self.runtime_transport)
        for sender in candidates:
            caption_link = sender is self.runtime_transport
            if caption_link and offering["offering_type"] != "SINGLE_IMAGE": continue
            requirements = TelegramRequirements(text=True,photo=offering["offering_type"]=="SINGLE_IMAGE",caption=offering["offering_type"]=="SINGLE_IMAGE",
                url_action=not caption_link,caption_text_url=caption_link)
            try:
                peer = sender.prepare_delivery(chat_id=context['telegram_chat_id'],requirements=requirements)
                if inspect.isawaitable(peer): peer = await peer
                peer.validate(requirements)
                if peer.peer_id != context['telegram_chat_id']:
                    raise TelegramPreflightError('Wrong peer.')
                return sender, peer.transport
            except Exception as error:
                errors.append(str(error))
        raise RelationshipManualOfferError('No reachable transport supports UNLOCK: '+','.join(errors))

    async def _execute(self, *, context, offering_id, expected_control_version, business_connection_id,
                       idempotency_key, message_text, reserved=None):
        text=str(message_text or '').strip()
        existing=self.operations.by_key(context=context,idempotency_key=idempotency_key)
        if existing and reserved is None:
            if str(existing['commercial_offering_id'])!=str(offering_id) or existing['message_text']!=text:
                raise RelationshipManualOfferError('Idempotency key was already used for a different offer.')
            if existing['state']=='CONFIRMED':return existing
            raise RelationshipManualOfferError('Existing offer operation requires reconciliation; do not retry.')
        self._manual_control(context,expected_control_version)
        offering=self._offering(context,offering_id)
        self._require_customer(context,offering,business_connection_id)
        self.presentations.validate_customer_text(text)
        if not text or len(text)>4096: raise RelationshipManualOfferError('Offer message must be 1–4096 characters.',422)
        sender, selected_transport = await self._live_transport(context,offering)
        operation=self.operations.reserve(context=context,offering=offering,business_connection_id=business_connection_id,
            idempotency_key=idempotency_key,message_text=text,expected_control_version=expected_control_version)
        if operation['state']=='CONFIRMED': return operation
        if operation['state'] in ('SENDING','AMBIGUOUS','FAILED'): raise RelationshipManualOfferError('Offer delivery requires reconciliation.')
        claimed=self.operations.claim(operation['operation_id'],expected_control_version)
        if claimed is None: raise RelationshipManualOfferError('Manual Mode changed before send.')
        intent=None;claimed_delivery=None;invocation_started=False;accepted_by_provider=False
        try:
            correlation=uuid5(NAMESPACE_URL,f"relationship-manual-offer:{operation['operation_id']}")
            intent=self.intents.create_before_presentation(creator_profile_id=context['creator_profile_id'],
                fanvue_account_id=context['fanvue_account_id'],telegram_identity_mapping_id=context.get('telegram_identity_mapping_id'),
                telegram_user_id=context['telegram_user_id'],telegram_chat_id=context['telegram_chat_id'],
                external_fanvue_user_uuid=context.get('external_fanvue_user_uuid'),commercial_offering_id=UUID(str(offering['offering_id'])),
                commercial_publication_id=UUID(str(offering['publication_id'])),provider='FANVUE',
                provider_resource_id=str(offering['external_product_id']),delivery_url=str(offering['delivery_url']),
                telegram_message_id=None,conversation_id=str(context.get('conversation_thread_id') or f"telegram:{context['creator_profile_id']}:{context['fanvue_account_id']}:{context['telegram_user_id']}"),correlation_id=correlation,
                expected_price_minor=int(offering['price_minor']),expected_currency=str(offering['currency']),
                expires_at=self.clock()+timedelta(hours=24),created_metadata={'presentation_origin':'HUMAN_OPERATOR_PRESENTED','manual_offer_operation_id':str(operation['operation_id'])})
            self.operations.attach(operation['operation_id'],purchase_intent_id=intent.purchase_intent_id)
            final_price = int(offering['price_minor'])
            reserve_price = getattr(self.unlocks, 'reserve_offer_price', None)
            if callable(reserve_price):
                intent, final_price = reserve_price(intent)
            _,unlock_url=self.unlocks.issue(intent)
            from app.models.telegram_offer_caption import telegram_offer_caption
            canonical_text = telegram_offer_caption(text)

            result=SimpleNamespace(correlation_id=correlation,response_text=text,
                diagnostic_metadata={'conversation_thread_id':context['conversation_thread_id'],
                    'conversation_fanvue_account_id':context['fanvue_account_id'],
                    'conversation_fanvue_user_id':context.get('local_fanvue_user_id'),
                    'manual_offer_operation_id':str(operation['operation_id'])},
                delivery_payload={'delivery_type':'TEXT','delivery_reason':'COMMERCIAL_OFFER','metadata':{
                    'price_minor':final_price,'configured_base_price_minor':offering['price_minor'],'currency':offering['currency'],
                    'presentation_origin':'HUMAN_OPERATOR_PRESENTED','private_chat_unlock_button':True}})
            payload=SimpleNamespace(telegram_chat_id=context['telegram_chat_id'],
                message_id=context['latest_inbound_telegram_message_id'])
            if offering['offering_type']=='SINGLE_IMAGE':
                presentation=self.presentations.build(creator_profile_id=context['creator_profile_id'],
                    offering_id=offering['offering_id'],publication_id=offering['publication_id'],
                    purchase_intent_id=intent.purchase_intent_id,
                    delivery_identity=f"telegram:{context['telegram_user_id']}:{context['telegram_chat_id']}",
                    attribution_identity=str(context.get('external_fanvue_user_uuid') or f"provisional:{context['telegram_user_id']}"),
                    message_text=canonical_text,unlock_button_url=unlock_url)
                presentation.apply_to(result.delivery_payload)
            from app.models.telegram_unlock_action import TelegramUnlockAction
            rendered = TelegramUnlockAction(unlock_url).render(canonical_text,
                transport=selected_transport,button_label=self.transport.BUTTON_LABEL)
            result.delivery_payload['message_text'] = rendered['message_text']
            result.delivery_payload['metadata']['unlock_action'] = {
                'semantic':'UNLOCK','destination':unlock_url,'transport':selected_transport,
                'rendering':'CAPTION_TEXT_URL' if 'caption_entities' in rendered else 'INLINE_URL_BUTTON'}
            result.delivery_payload['operator_rendered_send'] = rendered
            if 'caption_entities' in rendered:
                result.delivery_payload['metadata'].pop('private_chat_unlock_button',None)
            result.response_text = rendered['message_text']
            delivery,_=self.deliveries.prepare_operator_offer(intent=intent,result=result,payload=payload,
                manual_operation_id=operation['operation_id'])
            self.operations.attach(operation['operation_id'],sales_delivery_operation_id=delivery.operation_id)
            claimed_delivery=self.deliveries.claim(delivery)
            if claimed_delivery is None:
                raise RelationshipManualOfferError('Delivery claim was not acquired.')
            def record(evidence):
                nonlocal invocation_started,accepted_by_provider
                if 'transport_route' in evidence:
                    self._manual_control(context,expected_control_version)
                    invocation_started=True
                if evidence.get('accepted'):
                    accepted_by_provider=True
                return self.deliveries.record_provider_evidence(claimed_delivery,evidence)
            routed=RoutedTelegramSender(sender,context={
                'operation_id':str(claimed_delivery.operation_id),
                'record_transport_evidence':record},metadata={})
            with self.controls.repository.manual_send_guard(
                    creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],
                    telegram_user_id=context['telegram_user_id'],expected_version=expected_control_version):
                self._require_live_authority(context,expected_control_version,offering)
                values=dict(chat_id=context['telegram_chat_id'],**rendered)
                if result.delivery_payload.get('asset_path'):
                    receipt=routed.send_asset(asset_path=result.delivery_payload['asset_path'],**values)
                else:receipt=routed.send_text(**values)
                if inspect.isawaitable(receipt): receipt = await asyncio.wait_for(receipt, timeout=45)
            message_id=getattr(receipt,'id',receipt)
            if not isinstance(message_id,int) or isinstance(message_id,bool) or message_id<=0:
                raise TelegramInvocationUnknown('Provider acknowledgement has no message ID.')
            accepted=self.deliveries.accepted(claimed_delivery,message_id)
            if accepted is None:
                raise TelegramInvocationUnknown('Provider acceptance was not persisted.')
            confirmed=self.deliveries.confirm(accepted)
            if confirmed is None or getattr(getattr(confirmed,'state',None),'value',getattr(confirmed,'state',None)) != 'CONFIRMED':
                raise TelegramInvocationUnknown('Delivery terminal state was not persisted.')
            self.controls.repository.touch_manual_activity(self._manual_control(context,expected_control_version))
            return self.operations.finish(operation['operation_id'],'CONFIRMED',message_id=message_id)
        except (TimeoutError,ConnectionError,OSError) as error:
            if claimed_delivery is not None:self.deliveries.failed(claimed_delivery,error)
            self.operations.finish(operation['operation_id'],'AMBIGUOUS',error=error)
            raise RelationshipManualOfferError('Telegram offer delivery outcome is uncertain.') from error
        except Exception as error:
            if invocation_started or accepted_by_provider:
                uncertain=TelegramInvocationUnknown('Manual offer requires reconciliation.')
                if claimed_delivery is not None:self.deliveries.failed(claimed_delivery,uncertain)
                self.operations.finish(operation['operation_id'],'AMBIGUOUS',error=uncertain)
                raise RelationshipManualOfferError(str(uncertain)) from error
            if claimed_delivery is not None:self.deliveries.failed(claimed_delivery,error)
            if intent is not None:
                try:self.intents.mark_delivery_failed(intent.purchase_intent_id)
                except Exception:pass
            self.operations.finish(operation['operation_id'],'FAILED',error=error)
            raise RelationshipManualOfferError(f'Offer was not sent: {error}') from error

    def _require_live_authority(self,context,version,offering):
        self._manual_control(context,version)
        self.eligibility.require(context)
        current=self._offering(context,offering['offering_id'])
        if any(current.get(key)!=offering.get(key) for key in ('publication_id','price_minor','currency','external_product_id','delivery_url')):
            raise RelationshipManualOfferError('Offering changed before delivery; prepare a fresh review.')
        if str(offering['offering_id']) in self._owned_offerings(context):
            raise RelationshipManualOfferError('Customer already owns this offering.')

    def _manual_control(self,context,version):
        control=self.controls.get(creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],
            telegram_user_id=context['telegram_user_id'],telegram_chat_id=context['telegram_chat_id'])
        if getattr(control,'ignored',False): raise RelationshipManualOfferError('Relationship is ignored.')
        if not getattr(control,'content_selling_enabled',True): raise RelationshipManualOfferError('Content selling is disabled.')
        if not control.manual: raise RelationshipManualOfferError('Manual Mode is not active.')
        if control.control_version!=int(version): raise RelationshipManualOfferError('Relationship control version is stale.')
        return control

    def _offering(self,context,offering_id):
        try: key=UUID(str(offering_id))
        except ValueError as error: raise RelationshipManualOfferError('Offering was not found.',404) from error
        rows,_,_=self.fulfillment.list_fulfillable(creator_profile_id=context['creator_profile_id'],
            primary_sales_channel=PrimarySalesChannel.AI_CHAT.value,offering_type=None,provider='FANVUE',page=1,page_size=1000)
        row=next((item for item in rows if UUID(str(item['offering_id']))==key),None)
        if not row:
            raise RelationshipManualOfferError('Offering is not currently eligible.')
        return row

    def _require_customer(self,context,offering,connection_id):
        try:self.eligibility.require(context)
        except ValueError as error:raise RelationshipManualOfferError(str(error)) from error
        if not context.get('latest_inbound_telegram_message_id'):
            raise RelationshipManualOfferError('Known Telegram inbound context is required.')
        price=offering.get('price_minor');currency=str(offering.get('currency') or '')
        if isinstance(price,bool) or not isinstance(price,int) or price<=0 or len(currency)!=3 or not currency.isalpha():
            raise RelationshipManualOfferError('Configured price or currency is invalid.')
        if offering.get('offering_type')=='SINGLE_IMAGE':
            readiness=self.presentations.readiness.evaluate(offering)
            if not readiness.ready:raise RelationshipManualOfferError('Presentation unavailable: '+str(readiness.reason))
        if str(offering.get('photoshoot_selling_mode') or '').upper()=='SESSION':
            raise RelationshipManualOfferError('Session selling requires the canonical Sales Session lifecycle.')
        intents,owned=self.operations.customer_state(creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],telegram_user_id=context['telegram_user_id'])
        owned|=self._owned_offerings(context)
        if str(offering['offering_id']) in owned: raise RelationshipManualOfferError('Customer already owns this offering.')
        if any(item['status'] in ('CREATED','PRESENTED','CLICKED') for item in intents):
            raise RelationshipManualOfferError('An active PurchaseIntent already exists for this customer.')
        self._select_transport(context,offering)

    def _select_transport(self,context,offering=None):
        if self.queued_dispatch:
            try:
                return self.resolver.resolve(context)
            except Exception as error:
                raise RelationshipManualOfferError(str(error)) from error
        # Injected synchronous adapters preserve the Business contract.
        requirements=TelegramRequirements(text=True,url_action=True,photo=bool(offering and offering['offering_type']=='SINGLE_IMAGE'),caption=bool(offering and offering['offering_type']=='SINGLE_IMAGE'))
        errors=[]
        for sender in self.transport_candidates:
            try:
                prepare=getattr(sender,'prepare_delivery',None)
                if not callable(prepare):raise TelegramPreflightError('Missing reachability contract.')
                peer=prepare(chat_id=context['telegram_chat_id'],requirements=requirements)
                peer.validate(requirements)
                if peer.peer_id!=context['telegram_chat_id']:raise TelegramPreflightError('Wrong peer.')
                return sender
            except Exception as error:
                errors.append(str(error))
        raise RelationshipManualOfferError('No reachable transport supports the offer URL action: '+','.join(errors))

    def _recommended_id(self,context):
        try:
            profile=SimpleNamespace(fanvue_account_id=context['fanvue_account_id'],
                external_fanvue_user_uuid=context.get('external_fanvue_user_uuid'))
            result=self.selector.select(creator_profile_id=context['creator_profile_id'],telegram_user_id=context['telegram_user_id'],
                customer_profile=profile,commerce_signal=None,active_purchase_intent=None,
                conversation_context={'primary_sales_channel':'AI_CHAT','conversation_id':context.get('conversation_thread_id')})
            return str(result.offering_id) if getattr(result,'offering_id',None) else None
        except Exception:
            return None

    def _owned_offerings(self,context):
        answer=self.ownership.answer(OwnershipIdentity(creator_profile_id=context['creator_profile_id'],
            fanvue_account_id=context['fanvue_account_id'],external_fanvue_user_uuid=context.get('external_fanvue_user_uuid'),
            telegram_user_id=context['telegram_user_id'],legacy_fanvue_user_id=None,core_user_id=None))
        if getattr(answer,'conflicts',()):raise RelationshipManualOfferError('Ownership evidence is conflicting.')
        if any(str(reason).startswith('OWNERSHIP_SOURCE_UNAVAILABLE') for reason in getattr(answer,'insufficiencies',())):
            raise RelationshipManualOfferError('Ownership evidence is unavailable; try after the source is restored.')
        return {str(value) for value in answer.owned_offering_ids}

    @staticmethod
    def _review(row):
        return {'offeringId':str(row['offering_id']),'title':row['title'],'type':row['offering_type'],
            'priceMinor':row['price_minor'],'currency':row['currency'],
            'thumbnailUrl':f"/api/v1/assets/{row['hero_asset_id']}/thumbnail"}

    @staticmethod
    def _matches_type(row,requested):
        requested=str(requested).upper();kind=str(row.get('offering_type') or '').upper()
        if requested=='SINGLE':return kind in {'SINGLE_IMAGE','VIDEO','STORY'}
        if requested=='BUNDLE':return kind in {'BUNDLE','PHOTOSET','STORY_SET'}
        if requested=='SESSION':return str(row.get('photoshoot_selling_mode') or '').upper()=='SESSION'
        return kind==requested
