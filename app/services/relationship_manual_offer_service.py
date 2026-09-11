from datetime import datetime, timedelta, timezone
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
                 chat_inventory=None,ownership=None,
                 clock=lambda:datetime.now(timezone.utc)):
        self.fulfillment=fulfillment or CommercialFulfillmentRepository()
        self.operations=operations or TelegramManualOfferRepository()
        self.controls=controls or TelegramRelationshipControlService()
        self.peers=peer_observations or TelegramBusinessPeerObservationRepository()
        self.selector=selector or CommercialOfferingSelectorService()
        self.intents=intents or PurchaseIntentService()
        self.unlocks=unlocks or PrivateChatUnlockGatewayService()
        self.deliveries=deliveries or TelegramSalesDeliveryService(
            purchase_intent_service=self.intents,conversation_message_saver=save_chat_message)
        self.transport=transport or TelegramBusinessCommercialTransport()
        self.chat_inventory=chat_inventory or ChatCommerceInventoryService()
        self.ownership=ownership or OwnershipIntelligenceService()
        self.clock=clock

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

    def send(self, *, context, offering_id, expected_control_version, business_connection_id,
             idempotency_key, message_text):
        self._manual_control(context,expected_control_version)
        offering=self._offering(context,offering_id)
        self._require_customer(context,offering,business_connection_id)
        text=str(message_text or '').strip()
        if not text or len(text)>4096: raise RelationshipManualOfferError('Offer message must be 1–4096 characters.',422)
        operation=self.operations.reserve(context=context,offering=offering,business_connection_id=business_connection_id,
            idempotency_key=idempotency_key,message_text=text,expected_control_version=expected_control_version)
        if operation['state']=='CONFIRMED': return operation
        if operation['state'] in ('SENDING','AMBIGUOUS'): raise RelationshipManualOfferError('Offer delivery requires reconciliation.')
        claimed=self.operations.claim(operation['operation_id'],expected_control_version)
        if claimed is None: raise RelationshipManualOfferError('Manual Mode changed before send.')
        intent=None;claimed_delivery=None
        try:
            correlation=uuid5(NAMESPACE_URL,f"relationship-manual-offer:{operation['operation_id']}")
            intent=self.intents.create_before_presentation(creator_profile_id=context['creator_profile_id'],
                fanvue_account_id=context['fanvue_account_id'],telegram_identity_mapping_id=context['telegram_identity_mapping_id'],
                telegram_user_id=context['telegram_user_id'],telegram_chat_id=context['telegram_chat_id'],
                external_fanvue_user_uuid=context.get('external_fanvue_user_uuid'),commercial_offering_id=UUID(str(offering['offering_id'])),
                commercial_publication_id=UUID(str(offering['publication_id'])),provider='FANVUE',
                provider_resource_id=str(offering['external_product_id']),delivery_url=str(offering['delivery_url']),
                telegram_message_id=None,conversation_id=str(context['conversation_thread_id']),correlation_id=correlation,
                expected_price_minor=int(offering['price_minor']),expected_currency=str(offering['currency']),
                expires_at=self.clock()+timedelta(hours=24),created_metadata={'presentation_origin':'HUMAN_OPERATOR_PRESENTED'})
            self.operations.attach(operation['operation_id'],purchase_intent_id=intent.purchase_intent_id)
            _,unlock_url=self.unlocks.issue(intent)
            result=SimpleNamespace(correlation_id=correlation,response_text=text,
                diagnostic_metadata={'conversation_thread_id':context['conversation_thread_id'],
                    'conversation_fanvue_account_id':context['fanvue_account_id'],
                    'conversation_fanvue_user_id':context['local_fanvue_user_id']},
                delivery_payload={'delivery_type':'TEXT','delivery_reason':'COMMERCIAL_OFFER','metadata':{
                    'price_minor':offering['price_minor'],'currency':offering['currency'],
                    'presentation_origin':'HUMAN_OPERATOR_PRESENTED','private_chat_unlock_button':True}})
            payload=SimpleNamespace(telegram_chat_id=context['telegram_chat_id'],
                message_id=context['latest_inbound_telegram_message_id'])
            delivery,_=self.deliveries.prepare(intent=intent,result=result,payload=payload)
            self.operations.attach(operation['operation_id'],sales_delivery_operation_id=delivery.operation_id)
            claimed_delivery=self.deliveries.claim(delivery)
            receipt=self.transport.send_text(chat_id=context['telegram_chat_id'],message_text=text,
                button_label=self.transport.BUTTON_LABEL,button_url=unlock_url,
                expected_business_connection_id=business_connection_id)
            message_id=getattr(receipt,'id',receipt)
            accepted=self.deliveries.accepted(claimed_delivery,message_id)
            evidence=getattr(receipt,'provider_payload',None)
            if evidence:self.deliveries.record_provider_evidence(accepted,evidence)
            self.deliveries.confirm(accepted)
            self.controls.repository.touch_manual_activity(self._manual_control(context,expected_control_version))
            return self.operations.finish(operation['operation_id'],'CONFIRMED',message_id=message_id)
        except (TimeoutError,ConnectionError,OSError) as error:
            if claimed_delivery is not None:self.deliveries.failed(claimed_delivery,error)
            self.operations.finish(operation['operation_id'],'AMBIGUOUS',error=error)
            raise RelationshipManualOfferError('Telegram offer delivery outcome is uncertain.') from error
        except Exception as error:
            if claimed_delivery is not None:self.deliveries.failed(claimed_delivery,error)
            if intent is not None:
                try:self.intents.mark_delivery_failed(intent.purchase_intent_id)
                except Exception:pass
            self.operations.finish(operation['operation_id'],'FAILED',error=error)
            raise RelationshipManualOfferError(f'Offer was not sent: {error}') from error

    def _manual_control(self,context,version):
        control=self.controls.get(creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],
            telegram_user_id=context['telegram_user_id'],telegram_chat_id=context['telegram_chat_id'])
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
        if not all(context.get(key) for key in ('telegram_identity_mapping_id','local_fanvue_user_id','conversation_thread_id','latest_inbound_telegram_message_id')):
            raise RelationshipManualOfferError('Verified customer conversation context is required.')
        if str(offering.get('photoshoot_selling_mode') or '').upper()=='SESSION':
            raise RelationshipManualOfferError('Session selling requires the canonical Sales Session lifecycle.')
        intents,owned=self.operations.customer_state(creator_profile_id=context['creator_profile_id'],fanvue_account_id=context['fanvue_account_id'],telegram_user_id=context['telegram_user_id'])
        owned|=self._owned_offerings(context)
        if str(offering['offering_id']) in owned: raise RelationshipManualOfferError('Customer already owns this offering.')
        if any(item['status'] in ('CREATED','PRESENTED','CLICKED') for item in intents):
            raise RelationshipManualOfferError('An active PurchaseIntent already exists for this customer.')
        evidence=self.peers.evidence(business_connection_id=connection_id,telegram_peer_user_id=context['telegram_user_id'])
        if not evidence or not evidence['is_enabled'] or not evidence['can_reply'] or not evidence['last_business_inbound_at']:
            raise RelationshipManualOfferError('Recent Telegram Business peer evidence is required.')
        last=evidence['last_business_inbound_at'];last=last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        if self.clock()-last>timedelta(hours=24): raise RelationshipManualOfferError('Telegram Business peer evidence is stale.')

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
