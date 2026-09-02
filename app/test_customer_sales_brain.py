from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import customer_sales_brain as api
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.models.commercial_offering_selection import (
    OfferingSelectionReason,
    SelectedOfferingResult,
    immutable_selector_metadata,
)
from app.models.commercial_intelligence import (
    CommercialIntelligenceContext,
    OwnershipCoverage,
)
from app.models.purchase_intent import (
    AttributionResult,
    PurchaseIntentStatus,
)
from app.models.photoshoot_experience_recommendation import (
    PhotoshootExperienceRecommendation,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService


def test_historical_session_resolution_matches_customer_and_photoshoot():
    unrelated_latest = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-1",
        commercial_foundation_reference="photoshoot-new",
    )
    matching_older = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-1",
        commercial_foundation_reference="photoshoot-requested",
    )
    other_customer = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-2",
        commercial_foundation_reference="photoshoot-requested",
    )

    result = CustomerSalesBrainService._resolve_historical_session(
        (unrelated_latest, other_customer, matching_older),
        fanvue_account_id=2,
        fanvue_user_id="buyer-1",
        intended_photoshoot_reference="photoshoot-requested",
    )

    assert result is matching_older


NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
BUYER = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


class Customers:
    def __init__(self, profile):
        self.profile = profile

    def get_by_buyer_uuid(self, **kwargs):
        return self.profile

    def list_profiles(self, **kwargs):
        return ((self.profile,) if self.profile else ()), int(bool(self.profile)), 1


class Identities:
    def __init__(self, resolved=True):
        self.resolved = resolved

    def get_by_telegram_user_id(self, user):
        return SimpleNamespace(
            fanvue_account_id=7, external_fanvue_user_uuid=BUYER,
            telegram_user_id=user,
        ) if self.resolved else None


class Intents:
    def __init__(self, latest=None, active=None):
        self.latest, self.active = latest, active

    def get_latest_for_buyer(self, **kwargs):
        return self.latest

    def get_active_for_buyer(self, **kwargs):
        return self.active

    def mark_abandoned(self, purchase_intent_id, **kwargs):
        assert self.active is not None
        assert purchase_intent_id == self.active.purchase_intent_id
        self.active = None


class Signals:
    def __init__(self, signal):
        self.signal = signal

    def get_signal(self, **kwargs):
        return self.signal


class Selector:
    def __init__(self, offering=None):
        self.offering = offering
        self.calls = []

    def select(self, **kwargs):
        self.calls.append(kwargs)
        item = self.offering
        return SelectedOfferingResult(
            offering_id=item.offering_id if item else None,
            publication_id=item.publication_id if item else None,
            publication_provider="FANVUE" if item else None,
            delivery_url=item.delivery_url if item else None,
            offering_type="SINGLE_IMAGE" if item else None,
            primary_sales_channel="AI_CHAT" if item else None,
            selection_reason=(
                OfferingSelectionReason.MOST_RECENT
                if item else OfferingSelectionReason.NO_ELIGIBLE_OFFERING
            ),
            exclusion_reasons=(), evaluations=(),
            selector_metadata=immutable_selector_metadata({}),
            title=getattr(item, "title", None) if item else None,
            short_description=(
                getattr(item, "description", None) if item else None
            ),
            price_minor=getattr(item, "price_minor", None) if item else None,
            currency=getattr(item, "currency", None) if item else None,
            photoshoot_experience=(
                getattr(item, "photoshoot_experience", None) if item else None
            ),
        )


def profile(*, purchases=0, last_purchase=None, linked=True):
    return SimpleNamespace(
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_user_uuid=BUYER,
        telegram_user_id=22 if linked else None,
        telegram_identity_mapping_id=11 if linked else None,
        purchase_count=purchases, lifetime_gross_minor=purchases * 999,
        last_purchase_at=last_purchase,
    )


def signal(*, reconciliation=None, attribution="PENDING", conversion="NO_ACTIVE_OFFER"):
    return SimpleNamespace(
        buyer_uuid=str(BUYER), telegram_user_id=22, identity_resolved=True,
        lifetime_spend_minor=999, purchase_count=1,
        last_purchase_at=NOW - timedelta(days=2),
        current_active_offer_id=None, current_offer_status=None,
        conversion_state=conversion, latest_transaction="order-1",
        attribution_state=attribution, reconciliation_state=reconciliation,
    )


def intent(*, status="PRESENTED", presented_at=None, attribution="PENDING"):
    return SimpleNamespace(
        purchase_intent_id=uuid4(), commercial_offering_id=uuid4(),
        status=PurchaseIntentStatus(status),
        attribution_result=AttributionResult(attribution),
        created_at=NOW - timedelta(hours=2),
        presented_at=presented_at or NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=1),
        expected_price_minor=999,
    )


def test_active_offer_price_objection_routes_to_constrained_alternative():
    current = intent(status="PRESENTED")
    alternative = offering()
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=alternative)
    result = evaluate(service, {"latest_message": "anything cheaper?"})
    assert result.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
    assert result.reason_code is CustomerSalesReasonCode.PRICE_RECOVERY
    constraints = service.offering_selector.calls[-1]["strategy_constraints"]
    assert constraints.excluded_offering_ids == (current.commercial_offering_id,)
    assert constraints.maximum_price_minor == 899
    assert result.decision_metadata["commercialObjection"]["type"] == "PRICE_RESISTANCE"


def test_soft_price_objection_defends_original_offer_once_without_downsell():
    current = intent(status="PRESENTED")
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=offering())
    result = evaluate(service, {
        "latest_message": "That's more than I wanted to spend.",
        "sales_progression": {"phase": "PRESENT_OFFER", "recoveryAttemptCount": 0},
    })
    recovery = result.decision_metadata["objectionRecovery"]
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.OBJECTION_VALUE_DEFENSE
    assert recovery["strategy"] == "VALUE_DEFENSE"
    assert recovery["originalOfferPreserved"] is True
    assert recovery["originalPrice"] == 999
    assert recovery["alternativeSelected"] is False
    assert recovery["noDynamicDiscount"] is True
    assert recovery["falseScarcityAllowed"] is False
    assert service.intents.active is current
    assert service.offering_selector.calls == []


def test_discount_request_holds_original_price_without_product_downsell():
    current = intent(status="PRESENTED")
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=offering())
    result = evaluate(service, {"latest_message": "Come on, give it to me for $5"})
    objection = result.decision_metadata["commercialObjection"]
    assert objection["type"] == "DISCOUNT_REQUEST"
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.decision_metadata["objectionRecovery"]["originalPrice"] == 999
    assert service.offering_selector.calls == []


def test_explicit_budget_after_value_defense_authorizes_different_product():
    current = intent(status="PRESENTED")
    alternative = offering(); alternative.price_minor = 500
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=alternative)
    result = evaluate(service, {
        "latest_message": "No seriously, I only have $5.",
        "sales_progression": {"phase": "PRESENT_OFFER", "recoveryAttemptCount": 1},
    })
    objection = result.decision_metadata["commercialObjection"]
    constraints = service.offering_selector.calls[-1]["strategy_constraints"]
    assert objection["type"] == "BUDGET_LIMIT"
    assert objection["budgetConstraintAmount"] == 500
    assert constraints.maximum_price_minor == 500
    assert result.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
    assert result.recommended_offering_id == alternative.offering_id
    assert service.intents.active is None


def test_clear_global_rejection_never_uses_negative_contact():
    current = intent(status="PRESENTED")
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=offering())
    result = evaluate(service, {"latest_message": "Stop selling me stuff."})
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.decision_metadata["commercialObjection"]["type"] == "GLOBAL_DECLINE"
    assert result.decision_metadata["commercialObjection"]["negativeContactAuthorized"] is False
    assert service.offering_selector.calls == []


def test_contextual_hard_boundary_overrides_verified_buyer_value():
    result = evaluate(brain(customer=profile(purchases=8), commerce_signal=signal()), {
        "latest_message": "leave me alone",
        "contextual_customer_tone": {
            "hostilityLevel": "HIGH", "explicitDisengagement": True,
        },
    })
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.reason_code is CustomerSalesReasonCode.CUSTOMER_DECLINED


def test_current_backoff_requires_fresh_direct_reentry():
    service = brain(customer=profile(), commerce_signal=signal(), eligible=offering())
    vague = evaluate(service, {
        "latest_message": "whatever",
        "sales_progression": {"phase": "BACK_OFF"},
    })
    assert vague.decision is CustomerSalesDecisionType.BACK_OFF
    direct = evaluate(service, {
        "latest_message": "what private sets do you have?",
        "sales_progression": {"phase": "BACK_OFF"},
    })
    assert direct.decision is not CustomerSalesDecisionType.BACK_OFF


def test_repeated_abuse_after_backoff_requests_no_response_but_direct_reentry_does_not():
    service = brain(customer=profile(), commerce_signal=signal(), eligible=offering())
    abusive = evaluate(service, {
        "latest_message": "answer me, your nonsense is disgusting",
        "sales_progression": {"phase": "BACK_OFF"},
        "contextual_customer_tone": {
            "hostilityLevel": "HIGH", "repeatedHostility": True,
            "rageBaitPattern": True, "commercialCuriosity": False,
            "buyingIntent": False, "priceObjection": False,
        },
    })
    assert abusive.decision is CustomerSalesDecisionType.BACK_OFF
    assert abusive.decision_metadata["outboundSuppression"] == {
        "suppressed": True,
        "outcome": "NO_RESPONSE",
        "reason": "REPEATED_HOSTILITY_AFTER_BACK_OFF",
        "inboundProcessingRequired": True,
        "futureCommercialReentryAllowed": True,
        "freshCommercialIntentDetected": False,
        "nurtureBypassedForCommercialIntent": False,
    }
    direct = evaluate(service, {
        "latest_message": "what private sets do you have?",
        "sales_progression": {"phase": "BACK_OFF"},
        "contextual_customer_tone": {
            "hostilityLevel": "NONE", "repeatedHostility": True,
            "rageBaitPattern": True, "commercialCuriosity": True,
            "buyingIntent": True, "priceObjection": False,
        },
    })
    assert direct.decision is not CustomerSalesDecisionType.BACK_OFF
    assert direct.decision_metadata["outboundSuppression"]["suppressed"] is False


def test_verified_buyer_value_remains_visible_but_repeated_abuse_is_suppressed():
    result = evaluate(brain(customer=profile(purchases=8), commerce_signal=signal()), {
        "latest_message": "answer me, your nonsense is disgusting",
        "contextual_customer_tone": {
            "hostilityLevel": "HIGH", "repeatedHostility": True,
            "rageBaitPattern": True, "priorExplicitDisengagementCount": 1,
            "commercialCuriosity": False, "buyingIntent": False,
            "priceObjection": False,
        },
    })
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.decision_metadata["outboundSuppression"]["suppressed"] is True
    assert result.external_fanvue_buyer_uuid == BUYER
    assert result.commerce_signal["purchaseCount"] == 1


def test_active_offer_technical_failure_does_not_select_another_offer():
    current = intent(status="PRESENTED")
    service = brain(customer=profile(), commerce_signal=signal(),
                    latest=current, active=current, eligible=offering())
    result = evaluate(service, {"latest_message": "the link doesn't work"})
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.PAYMENT_SUPPORT_REQUIRED
    assert service.offering_selector.calls == []


def test_recent_abandoned_offer_backs_off_without_replacement():
    recent = intent(status="ABANDONED")
    result = evaluate(brain(
        customer=profile(), latest=recent, eligible=offering(),
    ))
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.reason_code is CustomerSalesReasonCode.CUSTOMER_DECLINED
    assert result.recommended_offering_id is None


def offering():
    return SimpleNamespace(
        offering_id=uuid4(), publication_id=uuid4(),
        delivery_url="https://fanvue.com/media-link",
        title="Private Release", description="A private image.",
        price_minor=999, currency="USD",
    )


def test_sales_brain_returns_photoshoot_experience_with_offering_fulfillment():
    selected = offering()
    selected.photoshoot_experience = PhotoshootExperienceRecommendation(
        photoshoot_id="photoshoot-sunday-porch",
        title="Sunday Porch",
        theme="warm porch",
        description="A slow Sunday morning with Ava.",
        hero_asset_id=42,
        supporting_asset_ids=(43, 44),
        photoshoot_intelligence={"themes": ("warm porch",)},
        commercial_offering_id=selected.offering_id,
        commercial_publication_id=selected.publication_id,
        delivery_url=selected.delivery_url,
        recommendation_score=0.91,
        recommendation_explanation="Selected using semantic match and affinity.",
        fulfillment_offering_type="PHOTOSET",
        fulfillment_price_minor=selected.price_minor,
        fulfillment_currency=selected.currency,
    )
    service = brain(
        customer=profile(),
        commerce_signal=signal(),
        eligible=selected,
    )

    result = service.evaluate_for_telegram_user(
        creator_profile_id=2, telegram_user_id=22
    )
    payload = api._payload(result)

    assert result.recommended_offering_id == selected.offering_id
    assert result.recommended_photoshoot_experience.photoshoot_id == (
        "photoshoot-sunday-porch"
    )
    assert payload["recommendedPhotoshootExperience"]["title"] == "Sunday Porch"
    assert payload["recommendedPhotoshootExperience"]["commercialOfferingId"] == str(
        selected.offering_id
    )


def brain(*, customer=None, identity=True, commerce_signal=None,
          latest=None, active=None, eligible=None):
    return CustomerSalesBrainService(
        customer_repository=Customers(customer),
        identity_repository=Identities(identity),
        intent_repository=Intents(latest, active),
        commerce_signal_service=Signals(commerce_signal),
        offering_selector_service=Selector(eligible),
        config=CustomerSalesBrainConfig(
            purchase_cooldown=timedelta(hours=24),
            offer_nudge_delay=timedelta(hours=24),
            offer_expiration=timedelta(hours=72),
        ),
        clock=lambda: NOW,
    )


def evaluate(service, context=None):
    return service.evaluate_for_telegram_user(
        creator_profile_id=2, telegram_user_id=22,
        conversation_context=context,
    )


class RepeatedNonconversionIntents(Intents):
    def get_customer_opportunity_evidence(self, **_kwargs):
        return {
            "commercial_opportunity_evidence_source": (
                "PURCHASE_INTENT_PRESENTATION_LIFECYCLE"
            ),
            "presented_opportunity_count": 2,
            "failed_nonconverted_opportunity_count": 2,
            "converted_opportunity_count": 0,
            "active_unresolved_opportunity": False,
        }


def test_low_cost_nurture_suppresses_optional_chat_but_not_fresh_buying_intent():
    service = brain(
        customer=profile(), commerce_signal=signal(), eligible=offering(),
    )
    service.intents = RepeatedNonconversionIntents()
    history = {
        "inbound_message_count": 20,
        "low_information_response_count": 4,
        "nurture_response_count_rolling_day": 1,
        "last_nurture_response_at": NOW - timedelta(hours=2),
    }

    optional = evaluate(service, {**history, "latest_message": "hey"})
    optional_attention = optional.decision_metadata["customerValueAttention"]
    optional_suppression = optional.decision_metadata["outboundSuppression"]
    assert optional_attention["lowCostNurtureActive"] is True
    assert optional_suppression["suppressed"] is True
    assert optional_suppression["reason"] == (
        "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
    )

    commercial = evaluate(
        service, {**history, "latest_message": "okay what can I unlock?"},
    )
    commercial_attention = commercial.decision_metadata["customerValueAttention"]
    commercial_suppression = commercial.decision_metadata["outboundSuppression"]
    assert commercial_attention["nurtureBypassedForCommercialIntent"] is True
    assert commercial_suppression["suppressed"] is False
    assert commercial.sell_allowed is True


def test_canonical_sustained_sexual_receptiveness_projection_is_fail_closed():
    service = brain()
    context = {
        "sexual_engagement_only": True,
        "sexual_engagement_count": 4,
        "inbound_message_count": 6,
        "rejection_count": 0,
        "contextual_customer_tone": {
            "sexualOrProvocative": True,
            "explicitDisengagement": False,
            "hostilityLevel": "NONE",
        },
        "sales_progression": {"phase": "CONVERSATIONAL"},
    }
    projection = service._sustained_sexual_receptiveness_projection(context)
    assert projection["value"] is True
    assert projection["authority"] == (
        "CUSTOMER_SALES_BRAIN_CANONICAL_BEHAVIOR_EVIDENCE"
    )
    assert service._sustained_sexual_receptiveness({
        **context, "sales_progression": {"phase": "BACK_OFF"},
    }) is False
    assert service._sustained_sexual_receptiveness({
        **context, "rejection_count": 1,
    }) is False


def test_identity_unresolved_has_first_priority():
    result = evaluate(brain(identity=False))
    assert result.decision is CustomerSalesDecisionType.MANUAL_REVIEW
    assert result.reason_code is CustomerSalesReasonCode.IDENTITY_UNRESOLVED


def test_enabled_bootstrap_uses_restricted_unmapped_prospect_and_selects_offer(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    selected = offering()
    prospect = SimpleNamespace(telegram_chat_id=22, inbound_message_count=6)
    prospects = UnmappedTelegramProspectService(repository=SimpleNamespace(
        get=lambda **_values: prospect,
    ))
    service = CustomerSalesBrainService(
        customer_repository=Customers(None), identity_repository=Identities(False),
        intent_repository=Intents(), commerce_signal_service=Signals(None),
        offering_selector_service=Selector(selected),
        unmapped_telegram_prospect_service=prospects,
        clock=lambda: NOW,
    )

    result = service.evaluate_for_telegram_user(
        creator_profile_id=2, telegram_user_id=22,
        conversation_context={"fanvue_account_id": 7, "telegram_chat_id": 22,
                              "latest_message": "I want to buy this now"},
    )

    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.identity_resolved is False
    assert result.external_fanvue_buyer_uuid is None
    assert result.recommended_offering_id == selected.offering_id
    assert result.commerce_signal["fanvueCommerceHistory"] == "UNKNOWN"
    assert result.decision_metadata["customerCommerceMemory"]["lifetimePurchaseCount"] == 0
    assert result.decision_metadata["activeBuyingWindow"] == {
        **result.decision_metadata["activeBuyingWindow"],
        "active": True,
        "source": "PRODUCTION_CUSTOMER_STATE",
        "scenarioInfluencedCommercialAuthority": False,
    }


def test_unmapped_bootstrap_enforces_one_active_offer(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    current = intent()
    service = brain(identity=False, active=current, eligible=offering())
    service.unmapped_prospects = UnmappedTelegramProspectService(
        repository=SimpleNamespace(get=lambda **_values: SimpleNamespace()))
    result = evaluate(service, {"fanvue_account_id": 7, "telegram_chat_id": 22})
    assert result.decision is CustomerSalesDecisionType.WAIT
    assert result.active_purchase_intent_id == current.purchase_intent_id


class DurableProspects:
    def __init__(self):
        self.records = {}

    @staticmethod
    def _key(values):
        return (
            values["creator_profile_id"], values["fanvue_account_id"],
            values["telegram_user_id"],
        )

    def get(self, **values):
        return self.records.get(self._key(values))

    def observe(self, **values):
        key = self._key(values)
        prospect = self.records.get(key) or SimpleNamespace(
            telegram_chat_id=values["telegram_chat_id"],
            inbound_message_count=1, relationship_state={},
            preference_state={"favoriteColor": "blue"},
        )
        self.records[key] = prospect
        return prospect

    def record_sales_progression(self, *, progression, correlation_id,
                                 **values):
        prospect = self.records[self._key(values)]
        if prospect.relationship_state.get(
            "salesProgressionCorrelationId"
        ) == correlation_id:
            return prospect
        prospect.relationship_state = {
            **prospect.relationship_state,
            "salesProgression": dict(progression),
            "salesProgressionCorrelationId": correlation_id,
        }
        return prospect

    def record_session_proposal(self, *, correlation_id,
                                session_offering_id=None, **values):
        prospect = self.records[self._key(values)]
        prospect.relationship_state = {
            **prospect.relationship_state,
            "sessionProposal": {
                "state": "PENDING", "proposalId": correlation_id,
                "correlationId": correlation_id,
                "sourceInbound": values.get("source_inbound") or correlation_id,
                "sessionOfferingId": str(session_offering_id),
                "createdAt": NOW.isoformat(), "deliveredAt": NOW.isoformat(),
                "expiresAt": (NOW + timedelta(hours=24)).isoformat(),
                "delivered": True, "consumed": False,
            },
        }
        return prospect

    def transition_session_proposal(self, *, target_state, reaction, **values):
        prospect = self.records[self._key(values)]
        proposal = dict(prospect.relationship_state.get("sessionProposal") or {})
        if proposal.get("state") != "PENDING":
            return None
        proposal.update({"state": target_state, "reaction": reaction,
                         "consumed": target_state != "PENDING"})
        prospect.relationship_state["sessionProposal"] = proposal
        return prospect


def durable_unmapped_brain(repository, selected):
    prospects = UnmappedTelegramProspectService(repository=repository)
    return CustomerSalesBrainService(
        customer_repository=Customers(None),
        identity_repository=Identities(False), intent_repository=Intents(),
        commerce_signal_service=Signals(None),
        offering_selector_service=Selector(selected),
        unmapped_telegram_prospect_service=prospects,
        clock=lambda: NOW,
    )


def unmapped_turn(service, message, correlation, *, creator=2, account=7,
                  telegram_user=22):
    decision = service.evaluate_for_telegram_user(
        creator_profile_id=creator, telegram_user_id=telegram_user,
        conversation_context={
            "fanvue_account_id": account,
            "telegram_chat_id": telegram_user,
            "latest_message": message,
            "conversation_id": correlation,
        },
    )
    service.record_unmapped_progression(
        decision, correlation_id=correlation,
    )
    return decision


def test_unmapped_progression_is_durable_scoped_and_restart_safe(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true"
    )
    repository = DurableProspects()
    selected = offering()
    first_service = durable_unmapped_brain(repository, selected)

    first = unmapped_turn(
        first_service, "show me something", "operation-1"
    )
    first_state = dict(first.decision_metadata)["salesProgression"]
    assert (first_state["phase"], first_state["teaseCount"]) == ("PRESENT_OFFER", 0)
    assert first.decision_metadata["salesProgressionSource"] == "NONE"

    restarted_service = durable_unmapped_brain(repository, selected)
    second = unmapped_turn(
        restarted_service, "tell me more", "operation-2"
    )
    second_state = dict(second.decision_metadata)["salesProgression"]
    assert (second_state["phase"], second_state["teaseCount"]) == (
        "PRESENT_OFFER", 0,
    )
    assert second.decision_metadata["activeBuyingWindow"]["active"] is True
    assert second_state["offeringId"] == str(selected.offering_id)
    assert second.decision_metadata["salesProgressionSource"] == (
        "TELEGRAM_NUMERIC_PROSPECT"
    )

    isolated = unmapped_turn(
        restarted_service, "show me something", "operation-other", telegram_user=23,
    )
    assert dict(isolated.decision_metadata)["salesProgression"][
        "phase"
    ] == "PRESENT_OFFER"
    other_scope = unmapped_turn(
        restarted_service, "show me something", "operation-scope", account=8,
    )
    assert dict(other_scope.decision_metadata)["salesProgression"][
        "phase"
    ] == "PRESENT_OFFER"

    prospect = repository.records[(2, 7, 22)]
    assert prospect.preference_state == {"favoriteColor": "blue"}


def test_unmapped_progression_offering_reset_and_duplicate_write(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true"
    )
    repository = DurableProspects()
    original = offering()
    service = durable_unmapped_brain(repository, original)
    first = unmapped_turn(service, "show me something", "operation-1")
    service.record_unmapped_progression(first, correlation_id="operation-1")
    assert repository.records[(2, 7, 22)].relationship_state[
        "salesProgression"
    ]["phase"] == "PRESENT_OFFER"

    replacement = offering()
    service.offering_selector.offering = replacement
    changed = unmapped_turn(service, "oh really?", "operation-2")
    changed_state = dict(changed.decision_metadata)["salesProgression"]
    assert changed_state["offeringId"] == str(replacement.offering_id)
    assert changed_state["teaseCount"] == 1


def test_mapped_progression_reports_sales_session_authority():
    selected = offering()
    result = evaluate(brain(customer=profile(), eligible=selected), {
        "latest_message": "hmm",
        "sales_progression": {
            "phase": "TEASE", "offeringId": str(selected.offering_id),
            "teaseCount": 1, "reasonCode": "TEASE_RELEVANT_OPPORTUNITY",
        },
    })

    assert result.decision_metadata["salesProgressionSource"] == "SALES_SESSION"


def test_commercial_intelligence_diagnostics_preserve_boundary_contexts():
    result = evaluate(
        brain(customer=profile(), eligible=offering()),
        {
            "latest_message": "show me a beach photo",
            "requested_themes": ("beach",),
        },
    )
    diagnostics = result.decision_metadata["commercialIntelligence"]

    assert diagnostics["strategy"] == "LIBRARY_SELLING"
    assert "ownershipConsiderations" in diagnostics
    assert "salesSessionContext" in diagnostics
    assert diagnostics["customerRequestContext"]["requestedThemes"] == (
        "beach",
    )
    assert "diagnosticContext" in diagnostics
    assert result.decision_metadata["offeringSelector"] is not None
    assert result.decision.value == "PRESENT_OFFER"


def test_customer_sales_brain_returns_no_sale_for_ownership_insufficiency():
    service = brain(customer=profile(), eligible=offering())
    service.commercial_context = SimpleNamespace(assemble=lambda **_values:
        CommercialIntelligenceContext(
            creator_profile_id=2, fanvue_account_id=7,
            telegram_user_id=22,
            latest_message="show me a beach photo",
            ownership=OwnershipCoverage(incomplete=True),
        )
    )

    result = evaluate(service, {"latest_message": "show me a beach photo"})

    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.NO_SELLING_STRATEGY
    assert (
        result.decision_metadata["commercialIntelligence"]["reason"]
        == "INSUFFICIENT_OWNERSHIP_EVIDENCE"
    )


@pytest.mark.parametrize(
    ("commerce_signal", "latest", "expected", "reason"),
    [
        (
            signal(reconciliation="PENDING"), None,
            CustomerSalesDecisionType.PAYMENT_PENDING,
            CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING,
        ),
        (
            signal(attribution="UNKNOWN"), None,
            CustomerSalesDecisionType.MANUAL_REVIEW,
            CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN,
        ),
    ],
)
def test_payment_rules_precede_offer_rules(
    commerce_signal, latest, expected, reason,
):
    active = intent(presented_at=NOW - timedelta(days=2))
    result = evaluate(brain(
        customer=profile(), commerce_signal=commerce_signal,
        latest=latest or active, active=active, eligible=offering(),
    ))
    assert result.decision is expected
    assert result.reason_code is reason


def test_verified_purchase_acknowledgement_precedes_cooldown():
    purchased = intent(status="PURCHASED", attribution="ATTRIBUTED")
    result = evaluate(brain(
        customer=profile(
            purchases=1, last_purchase=NOW - timedelta(hours=1)
        ),
        commerce_signal=signal(attribution="ATTRIBUTED", conversion="PURCHASED"),
        latest=purchased,
    ), {"purchase_acknowledgement_pending": True})
    assert result.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE
    assert result.congratulate_allowed is True


def test_recent_purchase_cooldown_blocks_sale():
    result = evaluate(brain(
        customer=profile(
            purchases=1, last_purchase=NOW - timedelta(hours=1)
        ),
        commerce_signal=signal(attribution="ATTRIBUTED"),
        eligible=offering(),
    ))
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    assert result.cooldown_until == NOW + timedelta(hours=23)


@pytest.mark.parametrize("message", (
    "send me another", "what else do you have?", "next one", "show me more",
))
def test_recent_purchase_direct_continuation_overrides_cooldown(message):
    selected = offering()
    service = brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=selected,
    )
    result = evaluate(service, {"latest_message": message})

    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True
    assert result.recommended_offering_id == selected.offering_id
    assert result.decision_metadata["commercialReceptiveness"]["state"] == "HOT"
    assert result.decision_metadata["purchaseCooldown"] == {
        "active": True,
        "blockingCurrentSale": False,
        "override": True,
        "overrideReason": "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN",
        "until": (NOW + timedelta(hours=23)).isoformat(),
    }
    assert result.decision_metadata["continuation"][
        "anotherSaleAppropriateNow"
    ] is True
    window = result.decision_metadata["activeBuyingWindow"]
    assert window["active"] is True
    assert window["source"] == "PRODUCTION_CUSTOMER_STATE"
    assert window["scenarioInfluencedCommercialAuthority"] is False
    assert window["purchaseCooldownOverridden"] is True


def test_recent_purchase_positive_engagement_is_elevated_but_not_forced_offer():
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {"latest_message": "damn that was so hot"})
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    assert result.decision_metadata["commercialReceptiveness"]["state"] == "HOT"
    assert result.decision_metadata["continuation"][
        "anotherSaleAppropriateNow"
    ] is False
    assert result.decision_metadata["activeBuyingWindow"]["active"] is False


def test_repeat_and_high_history_buyers_still_require_current_momentum():
    quiet = evaluate(brain(
        customer=profile(purchases=100, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {"latest_message": "how has your day been?"})
    assert quiet.sell_allowed is False
    assert quiet.decision_metadata["activeBuyingWindow"]["active"] is False

    selected = offering()
    active = evaluate(brain(
        customer=profile(purchases=100, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=selected,
    ), {"latest_message": "what else have you got?"})
    assert active.sell_allowed is True
    assert active.recommended_offering_id == selected.offering_id
    assert active.decision_metadata["activeBuyingWindow"]["active"] is True


def test_sexuality_without_commercial_evidence_does_not_open_buying_window():
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {
        "latest_message": "you look ridiculously hot tonight",
        "sexual_engagement_only": True,
        "sexual_engagement_count": 5,
        "inbound_message_count": 7,
        "contextual_customer_tone": {
            "sexualOrProvocative": True,
            "explicitDisengagement": False,
            "hostilityLevel": "NONE",
        },
    })
    assert result.decision_metadata["activeBuyingWindow"]["active"] is False
    assert result.decision_metadata["activeBuyingWindow"][
        "anotherSaleAppropriateNow"
    ] is False


def test_recent_purchase_no_novel_inventory_never_repeats_or_invents_offer():
    result = evaluate(brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(hours=1)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=None,
    ), {"latest_message": "send me another"})
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING
    assert result.recommended_offering_id is None


def test_fresh_direct_intent_closes_existing_offer_without_timer_wait():
    active = intent(presented_at=NOW - timedelta(hours=1))
    selected = offering()
    service = brain(customer=profile(), commerce_signal=signal(), latest=active,
                    active=active, eligible=selected)
    result = evaluate(service, {"latest_message": "how do I buy it?"})
    assert result.decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
    assert result.reason_code is CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT
    assert result.nudge_allowed is True
    assert service.offering_selector.calls[0]["active_purchase_intent"] is active


@pytest.mark.parametrize("message,continuation_type", (
    ("how much is it?", "PRICE_REQUEST"),
    ("yeah, send me the link", "SEND_OR_LINK_REQUEST"),
))
def test_customer_initiated_active_offer_continuation_bypasses_nudge_timer(
    message, continuation_type,
):
    active = intent(presented_at=NOW - timedelta(minutes=1))
    selected = offering()
    selected.offering_id = active.commercial_offering_id
    service = brain(customer=profile(), commerce_signal=signal(), latest=active,
                    active=active, eligible=selected)
    result = evaluate(service, {"latest_message": message})
    continuation = result.decision_metadata["activeOfferContinuation"]
    assert result.decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
    assert result.reason_code is (
        CustomerSalesReasonCode.CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION
    )
    assert result.active_purchase_intent_id == active.purchase_intent_id
    assert result.recommended_offering_id == active.commercial_offering_id
    assert continuation == {
        "customerInitiatedOfferContinuation": True,
        "continuationIntentType": continuation_type,
        "nudgeCooldownApplies": False,
        "structuredOfferReused": True,
        "structuredOfferRedelivered": False,
        "purchaseIntentReused": True,
        "relationshipDiscoverySuppressed": True,
    }
    assert result.decision_metadata["offerLifecycle"]["messagePurpose"] == (
        "ACTIVE_OFFER_CONTINUATION"
    )


@pytest.mark.parametrize("purchase_count", (2, 3))
def test_repeated_purchases_have_no_arbitrary_continuation_cap(purchase_count):
    selected = offering()
    result = evaluate(brain(
        customer=profile(
            purchases=purchase_count,
            last_purchase=NOW - timedelta(minutes=10),
        ),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=selected,
    ), {"latest_message": "I want another"})
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id == selected.offering_id
    assert result.decision_metadata["commercialReceptiveness"]["state"] == "HOT"


class ModeAwareSelector(Selector):
    def __init__(self, ordinary, session):
        super().__init__(ordinary)
        self.ordinary = ordinary
        self.session = session

    def select(self, **kwargs):
        constraints = kwargs.get("strategy_constraints")
        required = tuple(getattr(constraints, "required_selling_modes", ()) or ())
        self.offering = self.session if required == ("SESSION",) else self.ordinary
        return super().select(**kwargs)


def test_two_purchase_ongoing_intent_proposes_session_without_starting_it():
    ordinary, session = offering(), offering()
    service = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    service.offering_selector = ModeAwareSelector(ordinary, session)

    result = evaluate(service, {
        "latest_message": "don't stop, let's keep this going",
    })

    escalation = result.decision_metadata["sessionEscalation"]
    assert result.decision is CustomerSalesDecisionType.PROPOSE_SESSION
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    assert escalation["sessionCandidate"] is True
    assert escalation["sessionProposalAuthorized"] is True
    assert escalation["sessionStarted"] is False


def test_one_purchase_send_another_defaults_to_ordinary_ppv():
    ordinary, session = offering(), offering()
    service = brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    service.offering_selector = ModeAwareSelector(ordinary, session)

    result = evaluate(service, {"latest_message": "send me another"})

    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id == ordinary.offering_id
    assert result.decision_metadata["sessionEscalation"][
        "sessionCandidate"
    ] is False


def test_pending_session_proposal_acceptance_reaches_entry_boundary_only():
    ordinary, session = offering(), offering()
    service = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    service.offering_selector = ModeAwareSelector(ordinary, session)

    result = evaluate(service, {
        "latest_message": "yeah I'm in",
        "session_proposal": {"state": "PENDING"},
    })

    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.SESSION_ACCEPTED
    assert result.sell_allowed is False
    escalation = result.decision_metadata["sessionEscalation"]
    assert escalation["sessionStartAuthorityEligible"] is True
    assert escalation["sessionStarted"] is False


def test_confirmed_session_proposal_survives_service_restart_and_beats_cooldown():
    ordinary, session = offering(), offering()
    repository = DurableProspects()
    repository.observe(
        creator_profile_id=2, fanvue_account_id=7,
        telegram_user_id=22, telegram_chat_id=22,
    )
    prospects = UnmappedTelegramProspectService(repository=repository)
    first = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    first.offering_selector = ModeAwareSelector(ordinary, session)
    first.unmapped_prospects = prospects
    proposal = evaluate(first, {
        "latest_message": "don't stop, let's keep this going",
        "correlation_id": "inbound:proposal",
    })
    assert proposal.decision is CustomerSalesDecisionType.PROPOSE_SESSION
    first.confirm_session_proposal_delivery(
        proposal, correlation_id="inbound:proposal", provider_message_id=7001,
    )

    restarted = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    restarted.offering_selector = ModeAwareSelector(ordinary, session)
    restarted.unmapped_prospects = prospects
    accepted = evaluate(restarted, {
        "latest_message": "yeah I'm in, let's keep it going",
        "correlation_id": "inbound:acceptance",
    })

    assert accepted.reason_code is CustomerSalesReasonCode.SESSION_ACCEPTED
    escalation = accepted.decision_metadata["sessionEscalation"]
    assert escalation["sessionProposalCustomerReaction"] == "ACCEPT_OR_LEAN_IN"
    assert escalation["sessionEscalationDecision"] == "SESSION_ACCEPTED"
    assert escalation["sessionStartAuthorityEligible"] is True
    assert escalation["sessionStarted"] is False
    assert escalation["purchaseCooldownActive"] is True
    assert escalation["purchaseCooldownSuppressedForProposalReaction"] is True
    restarted.record_session_proposal(
        accepted, correlation_id="inbound:acceptance",
    )
    stored = repository.get(
        creator_profile_id=2, fanvue_account_id=7, telegram_user_id=22,
    ).relationship_state["sessionProposal"]
    assert stored["state"] == "ACCEPTED"
    assert stored["consumed"] is True


def test_pending_session_decline_for_another_item_resumes_discrete_ppv():
    ordinary, session = offering(), offering()
    service = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    service.offering_selector = ModeAwareSelector(ordinary, session)
    result = evaluate(service, {
        "latest_message": "not that, I'd rather just get another one instead",
        "session_proposal": {"state": "PENDING", "delivered": True},
    })
    escalation = result.decision_metadata["sessionEscalation"]
    assert escalation["sessionProposalCustomerReaction"] == (
        "DECLINE_SESSION_BUT_WANTS_MORE"
    )
    assert escalation["sessionProposalPending"] is False
    assert escalation["continueDiscretePpvsAuthorized"] is True
    assert result.recommended_offering_id == ordinary.offering_id


def test_ambiguous_pending_session_response_creates_no_competing_ppv():
    ordinary, session = offering(), offering()
    service = brain(
        customer=profile(purchases=2, last_purchase=NOW - timedelta(minutes=5)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=ordinary,
    )
    service.offering_selector = ModeAwareSelector(ordinary, session)
    result = evaluate(service, {
        "latest_message": "tell me about your day",
        "session_proposal": {"state": "PENDING", "delivered": True},
    })
    escalation = result.decision_metadata["sessionEscalation"]
    assert escalation["sessionProposalCustomerReaction"] == "NONE"
    assert escalation["sessionProposalPending"] is True
    assert escalation["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None


def test_recent_purchase_direct_intent_does_not_suppress_session_progression():
    selected = offering()
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=selected,
    ), {
        "latest_message": "next one",
        "sales_progression": {
            "phase": "PRESENT_OFFER", "offeringId": str(selected.offering_id),
            "teaseCount": 1,
        },
    })
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.reason_code is CustomerSalesReasonCode.SESSION_NEXT_UNLOCK_REQUEST
    assert result.decision_metadata["salesProgressionSource"] == "SALES_SESSION"


def test_recent_purchase_rejection_remains_cooldown_blocked():
    result = evaluate(brain(
        customer=profile(purchases=3, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {"latest_message": "no thanks, maybe later"})
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.sell_allowed is False
    assert result.decision_metadata["commercialReceptiveness"]["state"] == "BACK_OFF"


def test_turn18_outdoor_uncertainty_is_not_commercial_hesitation_after_purchase():
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {
        "latest_message": (
            "I might get outside this weekend if the weather’s decent."
        ),
    })
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    objection = result.decision_metadata["commercialObjection"]
    assert objection["type"] == "NONE"
    assert objection["evidence"] == ()
    assert objection["pressureDecrease"] is False
    assert result.sell_allowed is False


def test_turn22_pet_appointment_remains_noncommercial_during_purchase_cooldown():
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {
        "latest_message": (
            "He's got a vet appointment Friday and somehow he always knows "
            "when we're going 😂"
        ),
    })
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    assert result.sell_allowed is False
    objection = result.decision_metadata["commercialObjection"]
    assert objection["type"] == "NONE"
    assert objection["evidence"] == ()
    assert objection["pressureDecrease"] is False


def test_turn26_quiet_tomorrow_remains_noncommercial_during_purchase_cooldown():
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=offering(),
    ), {
        "latest_message": "I'm probably just gonna take it easy tomorrow after work.",
    })
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    assert result.sell_allowed is False
    objection = result.decision_metadata["commercialObjection"]
    assert objection["type"] == "NONE"
    assert objection["evidence"] == ()
    assert objection["pressureDecrease"] is False


@pytest.mark.parametrize("message", ("more", "anything hotter?"))
def test_required_hot_continuation_phrases_present_novel_offer(message):
    selected = offering()
    result = evaluate(brain(
        customer=profile(purchases=1, last_purchase=NOW - timedelta(minutes=10)),
        commerce_signal=signal(attribution="ATTRIBUTED"), eligible=selected,
    ), {"latest_message": message})
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id == selected.offering_id
    assert result.decision_metadata["commercialReceptiveness"]["state"] == "HOT"
    assert result.decision_metadata["purchaseCooldown"]["override"] is True


@pytest.mark.parametrize("message", (
    "I bought it", "I paid", "payment went through", "I unlocked it",
))
def test_customer_purchase_claim_never_creates_verified_purchase_truth(message):
    active = intent(status="PRESENTED", attribution="PENDING")
    result = evaluate(brain(
        customer=profile(purchases=0, last_purchase=None),
        commerce_signal=signal(attribution="PENDING"),
        latest=active, active=active, eligible=offering(),
    ), {"latest_message": message})
    assert result.decision is not CustomerSalesDecisionType.CONGRATULATE_PURCHASE
    assert result.decision_metadata["commercialReceptiveness"][
        "recentPurchaseDetected"
    ] is False
    assert result.decision_metadata["purchaseCooldown"]["active"] is False
    assert result.buyer_stage is CustomerBuyerStage.PROSPECT


def test_false_purchase_claim_and_real_intent_keeps_active_offer_authoritative():
    active = intent(status="PRESENTED", attribution="PENDING")
    result = evaluate(brain(
        customer=profile(purchases=0, last_purchase=None),
        commerce_signal=signal(attribution="PENDING"),
        latest=active, active=active, eligible=offering(),
    ), {"latest_message": "I bought that one, send me another."})
    assert result.decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
    assert result.active_purchase_intent_id == active.purchase_intent_id
    assert result.decision_metadata["commercialReceptiveness"][
        "recentPurchaseDetected"
    ] is False
    assert result.congratulate_allowed is False


def test_active_offer_waits_then_becomes_nudge_eligible():
    waiting = intent(presented_at=NOW - timedelta(hours=2))
    wait = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
        latest=waiting, active=waiting,
    ))
    assert wait.decision is CustomerSalesDecisionType.WAIT
    old = intent(presented_at=NOW - timedelta(hours=25))
    service = brain(
        customer=profile(), commerce_signal=signal(),
        latest=old, active=old,
        eligible=offering(),
    )
    nudge = evaluate(service)
    assert nudge.decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
    assert nudge.nudge_allowed is True
    assert len(service.offering_selector.calls) == 1
    assert (
        service.offering_selector.calls[0]["active_purchase_intent"] is old
    )


def test_expired_offer_precedes_new_offer_selection():
    expired = intent(status="EXPIRED")
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
        latest=expired, eligible=offering(),
    ))
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED
    assert result.active_purchase_intent_id is None
    assert result.active_offering_id is None
    assert result.decision_metadata["latestIntentStatus"] == "EXPIRED"


def test_decision_and_nested_metadata_are_immutable():
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(), eligible=offering(),
    ))
    with pytest.raises(FrozenInstanceError):
        result.sell_allowed = False
    with pytest.raises(TypeError):
        result.decision_metadata["rulePriority"] = 99


def test_first_repository_ordered_offering_is_structurally_selected():
    selected = offering()
    service = brain(
        customer=profile(), commerce_signal=signal(), eligible=selected,
    )
    result = evaluate(service)
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert len(service.offering_selector.calls) == 1
    assert result.recommended_offering_id == selected.offering_id
    assert result.recommended_publication_id == selected.publication_id
    assert result.recommended_offering_title == selected.title
    assert result.recommended_offering_price_minor == 999
    assert result.sell_allowed is False
    assert result.upsell_allowed is False
    assert result.cross_sell_allowed is False


def test_no_eligible_offering_means_no_sale():
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
    ))
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING


def test_buyer_stages_do_not_invent_high_value_or_inactive_thresholds():
    assert CustomerSalesBrainService.buyer_stage(0) is CustomerBuyerStage.PROSPECT
    assert CustomerSalesBrainService.buyer_stage(1) is CustomerBuyerStage.FIRST_TIME_BUYER
    assert CustomerSalesBrainService.buyer_stage(2) is CustomerBuyerStage.REPEAT_BUYER
    assert CustomerSalesBrainService.buyer_stage(100) is CustomerBuyerStage.REPEAT_BUYER


def test_statistics_and_read_only_api(monkeypatch):
    decision = evaluate(brain(
        customer=profile(), commerce_signal=signal(), eligible=offering(),
    ))

    class Service:
        def list_decisions(self, **kwargs):
            return (decision,), 1, 1

        def statistics(self, **kwargs):
            return {
                "total": 1,
                "decisionDistribution": {"PRESENT_OFFER": 1},
                "buyerStageDistribution": {"PROSPECT": 1},
                "currentActiveOffers": 0,
                "pendingPayments": 0,
                "unknownAttributions": 0,
            }

        def evaluate_for_telegram_user(self, **kwargs):
            return decision

    monkeypatch.setattr(api, "CustomerSalesBrainService", Service)
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)
    headers = {"X-Creator-OS-Developer": "true"}
    assert client.get(
        "/api/v1/developer/customer-sales-brain", headers=headers
    ).json()["items"][0]["decision"] == "TEASE"
    assert client.get(
        "/api/v1/developer/customer-sales-brain/statistics", headers=headers
    ).json()["decisionDistribution"] == {"PRESENT_OFFER": 1}
    assert client.get(
        "/api/v1/developer/customer-sales-brain/22", headers=headers
    ).json()["sellAllowed"] is False
    assert client.post(
        "/api/v1/developer/customer-sales-brain", headers=headers
    ).status_code == 405
