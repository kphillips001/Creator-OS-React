"""Read-only prospect/buyer eligibility; never creates identity evidence."""
from app.database import get_db_connection
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.runtime_control_service import RuntimeControlService
from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService

class RelationshipOfferEligibilityService:
    def __init__(self, connection_factory=get_db_connection, runtime=None, safety=None):
        self.connection_factory=connection_factory
        self.relationships=RelationshipsRepository(connection_factory=connection_factory)
        self.runtime=runtime or RuntimeControlService()
        self.safety=safety or CustomerInteractionSafetyService()

    def require(self, context):
        scope={k:context[k] for k in ('creator_profile_id','fanvue_account_id','telegram_user_id')}
        current=self.relationships.control_context(**scope)
        if not current: raise ValueError('Known Telegram relationship is required.')
        for key in ('telegram_chat_id','telegram_identity_mapping_id','local_fanvue_user_id','external_fanvue_user_uuid'):
            if current.get(key)!=context.get(key): raise ValueError('Relationship identity changed; refresh before offering.')
        with self.connection_factory() as c:
            mappings=c.execute("""SELECT id,telegram_chat_id FROM telegram_identity_map
                WHERE telegram_user_id=%s AND is_active=TRUE AND verification_status='VERIFIED'""",
                (scope['telegram_user_id'],)).fetchall()
            if len(mappings)>1 or (mappings and mappings[0]['id']!=current.get('telegram_identity_mapping_id')):
                raise ValueError('Relationship identity is ambiguous.')
            prospect=c.execute("""SELECT relationship_state,telegram_chat_id FROM telegram_sales_prospects
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s""",tuple(scope.values())).fetchone()
            if prospect:
                if mappings and mappings[0]['telegram_chat_id']!=prospect['telegram_chat_id']:
                    raise ValueError('Relationship identity is ambiguous.')
                block=(prospect['relationship_state'] or {}).get('telegramContactBlock') or {}
                if block.get('active') or block.get('blocked') or block.get('state')=='PERMANENT_BLOCKED':
                    raise ValueError('Telegram relationship is blocked.')
        if current.get('active_sales_session'): raise ValueError('An active sales session conflicts with this offer.')
        decision=self.runtime.evaluate_runtime(creator_profile_id=scope['creator_profile_id'])
        if not decision.allow_offers or not decision.allow_deliveries:
            raise ValueError('Commerce is unavailable: '+decision.reason)
        if current.get('local_fanvue_user_id'):
            safety=self.safety.decide(creator_profile_id=scope['creator_profile_id'],fanvue_account_id=scope['fanvue_account_id'],fanvue_user_id=current['local_fanvue_user_id'])
            if not safety.allowed: raise ValueError('Customer safety restriction: '+safety.code)
        return {'identityState':'MAPPED' if current.get('telegram_identity_mapping_id') else 'PROSPECT',
                'ownershipEvidence':'AUTHORITATIVE_LOOKUP' if current.get('telegram_identity_mapping_id') else 'FANVUE_HISTORY_UNKNOWN'}
