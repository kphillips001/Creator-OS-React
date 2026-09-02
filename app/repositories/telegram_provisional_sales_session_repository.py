"""Transactional provisional Session creation and exactly-once graduation."""
import json
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.telegram_provisional_sales_session import TelegramProvisionalSalesSession
from app.repositories.advisory_lock_key import deterministic_bigint_advisory_lock_key


_PROVISIONAL_SESSION_LOCK_DOMAIN = (
    "creator-os:telegram-provisional-session:create-or-get:v1"
)


def provisional_session_advisory_lock_key(
    *, fanvue_account_id: int, telegram_user_id: int,
) -> int:
    return deterministic_bigint_advisory_lock_key(
        domain=_PROVISIONAL_SESSION_LOCK_DOMAIN,
        components=(
            ("fanvue_account_id", fanvue_account_id),
            ("telegram_user_id", telegram_user_id),
        ),
    )


class TelegramProvisionalSalesSessionRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_active(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM public.telegram_provisional_sales_sessions
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s
                      AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT')
                    ORDER BY created_at DESC LIMIT 1""",
                    (creator_profile_id, fanvue_account_id, telegram_user_id))
                row = cursor.fetchone()
        return self._model(row) if row else None

    def create_or_get(self, *, prospect, photoshoot_reference, session_strategy,
                      configured_base_price_minor, commercial_context):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                lock_key = provisional_session_advisory_lock_key(
                    fanvue_account_id=prospect.fanvue_account_id,
                    telegram_user_id=prospect.telegram_user_id,
                )
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s::bigint)",
                    (lock_key,),
                )
                cursor.execute("""SELECT session.*,intent.status AS bound_intent_status
                    FROM public.telegram_provisional_sales_sessions session
                    LEFT JOIN public.purchase_intents intent
                      ON intent.purchase_intent_id=session.first_purchase_intent_id
                    WHERE session.creator_profile_id=%s
                      AND session.fanvue_account_id=%s
                      AND session.telegram_user_id=%s
                      AND session.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT')
                    FOR UPDATE OF session""",
                    (prospect.creator_profile_id, prospect.fanvue_account_id,
                     prospect.telegram_user_id))
                row = cursor.fetchone()
                if row is not None and row.get("bound_intent_status") == "ADMIN_CLOSED":
                    cursor.execute("""UPDATE public.telegram_provisional_sales_sessions
                        SET state='ADMIN_CLOSED',administratively_closed_at=NOW(),
                            administrative_close_reason='BOUND_INTENT_ADMIN_CLOSED',
                            updated_at=NOW()
                        WHERE provisional_session_id=%s
                          AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT')""",
                        (row["provisional_session_id"],))
                    row = None
                if row is None:
                    cursor.execute("""INSERT INTO public.telegram_provisional_sales_sessions (
                        provisional_session_id,telegram_sales_prospect_id,creator_profile_id,
                        fanvue_account_id,telegram_user_id,telegram_chat_id,photoshoot_reference,
                        session_strategy,configured_base_price_minor,commercial_context)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING *""",
                        (uuid4(), prospect.telegram_sales_prospect_id,
                         prospect.creator_profile_id, prospect.fanvue_account_id,
                         prospect.telegram_user_id, prospect.telegram_chat_id,
                         photoshoot_reference, session_strategy,
                         configured_base_price_minor,
                         json.dumps(dict(commercial_context or {}), default=str)))
                    row = cursor.fetchone()
        return self._model(row)

    def associate_intent(self, provisional_session_id, purchase_intent_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_provisional_sales_sessions SET
                    first_purchase_intent_id=COALESCE(first_purchase_intent_id,%s),
                    state='AWAITING_PAYMENT',updated_at=NOW()
                    WHERE provisional_session_id=%s
                      AND (first_purchase_intent_id IS NULL OR first_purchase_intent_id=%s)
                    RETURNING *""", (purchase_intent_id, provisional_session_id,
                                      purchase_intent_id))
                row = cursor.fetchone()
        if row is None:
            raise ValueError("Provisional Session is already bound to another intent.")
        return self._model(row)

    def graduate(self, *, purchase_intent_id, mapping, buyer_uuid,
                 actual_fingerprint_price_minor):
        """Create/attach one canonical Session and record Item 1 once."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM public.telegram_provisional_sales_sessions
                    WHERE first_purchase_intent_id=%s FOR UPDATE""", (purchase_intent_id,))
                provisional = cursor.fetchone()
                if provisional is None:
                    return None
                if provisional["state"] == "GRADUATED":
                    return self._model(provisional)
                cursor.execute("""SELECT sales_session_id,commercial_foundation_reference
                    FROM public.sales_sessions
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s
                      AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')
                    FOR UPDATE""", (provisional["creator_profile_id"],
                    provisional["fanvue_account_id"], mapping.local_fanvue_user_id))
                existing = cursor.fetchone()
                if (existing is not None and
                    str(existing["commercial_foundation_reference"]) !=
                    str(provisional["photoshoot_reference"])):
                    raise ValueError(
                        "Existing active Session has a different commercial foundation."
                    )
                session_id = existing["sales_session_id"] if existing else uuid4()
                if existing is None:
                    context = dict(provisional.get("commercial_context") or {})
                    context["provisionalSessionId"] = str(provisional["provisional_session_id"])
                    context["configuredBasePriceMinor"] = provisional["configured_base_price_minor"]
                    context["actualFingerprintPriceMinor"] = actual_fingerprint_price_minor
                    cursor.execute("""INSERT INTO public.sales_sessions (
                        sales_session_id,creator_profile_id,fanvue_account_id,fanvue_user_id,
                        external_fanvue_user_uuid,telegram_identity_mapping_id,
                        commercial_foundation_type,commercial_foundation_reference,state,
                        progression_stage,objective,commercial_context,started_by_type,
                        started_by_identifier) VALUES (%s,%s,%s,%s,%s,%s,'PHOTOSHOOT',%s,
                        'CONTINUING','PROGRESSION','Fingerprint bootstrap Session',%s::jsonb,
                        'AI','FingerprintPurchaseAttributionService')""", (session_id,
                        provisional["creator_profile_id"], provisional["fanvue_account_id"],
                        mapping.local_fanvue_user_id, buyer_uuid, mapping.id,
                        provisional["photoshoot_reference"], json.dumps(context, default=str)))
                cursor.execute("""INSERT INTO public.sales_session_purchase_intents
                    (sales_session_id,purchase_intent_id,sequence_index) VALUES (%s,%s,1)
                    ON CONFLICT (purchase_intent_id) DO NOTHING""",
                    (session_id, purchase_intent_id))
                cursor.execute("""UPDATE public.telegram_provisional_sales_sessions SET
                    state='GRADUATED',mapped_sales_session_id=%s,
                    actual_fingerprint_price_minor=%s,
                    first_purchase_recorded_at=COALESCE(first_purchase_recorded_at,NOW()),
                    current_position=GREATEST(current_position,2),
                    progression_stage='PROGRESSION',graduated_at=COALESCE(graduated_at,NOW()),
                    updated_at=NOW() WHERE provisional_session_id=%s RETURNING *""",
                    (session_id, actual_fingerprint_price_minor,
                     provisional["provisional_session_id"]))
                row = cursor.fetchone()
        return self._model(row)

    @staticmethod
    def _model(row):
        values = dict(row)
        values.pop("bound_intent_status", None)
        for key in ("provisional_session_id", "telegram_sales_prospect_id",
                    "first_purchase_intent_id", "mapped_sales_session_id"):
            if values.get(key) is not None:
                values[key] = UUID(str(values[key]))
        values["commercial_context"] = values.get("commercial_context") or {}
        return TelegramProvisionalSalesSession(**values)
