"""One-query provider-neutral Customer Controls inventory."""
from app.database import get_db_connection

class CustomerControlsInventoryRepository:
 def __init__(self,connection_factory=get_db_connection):self.connection_factory=connection_factory
 def rows(self,*,creator_profile_id,fanvue_account_id):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""WITH canonical AS (
    SELECT 'CANONICAL_CUSTOMER' row_kind,'customer:'||%s||':'||u.fanvue_account_id||':'||u.id row_key,
      u.id local_fanvue_user_id,u.fanvue_user_uuid,u.username canonical_username,u.display_name canonical_display_name,u.source canonical_source,
      COALESCE(u.display_name,u.username,p.display_name,p.handle,'Customer') display_name,
      COALESCE(u.username,p.handle) best_username,p.handle fanvue_handle,
      p.customer_commerce_profile_id,p.lifetime_gross_minor,p.lifetime_net_minor,p.purchase_count,p.first_purchase_at,p.last_purchase_at,p.last_synced_at,
      (SELECT COUNT(DISTINCT own.content_item_id) FROM provider_purchase_asset_ownership own WHERE own.fanvue_account_id=u.fanvue_account_id AND own.external_fanvue_user_uuid=u.fanvue_user_uuid) owned_asset_count,
      m.telegram_user_id,t.private_chat_id telegram_chat_id,t.username telegram_username,t.display_name telegram_display_name,t.last_observed_at telegram_observed_at,
      t.observation_sources,t.source_channel_id,t.private_chat_id,t.participant_status,
      CASE WHEN m.id IS NOT NULL AND m.is_active AND m.verification_status='VERIFIED' THEN 'VERIFIED' WHEN t.telegram_user_id IS NOT NULL THEN 'OBSERVED_UNVERIFIED' ELSE 'NOT_OBSERVED' END telegram_status,
      CASE WHEN t.private_chat_id IS NOT NULL THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END control_availability,
      COALESCE(control.mode,'AVA_AUTO') mode,
      COALESCE(control.content_selling_enabled,true) content_selling_enabled,
      COALESCE(control.session_selling_enabled,true) session_selling_enabled,
      x.external_numeric_id x_numeric_id,x.observed_username x_username,x.observed_display_name x_display_name,
      CASE WHEN x.external_numeric_id IS NOT NULL THEN 'VERIFIED' ELSE 'NOT_OBSERVED' END x_status,
      CASE WHEN t.private_chat_id IS NOT NULL THEN 'telegram:'||%s||':'||u.fanvue_account_id||':'||t.telegram_user_id END relationship_key,x.external_identity_link_id x_link_id,
      CASE
        WHEN m.id IS NOT NULL THEN 'VERIFIED_EXTERNAL_MAPPING'
        WHEN t.private_chat_id IS NOT NULL THEN 'PRIVATE_TELEGRAM_RELATIONSHIP'
        WHEN control.relationship_control_id IS NOT NULL THEN 'OTHER_CERTIFIED_REASON'
        WHEN x.external_identity_link_id IS NOT NULL THEN 'VERIFIED_EXTERNAL_MAPPING'
        WHEN EXISTS (SELECT 1 FROM canonical_relationship_facts fact WHERE fact.creator_profile_id=%s AND fact.fanvue_account_id=u.fanvue_account_id AND fact.subject_type='CUSTOMER' AND fact.subject_id=u.id AND fact.state='CURRENT') THEN 'CANONICAL_INTELLIGENCE'
        WHEN EXISTS (SELECT 1 FROM canonical_customer_materialization_audit audit WHERE audit.fanvue_account_id=u.fanvue_account_id AND audit.local_fanvue_user_id=u.id AND audit.source LIKE 'operator%%') THEN 'EXPLICIT_OPERATOR_ONBOARDING'
      END operational_eligibility_reason,
      GREATEST(p.last_seen_at,prospect.last_observed_at,t.last_observed_at) latest_activity_at
    FROM fanvue_users u LEFT JOIN customer_commerce_profiles p ON p.fanvue_account_id=u.fanvue_account_id AND p.external_fanvue_user_uuid=u.fanvue_user_uuid
    LEFT JOIN telegram_identity_map m ON m.fanvue_account_id=u.fanvue_account_id AND m.local_fanvue_user_id=u.id AND m.is_active AND m.verification_status='VERIFIED'
    LEFT JOIN telegram_identity_observations t ON t.telegram_user_id=m.telegram_user_id
    LEFT JOIN telegram_sales_prospects prospect ON prospect.creator_profile_id=%s AND prospect.fanvue_account_id=u.fanvue_account_id AND prospect.telegram_user_id=m.telegram_user_id
    LEFT JOIN telegram_relationship_controls control ON control.creator_profile_id=%s AND control.fanvue_account_id=u.fanvue_account_id AND control.telegram_user_id=m.telegram_user_id
    LEFT JOIN verified_external_customer_identities x ON x.creator_profile_id=%s AND x.fanvue_account_id=u.fanvue_account_id AND x.local_fanvue_user_id=u.id AND x.platform='X' AND x.is_active
    WHERE u.fanvue_account_id=%s AND (
      m.id IS NOT NULL OR t.private_chat_id IS NOT NULL OR control.relationship_control_id IS NOT NULL
      OR x.external_identity_link_id IS NOT NULL
      OR EXISTS (SELECT 1 FROM canonical_relationship_facts fact WHERE fact.creator_profile_id=%s AND fact.fanvue_account_id=u.fanvue_account_id AND fact.subject_type='CUSTOMER' AND fact.subject_id=u.id AND fact.state='CURRENT')
      OR EXISTS (SELECT 1 FROM canonical_customer_materialization_audit audit WHERE audit.fanvue_account_id=u.fanvue_account_id AND audit.local_fanvue_user_id=u.id AND audit.source LIKE 'operator%%')
    )), prospects AS (
    SELECT 'TELEGRAM_PROSPECT','telegram:'||p.creator_profile_id||':'||p.fanvue_account_id||':'||p.telegram_user_id,
      NULL::bigint,NULL::uuid,NULL,NULL,NULL,COALESCE(t.display_name,t.username,'Telegram prospect'),t.username,NULL,
      NULL::uuid,NULL::bigint,NULL::bigint,0,NULL::timestamptz,NULL::timestamptz,NULL::timestamptz,0::bigint,
      p.telegram_user_id,p.telegram_chat_id,t.username,t.display_name,p.last_observed_at,
      ARRAY['PRIVATE_CHAT']::text[],NULL::bigint,p.telegram_chat_id,NULL::text,
      'OBSERVED_UNVERIFIED','AVAILABLE',
      COALESCE(control.mode,'AVA_AUTO'),COALESCE(control.content_selling_enabled,true),COALESCE(control.session_selling_enabled,true),
      NULL,NULL,NULL,'NOT_OBSERVED','telegram:'||p.creator_profile_id||':'||p.fanvue_account_id||':'||p.telegram_user_id,NULL::uuid,'PRIVATE_TELEGRAM_RELATIONSHIP',p.last_observed_at
    FROM telegram_sales_prospects p LEFT JOIN telegram_identity_map m ON m.telegram_user_id=p.telegram_user_id AND m.fanvue_account_id=p.fanvue_account_id AND m.is_active AND m.verification_status='VERIFIED'
    LEFT JOIN telegram_identity_observations t ON t.telegram_user_id=p.telegram_user_id
    LEFT JOIN telegram_relationship_controls control ON control.creator_profile_id=p.creator_profile_id AND control.fanvue_account_id=p.fanvue_account_id AND control.telegram_user_id=p.telegram_user_id
    WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s AND m.id IS NULL
      AND (
        p.inbound_message_count > 0 OR t.private_chat_id IS NOT NULL
        OR EXISTS (
          SELECT 1 FROM ordinary_chat_reply_operations reply
          WHERE reply.telegram_chat_id=p.telegram_chat_id
            AND reply.inbound_sender_telegram_user_id=p.telegram_user_id
        )
      ))
    SELECT * FROM canonical UNION ALL SELECT * FROM prospects ORDER BY latest_activity_at DESC NULLS LAST,row_key""",
    (creator_profile_id,creator_profile_id,creator_profile_id,creator_profile_id,creator_profile_id,creator_profile_id,fanvue_account_id,creator_profile_id,creator_profile_id,fanvue_account_id))
   return q.fetchall()
