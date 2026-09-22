from uuid import uuid4
from datetime import timedelta
from app.database import get_db_connection

class ActiveOfferFollowThroughRepository:
 def __init__(self,connection_factory=get_db_connection): self.connection_factory=connection_factory
 def confirmed_summary(self,intent_id):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT count(*)::int confirmed_count,max(confirmed_at) last_nudge_at
   FROM active_offer_follow_through_events WHERE purchase_intent_id=%s AND delivery_state='SENT_CONFIRMED'""",(intent_id,));return q.fetchone()
 def relationship_nonconversion(self,**scope):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT count(DISTINCT e.purchase_intent_id)::int nonconversion_count,max(e.confirmed_at) last_confirmed_nudge_at FROM active_offer_follow_through_events e JOIN purchase_intents p ON p.purchase_intent_id=e.purchase_intent_id WHERE e.creator_profile_id=%s AND e.fanvue_account_id=%s AND e.telegram_user_id=%s AND e.telegram_chat_id=%s AND e.delivery_state='SENT_CONFIRMED' AND e.customer_response_observed_at IS NOT NULL AND e.purchase_observed_at IS NULL AND p.purchased_at IS NULL""",tuple(int(scope[k]) for k in ('creator_profile_id','fanvue_account_id','telegram_user_id','telegram_chat_id')));return dict(q.fetchone())
 def reserve(self,*,intent,reason,eligible_at,operation_id,now,cooldown=timedelta(hours=2),direct=False):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(str(intent.purchase_intent_id),))
   q.execute("SELECT status,expires_at,purchased_at FROM purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",(intent.purchase_intent_id,)); live=q.fetchone()
   if not live or live['status'] not in ('PRESENTED','CLICKED') or live['purchased_at'] or live['expires_at']<=eligible_at:return None
   q.execute("""SELECT * FROM active_offer_follow_through_events
    WHERE purchase_intent_id=%s ORDER BY nudge_sequence,event_id LIMIT 1""",
    (intent.purchase_intent_id,)); existing=q.fetchone()
   if existing:
    return (existing if existing['operation_id']==operation_id
            and existing['delivery_state'] in ('AUTHORIZED','GENERATED','SENDING')
            else None)
   q.execute("""INSERT INTO active_offer_follow_through_events(event_id,purchase_intent_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,nudge_sequence,nudge_reason,eligible_at,operation_id)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(operation_id) DO NOTHING RETURNING *""",
   (uuid4(),intent.purchase_intent_id,intent.creator_profile_id,intent.fanvue_account_id,intent.telegram_user_id,intent.telegram_chat_id,1,reason,eligible_at,operation_id));return q.fetchone()
 def confirm(self,*,operation_id,outbound_id,confirmed_at):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""UPDATE active_offer_follow_through_events SET delivery_state='SENT_CONFIRMED',outbound_telegram_message_id=%s,confirmed_at=%s,updated_at=NOW()
   WHERE operation_id=%s AND delivery_state IN ('AUTHORIZED','GENERATED') RETURNING *""",(outbound_id,confirmed_at,operation_id));return q.fetchone()
 def validate_before_generation(self,operation_id):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT e.* FROM active_offer_follow_through_events e
    JOIN purchase_intents p ON p.purchase_intent_id=e.purchase_intent_id
    WHERE e.operation_id=%s AND e.delivery_state='AUTHORIZED'
      AND p.status IN ('PRESENTED','CLICKED') AND p.expires_at>NOW()
      AND p.purchased_at IS NULL AND p.provider_transaction_order_id IS NULL
      AND p.provider_payment_id IS NULL AND p.provider_event_id IS NULL""",(operation_id,));return q.fetchone()
 def observe_customer_response(self,*,intent_id,observed_at):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""UPDATE active_offer_follow_through_events e SET customer_response_observed_at=COALESCE(customer_response_observed_at,%s),updated_at=NOW()
    WHERE purchase_intent_id=%s AND delivery_state='SENT_CONFIRMED' AND confirmed_at<%s
      AND NOT EXISTS(SELECT 1 FROM purchase_intents p WHERE p.purchase_intent_id=e.purchase_intent_id AND (p.status<>'PRESENTED' AND p.status<>'CLICKED' OR p.purchased_at IS NOT NULL)) RETURNING *""",(observed_at,intent_id,observed_at));return q.fetchall()
