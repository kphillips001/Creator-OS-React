"""Single-transaction settlement for a confirmed fingerprint purchase."""
import json
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.telegram_identity import TelegramIdentityMapping


class PrivateChatPurchaseSettlementService:
    PROVENANCE = "PRIVATE_CHAT_FINGERPRINT_PURCHASE"
    SOURCES = frozenset({"medialink", "media_link", "media"})

    def __init__(self, connection_factory=get_db_connection, fail_after=None):
        self.connection_factory = connection_factory
        self.fail_after = fail_after

    def _checkpoint(self, name):
        if self.fail_after == name:
            raise RuntimeError(f"Injected settlement failure after {name}")

    def settle(self, *, fanvue_account_id, currency, gross_minor, source,
               buyer_uuid, local_fanvue_user_id, transaction_id, payment_id,
               event_id, purchased_at):
        if str(source).lower() not in self.SOURCES:
            return None
        currency = str(currency).upper()
        buyer_uuid = UUID(str(buyer_uuid))
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                # Deterministic lock order: reservation/evidence, intent,
                # observation/prospect, provider customer/mapping, Sessions.
                cursor.execute("""SELECT reservation.*,runtime.runtime_media_link_id,
                    runtime.state AS runtime_state
                    FROM public.fanvue_fingerprint_reservations reservation
                    JOIN public.fanvue_runtime_media_links runtime USING (fingerprint_reservation_id)
                    WHERE reservation.fanvue_account_id=%s AND reservation.currency=%s
                      AND reservation.exact_price_minor=%s
                      AND runtime.state IN ('ACTIVE','PURCHASED') FOR UPDATE OF reservation,runtime""",
                    (fanvue_account_id, currency, gross_minor))
                matches = cursor.fetchall()
                if len(matches) != 1:
                    return None
                match = matches[0]
                cursor.execute("SELECT * FROM public.purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",
                               (match["purchase_intent_id"],))
                intent = cursor.fetchone()
                if intent is None or int(intent["fanvue_account_id"]) != int(fanvue_account_id):
                    return None
                if str(intent["expected_currency"]).upper() != currency:
                    return None
                prior_tx = intent.get("provider_transaction_order_id")
                if prior_tx and prior_tx != transaction_id:
                    raise ValueError("PurchaseIntent was settled by another transaction.")
                cursor.execute("SELECT * FROM public.telegram_identity_observations WHERE telegram_user_id=%s FOR UPDATE",
                               (intent["telegram_user_id"],))
                observation = cursor.fetchone()
                if observation is None:
                    raise ValueError("Telegram identity observation is required.")
                cursor.execute("""SELECT * FROM public.telegram_sales_prospects
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s FOR UPDATE""",
                    (intent["creator_profile_id"], fanvue_account_id, intent["telegram_user_id"]))
                prospect = cursor.fetchone()
                cursor.execute("SELECT * FROM public.fanvue_users WHERE id=%s AND fanvue_account_id=%s AND fanvue_user_uuid=%s FOR UPDATE",
                               (local_fanvue_user_id, fanvue_account_id, buyer_uuid))
                user = cursor.fetchone()
                if user is None:
                    raise ValueError("Authenticated Fanvue customer is not synchronized.")
                cursor.execute("""SELECT * FROM public.telegram_identity_map
                    WHERE telegram_user_id=%s OR (fanvue_account_id=%s AND external_fanvue_user_uuid=%s)
                    FOR UPDATE""", (intent["telegram_user_id"], fanvue_account_id, buyer_uuid))
                identities = cursor.fetchall()
                exact = next((row for row in identities
                    if int(row["telegram_user_id"]) == int(intent["telegram_user_id"])
                    and int(row["fanvue_account_id"]) == int(fanvue_account_id)
                    and UUID(str(row["external_fanvue_user_uuid"])) == buyer_uuid
                    and row["verification_status"] == "VERIFIED" and row["is_active"]), None)
                if identities and exact is None:
                    raise ValueError("Telegram/Fanvue mapping conflict.")
                if exact is None:
                    evidence = {"purchase_intent_id": str(intent["purchase_intent_id"]),
                        "fingerprint_reservation_id": str(match["fingerprint_reservation_id"]),
                        "transaction_id": transaction_id, "currency": currency,
                        "gross_minor": gross_minor, "accepted_forwarding_risk": True}
                    cursor.execute("""INSERT INTO public.telegram_identity_map (
                        telegram_user_id,telegram_chat_id,fanvue_account_id,local_fanvue_user_id,
                        external_fanvue_user_uuid,verification_status,verification_method,
                        verified_at,verified_by,verification_evidence,last_observed_username,
                        last_observed_display_name) VALUES (%s,%s,%s,%s,%s,'VERIFIED',%s,NOW(),
                        'COMMERCE_RECONCILIATION',%s::jsonb,%s,%s) RETURNING *""",
                        (intent["telegram_user_id"], observation["telegram_chat_id"], fanvue_account_id,
                         local_fanvue_user_id, buyer_uuid, self.PROVENANCE,
                         json.dumps(evidence), observation.get("username"), observation.get("display_name")))
                    exact = cursor.fetchone()
                    cursor.execute("""INSERT INTO public.telegram_identity_verification_audit (
                        audit_id,telegram_identity_mapping_id,telegram_user_id,fanvue_account_id,
                        local_fanvue_user_id,external_fanvue_user_uuid,action,verification_method,
                        operator_source,evidence) VALUES (%s,%s,%s,%s,%s,%s,'VERIFIED',%s,
                        'COMMERCE_RECONCILIATION',%s::jsonb)""", (uuid4(), exact["id"],
                        intent["telegram_user_id"], fanvue_account_id, local_fanvue_user_id,
                        buyer_uuid, self.PROVENANCE, json.dumps(evidence)))
                self._checkpoint("mapping")
                cursor.execute("""UPDATE public.purchase_intents SET status='PURCHASED',
                    telegram_identity_mapping_id=%s,external_fanvue_user_uuid=%s,
                    provider_transaction_order_id=COALESCE(provider_transaction_order_id,%s),
                    provider_payment_id=COALESCE(provider_payment_id,%s),
                    provider_event_id=COALESCE(provider_event_id,%s),purchased_at=COALESCE(purchased_at,%s),
                    attribution_result='ATTRIBUTED',attribution_reason=%s,
                    actual_charged_price_minor=%s,updated_at=NOW()
                    WHERE purchase_intent_id=%s RETURNING *""", (exact["id"], buyer_uuid,
                    transaction_id, payment_id, event_id, purchased_at, self.PROVENANCE,
                    gross_minor, intent["purchase_intent_id"]))
                settled_intent = cursor.fetchone()
                self._checkpoint("intent")
                cursor.execute("""UPDATE public.fanvue_fingerprint_reservations SET state='PURCHASED',
                    purchased_at=COALESCE(purchased_at,%s),provider_transaction_reference=COALESCE(provider_transaction_reference,%s)
                    WHERE fingerprint_reservation_id=%s AND (provider_transaction_reference IS NULL OR provider_transaction_reference=%s)""",
                    (purchased_at, transaction_id, match["fingerprint_reservation_id"], transaction_id))
                cursor.execute("UPDATE public.fanvue_runtime_media_links SET state='PURCHASED' WHERE runtime_media_link_id=%s",
                               (match["runtime_media_link_id"],))
                cursor.execute("""UPDATE public.telegram_unlock_grants SET
                    state='REVOKED',revoked_at=COALESCE(revoked_at,NOW()),
                    audit_metadata=audit_metadata || jsonb_build_object(
                      'purchaseSettlementTransactionId',%s::text,
                      'purchaseSettledAt',%s::text)
                    WHERE purchase_intent_id=%s AND state='ACTIVE'""",
                    (transaction_id, purchased_at, intent["purchase_intent_id"]))
                cursor.execute("""INSERT INTO public.provider_purchase_asset_ownership(
                    ownership_id,creator_profile_id,fanvue_account_id,
                    external_fanvue_user_uuid,provider_transaction_id,
                    provider_resource_id,content_item_id,purchase_timestamp,evidence)
                    SELECT %s,offering.creator_profile_id,%s,%s,%s,
                           runtime.provider_media_link_uuid,member.asset_id,%s,
                           %s::jsonb
                    FROM public.commercial_offerings offering
                    JOIN public.commercial_offering_assets member
                      ON member.offering_id=offering.offering_id
                    JOIN public.fanvue_runtime_media_links runtime
                      ON runtime.runtime_media_link_id=%s
                    WHERE offering.offering_id=%s
                    ON CONFLICT(fanvue_account_id,provider_transaction_id,content_item_id)
                    DO NOTHING""", (uuid4(), fanvue_account_id, buyer_uuid,
                    transaction_id, purchased_at, json.dumps({
                        "authority": self.PROVENANCE,
                        "purchase_intent_id": str(intent["purchase_intent_id"]),
                        "fingerprint_reservation_id": str(match["fingerprint_reservation_id"]),
                    }), match["runtime_media_link_id"], intent["commercial_offering_id"]))
                self._checkpoint("fingerprint")
                if prospect is not None:
                    if prospect.get("graduated_mapping_id") not in (None, exact["id"]):
                        raise ValueError("Prospect mapping conflict.")
                    cursor.execute("""UPDATE public.telegram_sales_prospects SET
                        graduated_mapping_id=%s,graduated_at=COALESCE(graduated_at,NOW()),last_observed_at=NOW()
                        WHERE telegram_sales_prospect_id=%s""", (exact["id"], prospect["telegram_sales_prospect_id"]))
                self._checkpoint("prospect")
                session = self._graduate_session(cursor, intent=settled_intent,
                    mapping=exact, buyer_uuid=buyer_uuid, gross_minor=gross_minor)
                self._checkpoint("session")
                mapping = TelegramIdentityMapping.from_row(exact)
                self._checkpoint("before_commit")
                return {"mapping": mapping, "intent": dict(settled_intent),
                        "match": dict(match), "provisional_session": session}

    def _graduate_session(self, cursor, *, intent, mapping, buyer_uuid, gross_minor):
        cursor.execute("SELECT * FROM public.telegram_provisional_sales_sessions WHERE first_purchase_intent_id=%s FOR UPDATE",
                       (intent["purchase_intent_id"],))
        provisional = cursor.fetchone()
        if provisional is None:
            return None
        if provisional["state"] == "GRADUATED":
            return dict(provisional)
        cursor.execute("""SELECT * FROM public.sales_sessions WHERE creator_profile_id=%s
            AND fanvue_account_id=%s AND fanvue_user_id=%s
            AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING') FOR UPDATE""",
            (intent["creator_profile_id"], intent["fanvue_account_id"], mapping["local_fanvue_user_id"]))
        existing = cursor.fetchone()
        if existing and existing["commercial_foundation_reference"] != provisional["photoshoot_reference"]:
            raise ValueError("Existing canonical Session conflicts with provisional Session.")
        session_id = existing["sales_session_id"] if existing else uuid4()
        if existing is None:
            context = dict(provisional.get("commercial_context") or {})
            context.update({"configuredBasePriceMinor": provisional["configured_base_price_minor"],
                            "actualFingerprintPriceMinor": gross_minor,
                            "provisionalSessionId": str(provisional["provisional_session_id"])})
            cursor.execute("""INSERT INTO public.sales_sessions (sales_session_id,creator_profile_id,
                fanvue_account_id,fanvue_user_id,external_fanvue_user_uuid,telegram_identity_mapping_id,
                commercial_foundation_type,commercial_foundation_reference,state,progression_stage,
                objective,commercial_context,started_by_type,started_by_identifier)
                VALUES (%s,%s,%s,%s,%s,%s,'PHOTOSHOOT',%s,'CONTINUING','PROGRESSION',
                'Fingerprint bootstrap Session',%s::jsonb,'AI','PrivateChatPurchaseSettlementService')""",
                (session_id, intent["creator_profile_id"], intent["fanvue_account_id"],
                 mapping["local_fanvue_user_id"], buyer_uuid, mapping["id"],
                 provisional["photoshoot_reference"], json.dumps(context, default=str)))
            self._checkpoint("canonical_session")
        cursor.execute("""INSERT INTO public.sales_session_purchase_intents
            (sales_session_id,purchase_intent_id,sequence_index) VALUES (%s,%s,1)
            ON CONFLICT (purchase_intent_id) DO NOTHING""", (session_id, intent["purchase_intent_id"]))
        cursor.execute("""UPDATE public.telegram_provisional_sales_sessions SET state='GRADUATED',
            mapped_sales_session_id=%s,actual_fingerprint_price_minor=%s,
            first_purchase_recorded_at=COALESCE(first_purchase_recorded_at,NOW()),
            current_position=GREATEST(current_position,2),progression_stage='PROGRESSION',
            graduated_at=COALESCE(graduated_at,NOW()),updated_at=NOW()
            WHERE provisional_session_id=%s RETURNING *""",
            (session_id, gross_minor, provisional["provisional_session_id"]))
        result = cursor.fetchone()
        self._checkpoint("provisional_session")
        self._checkpoint("session_advancement")
        return dict(result)
