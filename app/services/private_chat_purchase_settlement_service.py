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
                # Share the buyer lock with successor creation before acquiring
                # reservation and intent rows (consistent lock ordering).
                from app.services.evergreen_purchase_attribution import family_target
                probe = connection.execute("""SELECT purchase_intent_id FROM fanvue_fingerprint_reservations
                    WHERE fanvue_account_id=%s AND currency=%s AND exact_price_minor=%s""",
                    (fanvue_account_id, currency, gross_minor)).fetchone()
                if probe:
                    family_target(connection, probe['purchase_intent_id'])
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
                target_id = family_target(connection, match["purchase_intent_id"], create_receipt_intent=True)
                cursor.execute("SELECT * FROM public.purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",
                               (target_id,))
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
                    (transaction_id, purchased_at, match["purchase_intent_id"]))
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
                reconciled_session = self._reconcile_sales_session(
                    cursor,
                    intent=settled_intent,
                    mapping=exact,
                    buyer_uuid=buyer_uuid,
                    transaction_id=transaction_id,
                )
                self._checkpoint("session_reconciliation")
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
                        "match": dict(match), "provisional_session": session,
                        "sales_session": reconciled_session}

    def _reconcile_sales_session(
        self, cursor, *, intent, mapping, buyer_uuid, transaction_id,
    ):
        """Release an exactly bound Session after provider-backed settlement.

        This runs inside the settlement transaction so purchase, attribution,
        ownership, and the Session envelope cannot permanently disagree.  The
        photoshoot strategy/ownership state remains authoritative for whether
        the Session continues or is complete.
        """
        cursor.execute(
            """SELECT session.*
               FROM public.sales_session_purchase_intents link
               JOIN public.sales_sessions session
                 ON session.sales_session_id=link.sales_session_id
               WHERE link.purchase_intent_id=%s
               FOR UPDATE OF session""",
            (UUID(str((intent.get("created_metadata") or {}).get("evergreen_original_intent_id") or intent["purchase_intent_id"])),),
        )
        session = cursor.fetchone()
        if session is None:
            return None
        if (
            int(session["creator_profile_id"]) != int(intent["creator_profile_id"])
            or int(session["fanvue_account_id"]) != int(intent["fanvue_account_id"])
            or int(session["fanvue_user_id"]) != int(mapping["local_fanvue_user_id"])
            or UUID(str(session["external_fanvue_user_uuid"])) != buyer_uuid
            or str(session["commercial_foundation_type"]) != "PHOTOSHOOT"
            or not session["commercial_foundation_reference"]
        ):
            return dict(session)
        if session["state"] != "AWAITING_PAYMENT":
            return dict(session)

        cursor.execute(
            """SELECT asset_id FROM public.commercial_offering_assets
               WHERE offering_id=%s ORDER BY position,asset_id""",
            (intent["commercial_offering_id"],),
        )
        offering_assets = tuple(int(row["asset_id"]) for row in cursor.fetchall())
        if not offering_assets:
            return dict(session)
        cursor.execute(
            """SELECT asset_id FROM public.photoshoot_asset_memberships
               WHERE photoshoot_session_id=%s AND approved=TRUE
                 AND asset_id=ANY(%s)""",
            (str(session["commercial_foundation_reference"]), list(offering_assets)),
        )
        foundation_assets = {int(row["asset_id"]) for row in cursor.fetchall()}
        if foundation_assets != set(offering_assets):
            return dict(session)
        cursor.execute(
            """SELECT content_item_id FROM public.provider_purchase_asset_ownership
               WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s
                 AND provider_transaction_id=%s
                 AND content_item_id=ANY(%s)""",
            (
                intent["fanvue_account_id"], buyer_uuid, transaction_id,
                list(offering_assets),
            ),
        )
        if {int(row["content_item_id"]) for row in cursor.fetchall()} != set(offering_assets):
            return dict(session)

        cursor.execute(
            """SELECT strategy_data
               FROM public.photoshoot_session_sales_strategies
               WHERE photoshoot_session_id=%s AND creator_profile_id=%s
                 AND status='READY'
               ORDER BY generated_at DESC,strategy_version DESC LIMIT 1""",
            (
                str(session["commercial_foundation_reference"]),
                intent["creator_profile_id"],
            ),
        )
        strategy = cursor.fetchone()
        if strategy is None:
            return dict(session)
        shots = tuple(dict(value) for value in dict(
            strategy["strategy_data"] or {}
        ).get("shots", ()))
        strategy_assets = {
            int(shot["asset_id"]) for shot in shots if shot.get("asset_id") is not None
        }
        if not strategy_assets or not set(offering_assets).issubset(strategy_assets):
            return dict(session)
        cursor.execute(
            """SELECT content_item_id
               FROM public.provider_purchase_asset_ownership
               WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s
                 AND content_item_id=ANY(%s)""",
            (intent["fanvue_account_id"], buyer_uuid, list(strategy_assets)),
        )
        advanced = {int(row["content_item_id"]) for row in cursor.fetchall()}
        free_assets = {
            int(shot["asset_id"]) for shot in shots
            if str(shot.get("access_recommendation") or "").upper() == "FREE"
        }
        if free_assets:
            cursor.execute(
                """SELECT DISTINCT event.asset_id
                   FROM public.customer_photoshoot_lifecycle_events event
                   JOIN public.customer_photoshoot_lifecycles lifecycle
                     ON lifecycle.lifecycle_id=event.lifecycle_id
                   JOIN public.customer_commerce_profiles customer
                     ON customer.customer_commerce_profile_id=
                        lifecycle.customer_commerce_profile_id
                   WHERE lifecycle.creator_profile_id=%s
                     AND lifecycle.photoshoot_id=%s
                     AND customer.external_fanvue_user_uuid=%s
                     AND event.event_type='PRESENTED'
                     AND event.asset_id=ANY(%s)""",
                (
                    intent["creator_profile_id"],
                    str(session["commercial_foundation_reference"]),
                    buyer_uuid, list(free_assets),
                ),
            )
            advanced.update(int(row["asset_id"]) for row in cursor.fetchall())

        terminal = strategy_assets.issubset(advanced)
        new_state = "COMPLETED" if terminal else "CONTINUING"
        new_stage = "FINALE" if terminal else session["progression_stage"]
        outcome = "COMPLETED_WITH_PURCHASE" if terminal else None
        reason = (
            "Final provider-settled Session step completed the ordered experience."
            if terminal else
            "Provider-settled Session step released payment wait for continuation."
        )
        cursor.execute(
            """UPDATE public.sales_sessions SET state=%s,progression_stage=%s,
                   outcome=%s,terminal_reason=%s,last_activity_at=NOW(),
                   ended_at=CASE WHEN %s THEN NOW() ELSE NULL END,updated_at=NOW()
               WHERE sales_session_id=%s AND state='AWAITING_PAYMENT'
               RETURNING *""",
            (
                new_state, new_stage, outcome, reason if terminal else None,
                terminal, session["sales_session_id"],
            ),
        )
        updated = cursor.fetchone()
        if updated is None:
            return dict(session)
        cursor.execute(
            """INSERT INTO public.sales_session_history (
                   sales_session_id,creator_profile_id,event_type,
                   previous_state,new_state,previous_progression_stage,
                   new_progression_stage,purchase_intent_id,actor_type,
                   actor_identifier,reason
               ) VALUES (%s,%s,'PURCHASE_SETTLED',%s,%s,%s,%s,%s,
                         'SYSTEM','PrivateChatPurchaseSettlementService',%s)""",
            (
                updated["sales_session_id"], updated["creator_profile_id"],
                session["state"], updated["state"],
                session["progression_stage"], updated["progression_stage"],
                intent["purchase_intent_id"], reason,
            ),
        )
        return dict(updated)

    def _graduate_session(self, cursor, *, intent, mapping, buyer_uuid, gross_minor):
        cursor.execute("SELECT * FROM public.telegram_provisional_sales_sessions WHERE first_purchase_intent_id=%s FOR UPDATE",
                       (UUID(str((intent.get("created_metadata") or {}).get("evergreen_original_intent_id") or intent["purchase_intent_id"])),))
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
        context = dict(provisional.get("commercial_context") or {})
        context.update({"configuredBasePriceMinor": provisional["configured_base_price_minor"],
                        "actualFingerprintPriceMinor": gross_minor,
                        "provisionalSessionId": str(provisional["provisional_session_id"])})
        if existing is None:
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
        else:
            # A Session may already have been opened by the first structured
            # presentation.  Graduation must still carry forward the exact
            # provider-confirmed free-step receipt from its provisional
            # envelope; otherwise restart-safe runtime reconstruction sees the
            # intentionally unowned FREE asset as available forever.
            cursor.execute(
                """UPDATE public.sales_sessions
                   SET commercial_context=COALESCE(commercial_context,'{}'::jsonb)
                       || %s::jsonb,updated_at=NOW()
                   WHERE sales_session_id=%s""",
                (json.dumps(context, default=str), session_id),
            )
        lifecycle = self._resolve_graduated_photoshoot_lifecycle(
            cursor, provisional=provisional, intent=intent,
            buyer_uuid=buyer_uuid, sales_session_id=session_id,
        )
        self._checkpoint("photoshoot_lifecycle")
        self._transfer_confirmed_free_step(
            cursor, provisional=provisional, intent=intent,
            lifecycle=lifecycle, sales_session_id=session_id,
        )
        self._transfer_first_paid_step(
            cursor, intent=intent, lifecycle=lifecycle,
            sales_session_id=session_id,
        )
        cursor.execute("""INSERT INTO public.sales_session_purchase_intents
            (sales_session_id,purchase_intent_id,sequence_index) VALUES (%s,%s,1)
            ON CONFLICT (purchase_intent_id) DO NOTHING""", (session_id,
                UUID(str((intent.get("created_metadata") or {}).get("evergreen_original_intent_id") or intent["purchase_intent_id"]))))
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

    @staticmethod
    def _resolve_graduated_photoshoot_lifecycle(
        cursor, *, provisional, intent, buyer_uuid, sales_session_id,
    ):
        from app.repositories.customer_photoshoot_lifecycle_repository import (
            CustomerPhotoshootLifecycleRepository,
        )

        cursor.execute(
            """INSERT INTO public.customer_commerce_profiles (
                   customer_commerce_profile_id,creator_profile_id,
                   fanvue_account_id,external_fanvue_user_uuid,
                   first_seen_at,last_seen_at)
               VALUES (%s,%s,%s,%s,COALESCE(%s,NOW()),COALESCE(%s,NOW()))
               ON CONFLICT (creator_profile_id,external_fanvue_user_uuid)
               DO UPDATE SET last_seen_at=GREATEST(
                   customer_commerce_profiles.last_seen_at,
                   EXCLUDED.last_seen_at)
               RETURNING customer_commerce_profile_id,fanvue_account_id""",
            (
                uuid4(), intent["creator_profile_id"],
                intent["fanvue_account_id"], buyer_uuid,
                intent.get("purchased_at"), intent.get("purchased_at"),
            ),
        )
        customer = cursor.fetchone()
        if (
            customer is None
            or int(customer["fanvue_account_id"])
                != int(intent["fanvue_account_id"])
        ):
            raise ValueError(
                "Photoshoot Session graduation requires an exact customer commerce profile."
            )
        lifecycle = CustomerPhotoshootLifecycleRepository.resolve_with_cursor(
            cursor,
            creator_profile_id=intent["creator_profile_id"],
            customer_commerce_profile_id=customer["customer_commerce_profile_id"],
            photoshoot_id=str(provisional["photoshoot_reference"]),
            selected_offering_id=intent["commercial_offering_id"],
            recommendation_reason="PROVIDER_BACKED_FIRST_SESSION_PURCHASE",
            metadata={
                "authority": "PRIVATE_CHAT_PURCHASE_SETTLEMENT",
                "provisional_session_id": str(
                    provisional["provisional_session_id"]
                ),
            },
        )
        if lifecycle is None or lifecycle["status"] not in {"ACTIVE", "OBJECTION"}:
            raise ValueError(
                "Photoshoot Session graduation requires an active durable lifecycle."
            )
        cursor.execute(
            """INSERT INTO public.customer_photoshoot_lifecycle_sessions
               (lifecycle_id,sales_session_id) VALUES (%s,%s)
               ON CONFLICT DO NOTHING""",
            (lifecycle["lifecycle_id"], sales_session_id),
        )
        cursor.execute(
            """UPDATE public.customer_photoshoot_lifecycles
               SET first_sales_session_id=COALESCE(first_sales_session_id,%s),
                   last_sales_session_id=%s,last_purchase_intent_id=%s,
                   last_activity_at=NOW(),updated_at=NOW()
               WHERE lifecycle_id=%s""",
            (
                sales_session_id, sales_session_id,
                intent["purchase_intent_id"], lifecycle["lifecycle_id"],
            ),
        )
        return lifecycle

    @staticmethod
    def _transfer_confirmed_free_step(
        cursor, *, provisional, intent, lifecycle, sales_session_id,
    ):
        """Project a confirmed provisional FREE delivery into lifecycle coverage.

        Paid progression remains ownership-backed.  This event is the durable,
        restart-safe consumption authority only for a canonically validated
        FREE_TEASER and never grants paid ownership.
        """
        delivery = dict(
            dict(provisional.get("commercial_context") or {}).get(
                "freeTeaserDelivery"
            ) or {}
        )
        if (
            str(delivery.get("salesRole") or "").upper() != "FREE_TEASER"
            or delivery.get("assetId") is None
            or not str(delivery.get("providerDeliveryId") or "").strip()
        ):
            return
        provider = str(delivery.get("provider") or "PROVISIONAL_SESSION_DELIVERY")
        provider_delivery_id = str(delivery["providerDeliveryId"])
        asset_id = int(delivery["assetId"])
        cursor.execute(
            """SELECT 1 FROM public.customer_photoshoot_lifecycle_events
               WHERE lifecycle_id=%s AND event_type='PRESENTED'
                 AND asset_id=%s AND provider=%s AND provider_delivery_id=%s""",
            (lifecycle["lifecycle_id"], asset_id, provider, provider_delivery_id),
        )
        if cursor.fetchone() is not None:
            return
        cursor.execute(
            """INSERT INTO public.customer_photoshoot_lifecycle_events (
                   lifecycle_id,event_type,previous_status,new_status,asset_id,
                   sales_session_id,provider,provider_delivery_id,metadata)
               VALUES (%s,'PRESENTED',%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT DO NOTHING""",
            (
                lifecycle["lifecycle_id"], lifecycle["status"],
                lifecycle["status"], asset_id, sales_session_id, provider,
                provider_delivery_id, json.dumps({
                    "authority": "CONFIRMED_PROVISIONAL_FREE_TEASER_DELIVERY",
                    "access_recommendation": "FREE",
                    "sales_role": "FREE_TEASER",
                    "provisional_session_id": str(
                        provisional["provisional_session_id"]
                    ),
                }),
            ),
        )

    @staticmethod
    def _transfer_first_paid_step(
        cursor, *, intent, lifecycle, sales_session_id,
    ):
        """Persist exact first provider purchase as lifecycle coverage once."""
        cursor.execute(
            """SELECT member.asset_id
               FROM public.commercial_offering_assets member
               JOIN public.photoshoot_asset_memberships membership
                 ON membership.asset_id=member.asset_id
                AND membership.photoshoot_session_id=%s
                AND membership.approved=TRUE
               WHERE member.offering_id=%s ORDER BY member.position,member.asset_id""",
            (
                str(lifecycle["photoshoot_id"]),
                intent["commercial_offering_id"],
            ),
        )
        asset_ids = tuple(int(row["asset_id"]) for row in cursor.fetchall())
        if not asset_ids:
            raise ValueError(
                "First Session purchase does not bind to the graduated photoshoot."
            )
        for asset_id in asset_ids:
            cursor.execute(
                """SELECT 1 FROM public.customer_photoshoot_lifecycle_events
                   WHERE lifecycle_id=%s AND event_type='PURCHASED'
                     AND asset_id=%s AND purchase_intent_id=%s""",
                (
                    lifecycle["lifecycle_id"], asset_id,
                    intent["purchase_intent_id"],
                ),
            )
            if cursor.fetchone() is not None:
                continue
            cursor.execute(
                """INSERT INTO public.customer_photoshoot_lifecycle_events (
                       lifecycle_id,event_type,previous_status,new_status,asset_id,
                       purchase_outcome_id,sales_session_id,purchase_intent_id,
                       metadata)
                   VALUES (%s,'PURCHASED',%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT DO NOTHING""",
                (
                    lifecycle["lifecycle_id"], lifecycle["status"],
                    lifecycle["status"], asset_id,
                    intent["purchase_intent_id"], sales_session_id,
                    intent["purchase_intent_id"], json.dumps({
                        "authority": "PROVIDER_BACKED_FIRST_SESSION_PURCHASE",
                        "commercial_offering_id": str(
                            intent["commercial_offering_id"]
                        ),
                    }),
                ),
            )
