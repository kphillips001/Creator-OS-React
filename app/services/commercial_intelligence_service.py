"""Deterministic strategy recommendation without selection or authorization."""

from __future__ import annotations

import re

from app.models.commercial_intelligence import (
    BundleEligibility,
    CommercialIntelligenceContext,
    CommercialIntelligenceDecision,
    SellingStrategy,
    StrategyConstraints,
    StrategyDecisionReason,
    immutable_mapping,
)
from app.models.ownership_intelligence import CoverageState


class CommercialIntelligenceService:
    _REQUEST_TERMS = frozenset({
        "show", "see", "have", "photo", "photos", "video", "set", "content",
        "outfit", "wearing", "wardrobe", "theme", "mood", "location",
        "setting", "activity", "collection",
    })
    _COMPLETE_SET_PHRASES = (
        "complete set", "full set", "whole set", "entire set",
        "all the photos", "everything from", "complete collection",
        "whole collection", "entire photoshoot", "full photoshoot",
    )

    def recommend(
        self, context: CommercialIntelligenceContext,
    ) -> CommercialIntelligenceDecision:
        ownership_unsafe = (
            context.ownership.incomplete
            or bool(context.ownership.conflicts)
            or (
                context.canonical_ownership_answer is not None
                and not context.canonical_ownership_answer.evidence_sufficient
            )
        )
        if ownership_unsafe:
            return self._decision(
                context, strategy=None,
                reason=StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                summary=(
                    "Ownership evidence is insufficient for safe commercial "
                    "evaluation."
                ),
                evidence=("ownership_coverage",),
                constraints=StrategyConstraints(),
                bundle=(
                    BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE
                    if self._complete_set_requested(
                        str(context.latest_message or "")
                    )
                    else BundleEligibility.NOT_EVALUATED
                ),
                sufficient=False,
            )
        if context.active_sales_session_id is not None:
            continuation = (
                "Continue from the customer's existing session purchase history."
                if context.session_purchase_count else
                "Continue the active Sales Session without restarting it."
            )
            return self._decision(
                context,
                strategy=SellingStrategy.SESSION_SELLING,
                reason=StrategyDecisionReason.ACTIVE_SESSION_CONTINUATION,
                summary="An active canonical Sales Session controls the commercial path.",
                evidence=("active_sales_session", "session_progression"),
                constraints=StrategyConstraints(
                    required_photoshoot_reference=(
                        context.sales_session_foundation
                        if context.sales_session_foundation_type in (
                            None, "PHOTOSHOOT",
                        )
                        else None
                    ),
                    progression=context.sales_session_progression,
                    approved_commercial_roles=context.approved_commercial_roles,
                    excluded_asset_ids=context.ownership.owned_asset_ids,
                    remaining_value_required=context.session_purchase_count > 0,
                    continuation_required=True,
                ),
                continuation=continuation,
            )

        message = str(context.latest_message or "").strip()
        complete_set = self._complete_set_requested(message)
        request_present = self._request_present(context, message)
        bundle_available = "BUNDLE" in context.available_offering_types

        if complete_set:
            classification, reason, guidance = self._bundle_interpretation(context)
            if classification in {
                BundleEligibility.PARTIAL_SESSION_PURCHASE,
                BundleEligibility.CONTINUATION_REQUIRED,
                BundleEligibility.COMPLETE_VALUE_OWNED,
                BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE,
            }:
                reason_map = {
                    BundleEligibility.COMPLETE_VALUE_OWNED:
                        StrategyDecisionReason.COMPLETE_VALUE_OWNED,
                    BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE:
                        StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                }
                return self._decision(
                    context, strategy=None,
                    reason=reason_map.get(
                        classification,
                        StrategyDecisionReason.CONTINUATION_REQUIRED,
                    ),
                    summary=guidance or "The original full bundle is not appropriate.",
                    evidence=("complete_set_request", "ownership_coverage"),
                    constraints=StrategyConstraints(
                        required_offering_types=("BUNDLE",),
                        complete_set_required=True,
                        excluded_asset_ids=context.ownership.owned_asset_ids,
                        remaining_value_required=(
                            classification
                            is not BundleEligibility.COMPLETE_VALUE_OWNED
                        ),
                        continuation_required=(
                            classification
                            is not BundleEligibility.COMPLETE_VALUE_OWNED
                        ),
                    ),
                    bundle=classification, continuation=guidance,
                    sufficient=classification != BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                )
            if bundle_available:
                return self._decision(
                    context, strategy=SellingStrategy.BUNDLE_SELLING,
                    reason=StrategyDecisionReason.COMPLETE_SET_REQUEST,
                    summary="The customer requested a complete grouped experience.",
                    evidence=("complete_set_request", "bundle_inventory_available"),
                    constraints=StrategyConstraints(
                        required_offering_types=("BUNDLE",),
                        required_photoshoot_reference=(
                            context.sales_session_foundation
                            if context.sales_session_foundation_type in (
                                None, "PHOTOSHOOT",
                            )
                            else None
                        ),
                        complete_set_required=True,
                        excluded_asset_ids=context.ownership.owned_asset_ids,
                    ),
                    bundle=BundleEligibility.BUNDLE_ELIGIBLE,
                )

        if request_present:
            return self._decision(
                context, strategy=SellingStrategy.LIBRARY_SELLING,
                reason=StrategyDecisionReason.CUSTOMER_REQUEST_MATCH,
                summary="The customer's expressed request should search approved inventory.",
                evidence=("customer_request",),
                constraints=StrategyConstraints(
                    excluded_offering_types=("BUNDLE",),
                    requested_media_type=context.requested_media_type,
                    requested_themes=context.requested_themes,
                    excluded_asset_ids=context.ownership.owned_asset_ids,
                ),
            )

        return self._decision(
            context, strategy=None,
            reason=StrategyDecisionReason.INSUFFICIENT_EVIDENCE,
            summary="No durable session or sufficiently clear customer request supports a strategy.",
            evidence=(), constraints=StrategyConstraints(), sufficient=False,
        )

    @classmethod
    def _complete_set_requested(cls, message: str) -> bool:
        normalized = " ".join(message.lower().split())
        return any(phrase in normalized for phrase in cls._COMPLETE_SET_PHRASES)

    @classmethod
    def _request_present(cls, context, message: str) -> bool:
        if context.requested_media_type or context.requested_themes:
            return True
        tokens = frozenset(re.findall(r"[a-z0-9]+", message.lower()))
        return bool(tokens & cls._REQUEST_TERMS)

    @staticmethod
    def _bundle_interpretation(context):
        ownership = context.ownership
        if ownership.conflicts or ownership.incomplete:
            return (
                BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                "Ownership evidence requires review before offering the full bundle.",
            )
        compositions = tuple(
            item for item in context.bundle_compositions
            if (
                context.intended_photoshoot_reference is None
                or item.photoshoot_reference
                == context.intended_photoshoot_reference
            )
        )
        if len(compositions) != 1 or not compositions[0].complete_set:
            return (
                BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                "One intended complete-set composition could not be established.",
            )
        represented = frozenset(compositions[0].asset_ids)
        canonical = context.canonical_bundle_coverage
        if canonical is not None and canonical.state in {
            CoverageState.CONFLICTING, CoverageState.INSUFFICIENT,
        }:
            return (
                BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE,
                "Ownership evidence requires review before offering the full bundle.",
            )
        owned = (
            frozenset(canonical.owned_asset_ids)
            if canonical is not None
            else represented.intersection(ownership.owned_asset_ids)
        )
        if (
            canonical is not None
            and canonical.state is CoverageState.COMPLETE
        ) or (canonical is None and represented and owned == represented):
            return (
                BundleEligibility.COMPLETE_VALUE_OWNED,
                StrategyDecisionReason.COMPLETE_VALUE_OWNED,
                "The customer already owns the complete represented value.",
            )
        if (
            owned
            or context.session_purchase_count > 0
            or ownership.session_owned_asset_ids
        ):
            return (
                BundleEligibility.PARTIAL_SESSION_PURCHASE,
                StrategyDecisionReason.CONTINUATION_REQUIRED,
                "Use continuation, remaining value, upgrade, or premium extension.",
            )
        if context.session_participated:
            return (
                BundleEligibility.PARTICIPATED_NO_PURCHASE,
                StrategyDecisionReason.COMPLETE_SET_REQUEST,
                None,
            )
        return (
            BundleEligibility.MISSED_ORIGINAL_SESSION,
            StrategyDecisionReason.COMPLETE_SET_REQUEST,
            None,
        )

    @staticmethod
    def _decision(
        context, *, strategy, reason, summary, evidence, constraints,
        bundle=BundleEligibility.NOT_EVALUATED, continuation=None,
        sufficient=True,
    ):
        return CommercialIntelligenceDecision(
            strategy=strategy, reason=reason, reason_summary=summary,
            evidence=tuple(evidence),
            evidence_provenance=immutable_mapping(context.provenance),
            constraints=constraints,
            sales_session_context=immutable_mapping({
                "salesSessionId": (
                    str(context.active_sales_session_id)
                    if context.active_sales_session_id else None
                ),
                "state": context.sales_session_state,
                "progression": context.sales_session_progression,
                "foundationType": context.sales_session_foundation_type,
                "foundation": context.sales_session_foundation,
                "participated": context.session_participated,
                "purchaseCount": context.session_purchase_count,
            }),
            customer_request_context=immutable_mapping({
                "latestMessagePresent": bool(context.latest_message),
                "requestedMediaType": context.requested_media_type,
                "requestedThemes": context.requested_themes,
            }),
            ownership_considerations=immutable_mapping({
                "ownedOfferingCount": len(context.ownership.owned_offering_ids),
                "ownedAssetIds": context.ownership.owned_asset_ids,
                "sessionOwnedAssetIds": context.ownership.session_owned_asset_ids,
                "canonicalBundleCoverage": (
                    context.canonical_bundle_coverage.state.value
                    if context.canonical_bundle_coverage else None
                ),
                "canonicalBundleRemainingAssetIds": (
                    context.canonical_bundle_coverage.remaining_asset_ids
                    if context.canonical_bundle_coverage else ()
                ),
                "canonicalSessionCoverage": (
                    context.canonical_session_coverage.coverage.state.value
                    if context.canonical_session_coverage else None
                ),
                "canonicalSessionRemainingAssetIds": (
                    context.canonical_session_coverage.remaining_asset_ids
                    if context.canonical_session_coverage else ()
                ),
                "canonicalOwnershipAnswerState": (
                    context.canonical_ownership_answer.state.value
                    if context.canonical_ownership_answer else None
                ),
                "canonicalOwnershipDiagnostics": (
                    dict(context.canonical_ownership_answer.diagnostics)
                    if context.canonical_ownership_answer else {}
                ),
                "evidenceSources": context.ownership.evidence_sources,
                "incomplete": context.ownership.incomplete,
            }),
            bundle_eligibility=bundle,
            continuation_guidance=continuation,
            evidence_sufficient=sufficient,
            conflicts=context.ownership.conflicts,
            diagnostic_context=immutable_mapping({
                "availableOfferingTypes": context.available_offering_types,
                "intendedPhotoshootReference": (
                    context.intended_photoshoot_reference
                ),
                "bundleCompositionCount": len(context.bundle_compositions),
                "durableEvidence": dict(context.durable_evidence),
                "conversationEvidenceKeys": tuple(
                    context.conversation_evidence.keys()
                ),
                "assetLineageEvidence": dict(context.lineage_evidence),
            }),
        )
