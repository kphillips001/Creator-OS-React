from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.models.customer_intelligence import (
    CustomerIntelligenceState,
    CustomerSignalQuality,
)
from app.services.customer_intelligence_service import CustomerIntelligenceService
from app.services.customer_intelligence_service import CustomerIntelligenceCompatibilityAdapter


NOW = "2026-07-31T12:00:00+00:00"


def context(**changes):
    return {
        "creator_profile_id": 7,
        "fanvue_account_id": 11,
        "canonical_customer_id": "11:42",
        "external_fanvue_user_uuid": "11111111-1111-4111-8111-111111111111",
        "identity_path": "fanvue_account:legacy_user",
        **changes,
    }


def profile(**changes):
    values = {
        "customer_context": context(),
        "transactions": ({"transaction_order_id": "tx-1", "gross_minor": 2500, "net_minor": 2000, "currency": "USD", "timestamp": NOW},),
        "purchase_intents": ({"purchase_intent_id": "intent-1", "provider_transaction_order_id": "tx-1", "commercial_offering_id": "offering-1", "status": "PURCHASED", "attribution_result": "ATTRIBUTED", "created_metadata": {"media_type": "VIDEO", "offering_type": "BUNDLE"}},),
        "ownership": {"owned_asset_ids": (101,), "owned_offering_ids": ("offering-1",), "conflicts": (), "insufficiencies": ()},
        "sessions": ({"sales_session_id": "session-1", "state": "COMPLETED", "progression_stage": "PRESENTATION", "started_at": "2026-07-31T11:00:00+00:00", "ended_at": NOW},),
        "messages": ({"id": "message-1", "direction": "inbound", "sent_at": "2026-07-31T11:30:00+00:00", "requested_media_type": "VIDEO"}, {"id": "message-2", "direction": "outbound", "sent_at": "2026-07-31T11:31:00+00:00"}),
        "recommendations": ({"id": "recommendation-1", "event_state": "PRESENTED"}, {"id": "recommendation-2", "event_state": "PURCHASED"}),
    }
    values.update(changes)
    return CustomerIntelligenceService().build_canonical_profile(**values)


def test_profile_is_creator_scoped_immutable_and_preserves_provenance():
    value = profile()
    assert value.customer_context["creator_profile_id"] == 7
    assert value.identity_confidence == 1.0
    assert value.provenance["customer_identity_path"] == "fanvue_account:legacy_user"
    assert value.facts[0].creator_profile_id == 7
    with pytest.raises(FrozenInstanceError):
        value.profile_state = CustomerIntelligenceState.UNAVAILABLE


def test_profile_nested_values_are_deeply_immutable_and_detached():
    source = {"creator_profile_id": 7, "fanvue_account_id": 11,
              "canonical_customer_id": "11:42",
              "external_fanvue_user_uuid": "source-user",
              "identity_path": "test", "nested": {"tags": ["one"]}}
    value = profile(customer_context=source)
    source["nested"]["tags"].append("source mutation")
    assert value.customer_context["nested"]["tags"] == ("one",)
    with pytest.raises(TypeError):
        value.customer_context["nested"]["tags"] = ("changed",)
    with pytest.raises(TypeError):
        value.section_states["identity"] = CustomerIntelligenceState.UNAVAILABLE
    with pytest.raises(TypeError):
        value.facts[0].metadata["referenced_only"] = False


def test_missing_and_conflicting_identity_remain_explicit():
    missing = profile(customer_context={})
    assert missing.profile_state == CustomerIntelligenceState.INSUFFICIENT
    assert "CREATOR_SCOPE_REQUIRED" in missing.insufficiencies
    conflicting = profile(customer_context=context(identity_conflicts=("TELEGRAM_MAPPING_CONFLICT",)))
    assert conflicting.profile_state == CustomerIntelligenceState.CONFLICTING
    assert conflicting.identity_confidence == .25


def test_currency_safe_spending_never_combines_currencies():
    value = profile(transactions=(
        {"transaction_order_id": "usd", "gross_minor": 1000, "net_minor": 900, "currency": "USD"},
        {"transaction_order_id": "eur", "gross_minor": 2000, "net_minor": 1800, "currency": "EUR"},
        {"transaction_order_id": "unknown", "gross_minor": 999, "net_minor": 999},
    ))
    assert value.spending_profile["USD:lifetime_gross"].value == 1000
    assert value.spending_profile["EUR:lifetime_gross"].value == 2000
    assert "unknown" in value.spending_profile["USD:lifetime_gross"].excluded_records
    assert not any(key.startswith("ALL:") for key in value.spending_profile)


def test_session_video_bundle_and_engagement_metrics_are_deterministic():
    value = profile()
    assert value.session_profile["completion_rate"] == 1
    assert value.session_profile["average_duration_seconds"] == 3600
    assert value.video_conversion["numerator"] == 1
    assert value.video_conversion["denominator"] == 1
    assert value.engagement_profile["average_response_latency_seconds"] == 60
    assert value.bundle_behavior["state"] in {"PARTIAL", "SUFFICIENT"}


def test_preferences_preserve_quality_evidence_and_sparse_insufficiency():
    value = profile()
    video = next(item for item in value.media_preferences if item.subject == "VIDEO")
    assert video.quality in {CustomerSignalQuality.SUPPORTING, CustomerSignalQuality.STRONG_COMMERCIAL}
    assert video.positive_evidence
    assert "SPARSE_PREFERENCE_EVIDENCE" in video.insufficiencies
    assert value.aversions == ()


@pytest.mark.parametrize("consumer", (
    "commercial_intelligence", "offering_selector", "customer_sales_brain",
    "product_recommendation", "sales_sessions", "customer_workspace",
    "commercial_administration", "conversation",
))
def test_consumer_projections_share_profile_truth_without_decisions(consumer):
    value = profile()
    result = CustomerIntelligenceService().project_canonical_profile(value, consumer)
    assert result["consumer_projection"] == consumer
    assert result["identity_confidence"] == value.identity_confidence
    assert "selected_offering" not in result
    assert "authorized_sale" not in result
    assert result["section_states"] == value.section_states
    assert result["provenance"] == value.provenance
    with pytest.raises(TypeError):
        result["profile_state"] = "MUTATED"
    with pytest.raises(TypeError):
        result["customer_context"]["canonical_customer_id"] = "MUTATED"


def test_every_required_section_has_an_independent_state():
    value = profile()
    assert set((
        "spending", "purchase_history", "ownership", "sessions", "media",
        "bundles", "video", "engagement", "recommendations",
        "classifications", "provenance",
    )).issubset(value.section_states)
    assert all(isinstance(state, CustomerIntelligenceState)
               for state in value.section_states.values())


def test_interpreted_outputs_carry_complete_item_provenance():
    value = profile(classifications=({"label": "PURCHASER", "source": "Test",
                                      "confidence": .8, "evidence": ("tx-1",)},))
    outputs = [*value.spending_profile.values(), *value.purchase_preferences,
               *value.media_preferences]
    provenances = [item.provenance for item in outputs]
    provenances.extend(item["provenance"] for item in (
        *value.classifications, *value.opportunities, *value.risks,
    ))
    required = {"source_authority", "source_ids", "creator_profile_id",
                "customer_identity_path", "time_window", "calculated_at",
                "included_evidence", "excluded_evidence", "derivation_method",
                "confidence", "conflicts", "insufficiencies"}
    assert provenances
    assert all(required.issubset(item) for item in provenances)


def test_canonical_outputs_never_generate_decisions():
    value = profile()
    payload = CustomerIntelligenceService()._profile_payload(value)
    forbidden = {"recommendation_score", "strategy", "selected_offering",
                 "authorized_sale", "product_recommendation", "session_decision"}
    assert forbidden.isdisjoint(payload)


def test_source_failure_isolated_from_unrelated_sections():
    value = profile(source_failures={"ownership": "DependencyError"}, ownership=None)
    assert value.section_states["ownership"] == CustomerIntelligenceState.UNAVAILABLE
    assert value.section_states["spending"] == CustomerIntelligenceState.SUFFICIENT
    assert value.spending_profile["USD:lifetime_net"].value == 2000
    assert "SOURCE_UNAVAILABLE:ownership:DependencyError" in value.insufficiencies


def test_canonical_service_contract_excludes_legacy_decisions_and_mutations():
    canonical = CustomerIntelligenceService()
    forbidden = {
        "recommend_relationship_focus", "infer_relationship_stage",
        "calculate_engagement", "determine_commerce_maturity",
        "update_relationship", "update_preferences",
    }
    assert forbidden.isdisjoint(name for name in dir(canonical) if not name.startswith("_"))
    assert all(hasattr(CustomerIntelligenceCompatibilityAdapter(), name) for name in forbidden)


def test_profile_construction_does_not_invoke_compatibility_decisions():
    class Composer(CustomerIntelligenceCompatibilityAdapter):
        def recommend_relationship_focus(self, **kwargs): raise AssertionError("decision called")
        def infer_relationship_stage(self, **kwargs): raise AssertionError("decision called")
        def calculate_engagement(self, **kwargs): raise AssertionError("score called")
        def determine_commerce_maturity(self, **kwargs): raise AssertionError("decision called")
        def update_relationship(self, **kwargs): raise AssertionError("mutation called")
        def update_preferences(self, **kwargs): raise AssertionError("mutation called")
    result = CustomerIntelligenceService(profile_composer=Composer()).build_canonical_profile(
        customer_context=context(),
    )
    assert result.calculation_metadata["commercial_decisions"] is False


@pytest.mark.parametrize(("failure", "unavailable", "partial"), (
    ("identity", ("identity",), ()),
    ("transactions", ("spending",), ("purchase_history",)),
    ("Purchase Intents", ("bundles", "video"), ("purchase_history", "media")),
    ("entitlements", ("entitlements",), ("purchase_history", "bundles")),
    ("Ownership Intelligence", ("ownership",), ("bundles",)),
    ("Sales Sessions", ("sessions",), ()),
    ("conversation", ("engagement",), ("media",)),
    ("recommendation history", ("recommendations",), ()),
    ("Commercial Roles", ("commercial_roles",), ()),
    ("Asset Lineage", ("asset_lineage",), ("media", "video")),
    ("Publication", ("publications",), ()),
    ("fulfillments", ("fulfillment",), ()),
    ("deliveries", ("delivery",), ()),
))
def test_source_failure_families_are_normalized_and_isolated(failure, unavailable, partial):
    value = profile(source_failures={failure: RuntimeError("secret detail")})
    for section in unavailable:
        assert value.section_states[section] == CustomerIntelligenceState.UNAVAILABLE
        assert any(reason.endswith(":RuntimeError") for reason in value.section_state_reasons[section])
    for section in partial:
        assert value.section_states[section] == CustomerIntelligenceState.PARTIAL
        assert any(reason.endswith(":RuntimeError") for reason in value.section_state_reasons[section])
    assert "secret detail" not in repr(value.provenance)


def test_section_state_contract_supports_all_five_states_independently():
    assert profile().section_states["spending"] == CustomerIntelligenceState.SUFFICIENT
    assert profile(transactions=({"transaction_order_id": "tx", "complete": False},)).section_states["spending"] == CustomerIntelligenceState.PARTIAL
    assert profile(transactions=()).section_states["spending"] == CustomerIntelligenceState.INSUFFICIENT
    assert profile(transactions=({"transaction_order_id": "tx", "conflicts": ("DUPLICATE",)},)).section_states["spending"] == CustomerIntelligenceState.CONFLICTING
    unavailable = profile(source_failures={"transactions": "DependencyError"})
    assert unavailable.section_states["spending"] == CustomerIntelligenceState.UNAVAILABLE
    assert unavailable.section_states["sessions"] == CustomerIntelligenceState.SUFFICIENT


def test_scalar_metric_contract_and_aggregate_provenance_are_explicit():
    value = profile()
    metric = value.session_profile["metric_details"]["completion_rate"]
    assert metric.numerator == 1 and metric.denominator == 1
    assert metric.unit == "ratio"
    assert metric.included_records == ("session-1",)
    assert metric.lifecycle_filters
    assert metric.provenance["included_evidence_count"] == 1
    aggregate = profile(sessions=()).session_profile["provenance"]
    assert aggregate["aggregate_evidence"] is True


def test_identity_paths_are_source_attributed_and_never_speculatively_merged():
    unsupported = profile(customer_context=context(identity_path="display_name:similarity"))
    assert unsupported.section_states["identity"] == CustomerIntelligenceState.INSUFFICIENT
    assert "UNSUPPORTED_IDENTITY_PATH:display_name:similarity" in unsupported.insufficiencies
    telegram = profile(customer_context=context(telegram_user_id=99))
    assert "TELEGRAM_MAPPING_UNVERIFIED" in telegram.insufficiencies
    verified = profile(customer_context=context(
        telegram_user_id=99, telegram_mapping_source="CanonicalIdentityMapping",
        core_user_id="core-1", core_user_source="CoreUserRepository",
    ))
    assert verified.section_states["identity"] == CustomerIntelligenceState.SUFFICIENT
    conflicting = profile(customer_context=context(
        telegram_user_id=99, telegram_mapping_source="CanonicalIdentityMapping",
        telegram_mapping_conflicts=("MULTIPLE_CORE_USERS",),
    ))
    assert conflicting.section_states["identity"] == CustomerIntelligenceState.CONFLICTING


def test_refund_entitlement_contradiction_and_aversion_semantics():
    rejected = tuple({
        "purchase_intent_id": f"negative-{index}", "status": "REJECTED",
        "created_at": f"2026-07-3{index}T10:00:00+00:00",
        "created_metadata": {"media_type": "VIDEO"},
    } for index in (0, 1))
    value = profile(purchase_intents=rejected, messages=(), entitlements=({
        "entitlement_id": "ent-1", "status": "ACTIVE",
        "metadata": {"media_type": "VIDEO"},
    },))
    video = value.media_preferences[0]
    assert video.direction == "negative" and video.exposure_count == 2
    assert video.supporting_evidence == ("ent-1",)
    assert video.latest_evidence_at is not None
    assert value.aversions and value.aversions[0]["direction"] == "negative"
    refunded = profile(messages=(), purchase_intents=({
        "purchase_intent_id": "refund", "status": "PURCHASED",
        "attribution_result": "DIRECT",
        "created_metadata": {"media_type": "VIDEO", "refunded": True},
    },))
    assert refunded.media_preferences[0].positive_evidence == ()
    assert refunded.media_preferences[0].direction == "negative"
    single = profile(messages=(), purchase_intents=rejected[:1])
    assert single.aversions == ()


def test_failed_transactions_are_excluded_before_every_canonical_output():
    value = profile(source_failures={"transactions": RuntimeError("stale")})
    assert not any(fact.authority == "Customer Commerce Transactions" for fact in value.facts)
    assert not any(item.get("source_authority") == "Customer Commerce Transactions" for item in value.unified_purchase_history)
    assert set(value.spending_profile) == {"unavailable"}
    assert value.spending_profile["unavailable"].value is None
    assert value.section_states["sessions"] == CustomerIntelligenceState.SUFFICIENT


def test_failed_purchase_intents_preserve_valid_transactions_but_no_intent_conclusions():
    value = profile(source_failures={"purchase_intents": RuntimeError("stale")})
    assert not any(fact.authority == "Purchase Intents" for fact in value.facts)
    assert len(value.unified_purchase_history) == 1
    assert value.unified_purchase_history[0]["transaction_reference"] == "tx-1"
    assert value.unified_purchase_history[0]["purchase_intent_reference"] is None
    assert not value.purchase_preferences
    assert all("intent-1" not in item.positive_evidence + item.contradictory_evidence + item.supporting_evidence
               for item in value.media_preferences)
    assert value.video_conversion.get("videos_purchased") is None
    assert not any(item["type"] == "REPEATED_VIDEO_PURCHASE" for item in value.opportunities)


def test_failed_ownership_fails_closed_without_false_nonownership():
    value = profile(ownership={"owned_asset_ids": (999,), "owned_offering_ids": ("stale",)},
                    source_failures={"ownership": RuntimeError("stale")})
    assert value.section_states["ownership"] == CustomerIntelligenceState.UNAVAILABLE
    assert value.ownership_summary == {}
    assert "owned_asset_ids" not in value.ownership_summary
    assert not any(fact.authority == "Ownership Intelligence" for fact in value.facts)
    assert not any("OWNERSHIP" in item["type"] for item in value.opportunities)
    assert value.section_states["spending"] == CustomerIntelligenceState.SUFFICIENT


def test_failed_sessions_conversations_and_recommendations_emit_no_false_outcomes():
    sessions = profile(source_failures={"sessions": RuntimeError("stale")})
    assert not any(fact.authority == "Sales Sessions" for fact in sessions.facts)
    assert sessions.session_profile["metric_details"] == {}
    assert not any(item["type"] == "REPEATED_SESSION_ABANDONMENT" for item in sessions.risks)
    conversations = profile(source_failures={"conversations": RuntimeError("stale")})
    assert not any(fact.authority == "Conversation History" for fact in conversations.facts)
    assert conversations.engagement_profile["metric_details"] == {}
    assert all("message-1" not in item.positive_evidence for item in conversations.media_preferences)
    recommendations = profile(source_failures={"recommendations": RuntimeError("stale")})
    assert not any(fact.authority == "Recommendation and Outcome History" for fact in recommendations.facts)
    assert recommendations.recommendation_history["metric_details"] == {}
    assert recommendations.recommendation_history.get("rejection_count") is None


@pytest.mark.parametrize(("failure", "argument", "authority", "section"), (
    ("roles", "commercial_roles", "Commercial Roles", "commercial_roles"),
    ("lineage", "lineage", "Asset Lineage", "asset_lineage"),
    ("publications", "publications", "Publication", "publications"),
    ("fulfillment", "fulfillments", "Fulfillment", "fulfillment"),
    ("delivery", "deliveries", "Delivery", "delivery"),
))
def test_failed_supporting_authorities_are_excluded(failure, argument, authority, section):
    value = profile(**{argument: ({"id": "stale-source"},),
                       "source_failures": {failure: RuntimeError("stale")}})
    assert value.section_states[section] == CustomerIntelligenceState.UNAVAILABLE
    assert not any(fact.authority == authority for fact in value.facts)
    assert value.section_states["spending"] == CustomerIntelligenceState.SUFFICIENT


def test_opportunity_and_risk_provenance_use_canonical_records_not_metric_names():
    intents = tuple({"purchase_intent_id": f"video-{index}", "status": "PURCHASED",
                     "attribution_result": "DIRECT",
                     "commercial_offering_id": "offering-video",
                     "created_metadata": {"media_type": "VIDEO"}} for index in range(2))
    sessions = tuple({"sales_session_id": f"abandoned-{index}", "state": "ABANDONED"}
                     for index in range(2))
    value = profile(purchase_intents=intents, sessions=sessions, messages=())
    opportunity = next(item for item in value.opportunities if item["type"] == "REPEATED_VIDEO_PURCHASE")
    assert opportunity["provenance"]["source_ids"] == ("video-0", "video-1")
    assert opportunity["provenance"]["aggregate_evidence"] is False
    assert "videos_purchased" not in opportunity["provenance"]["source_ids"]
    risk = next(item for item in value.risks if item["type"] == "REPEATED_SESSION_ABANDONMENT")
    assert risk["provenance"]["source_ids"] == ("abandoned-0", "abandoned-1")
    assert risk["provenance"]["aggregate_evidence"] is False
    assert "session_profile" not in risk["provenance"]["source_ids"]


def test_aggregate_provenance_never_places_metric_names_in_source_ids():
    intents = tuple({"status": "PURCHASED", "attribution_result": "DIRECT",
                     "created_metadata": {"media_type": "VIDEO"}} for _ in range(2))
    value = profile(purchase_intents=intents, messages=())
    opportunity = next(item for item in value.opportunities if item["type"] == "REPEATED_VIDEO_PURCHASE")
    assert opportunity["provenance"]["source_ids"] == ()
    assert opportunity["provenance"]["aggregate_evidence"] is True
    assert opportunity["provenance"]["aggregate_name"] == "video_purchase_aggregate"


def test_every_projection_inherits_failed_source_exclusion_and_provenance():
    value = profile(ownership={"owned_asset_ids": (999,)},
                    source_failures={"ownership": RuntimeError("stale")})
    service = CustomerIntelligenceService()
    for consumer in ("commercial_intelligence", "offering_selector", "customer_sales_brain",
                     "product_recommendation", "sales_sessions", "customer_workspace",
                     "commercial_administration", "conversation"):
        projection = service.project_canonical_profile(value, consumer)
        if "ownership_summary" in projection:
            assert projection["ownership_summary"] == {}
        assert projection["section_states"]["ownership"] == CustomerIntelligenceState.UNAVAILABLE
        assert projection["section_state_reasons"]["ownership"]


def test_compatibility_adapter_cannot_bypass_canonical_failed_source_exclusion():
    value = CustomerIntelligenceCompatibilityAdapter().build_canonical_profile(
        customer_context=context(), ownership={"owned_asset_ids": (999,)},
        source_failures={"ownership": RuntimeError("stale")},
    )
    assert value.ownership_summary == {}
    assert value.commercial_summary["owned_asset_count"] is None
