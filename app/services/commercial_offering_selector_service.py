"""Deterministic, read-only Commercial Offering eligibility and selection."""
from __future__ import annotations

import logging
import time
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from app.models.commercial_offering_selection import (
    OfferingEligibilityEvaluation,
    OfferingExclusionReason,
    OfferingSelectionReason,
    SelectedOfferingResult,
    immutable_selector_metadata,
)
from app.models.commerce_recommendation import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationHistoryEntry,
)
from app.models.commercial_intelligence import StrategyConstraints
from app.models.photoshoot_experience_recommendation import (
    PhotoshootExperienceRecommendation,
)
from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.commercial_offering_selector_repository import (
    CommercialOfferingSelectorRepository,
)
from app.services.commerce_recommendation_engine import (
    CommerceRecommendationEngine,
    ProductTypeFitStrategy,
)
from app.services.ownership_intelligence_service import (
    OwnershipIntelligenceService,
)
from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus


logger = logging.getLogger("commercial-offering-selector")


class CommercialOfferingSelectorService:
    """Select one provider-ready offering without AI, scoring, or mutation."""

    def __init__(
        self, repository=None, clock=lambda: datetime.now(timezone.utc),
        recommendation_engine=None, ownership_intelligence=None,
        photoshoot_lifecycle_service=None, progression_repository=None,
    ):
        self.repository = (
            repository or CommercialOfferingSelectorRepository()
        )
        self.clock = clock
        self.recommendation_engine = (
            recommendation_engine or CommerceRecommendationEngine()
        )
        self.ownership_intelligence = (
            ownership_intelligence or OwnershipIntelligenceService()
        )
        self.photoshoot_lifecycles = photoshoot_lifecycle_service
        self.progression_repository = progression_repository

    def select(
        self, *, creator_profile_id: int, telegram_user_id: int | None,
        customer_profile, commerce_signal, active_purchase_intent,
        conversation_context: dict | None = None,
        strategy_constraints: StrategyConstraints | None = None,
        strategy: str | None = None,
    ) -> SelectedOfferingResult:
        started = time.perf_counter()
        context = dict(conversation_context or {})
        progression = dict(context.get("sales_progression") or {})
        progression_phase = str(progression.get("phase") or "").upper()
        bound_offering_id = None
        if progression_phase in {"TEASE", "BUILD_INTEREST", "PRESENT_OFFER"}:
            try:
                bound_offering_id = UUID(str(progression.get("offeringId")))
            except (TypeError, ValueError, AttributeError):
                bound_offering_id = None
        constraints = strategy_constraints or StrategyConstraints()
        channel = str(
            context.get("primary_sales_channel") or "AI_CHAT"
        ).strip().upper()
        recommendation_context = RecommendationContext(
            creator_profile_id=int(creator_profile_id),
            active_purchase_intent_offering_id=(
                UUID(str(active_purchase_intent.commercial_offering_id))
                if active_purchase_intent is not None else None
            ),
            evaluated_at=self.clock(),
            requested_media_type=context.get("requested_media_type"),
            conversation_id=(
                str(context["conversation_id"])
                if context.get("conversation_id") is not None else None
            ),
            current_request=context.get("latest_message"),
            requested_themes=tuple(context.get("requested_themes") or ()),
            recent_conversation_requests=tuple(
                context.get("recent_conversation_requests") or ()
            )[-3:],
            buyer_stage=self._buyer_stage(customer_profile, context),
            engagement_score=self._engagement_score(context),
            price_sensitive=self._price_sensitive(context),
        )
        account_id = int(getattr(customer_profile, "fanvue_account_id", 0))
        buyer_uuid = getattr(
            customer_profile, "external_fanvue_user_uuid", None
        )
        commerce_memory = context.get("_customer_commerce_memory")
        ownership = getattr(commerce_memory, "ownership", None)
        if ownership is None:
            ownership = self.ownership_intelligence.answer(OwnershipIdentity(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=account_id,
                external_fanvue_user_uuid=buyer_uuid,
                telegram_user_id=telegram_user_id,
                legacy_fanvue_user_id=(
                    str(context["legacy_fanvue_user_id"])
                    if context.get("legacy_fanvue_user_id") is not None
                    else None
                ),
                core_user_id=context.get("core_user_id"),
            ))
        purchased = frozenset(ownership.owned_offering_ids)
        ownership_conflicts = tuple(getattr(ownership, "conflicts", ()) or ())
        ownership_insufficiencies = tuple(
            getattr(ownership, "insufficiencies", ()) or ()
        )
        if ownership_conflicts or ownership_insufficiencies:
            recommendation = self.recommendation_engine.rank(
                (), recommendation_context, rejection_count=0
            )
            return self._result(
                started=started, channel=channel, selected=None,
                constraints=constraints,
                reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                evaluations=(), candidate_count=0, purchased=purchased,
                active_intent=active_purchase_intent is not None,
                extra_exclusions=(
                    "OWNERSHIP_CONFLICT"
                    if ownership_conflicts
                    else "OWNERSHIP_EVIDENCE_INSUFFICIENT",
                ),
                recommendation=recommendation, strategy=strategy,
            )
        if ownership.owned_asset_ids:
            constraints = replace(
                constraints,
                excluded_asset_ids=tuple(sorted(set((
                    *constraints.excluded_asset_ids,
                    *ownership.owned_asset_ids,
                )))),
            )

        if active_purchase_intent is not None:
            candidate = self.repository.get_candidate(
                active_purchase_intent.commercial_offering_id,
                creator_profile_id=int(creator_profile_id),
            )
            if candidate is None:
                recommendation = self.recommendation_engine.rank(
                    (), recommendation_context, rejection_count=0
                )
                return self._result(
                    started=started, channel=channel, selected=None,
                    constraints=constraints,
                    reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                    evaluations=(), candidate_count=0, purchased=purchased,
                    active_intent=True,
                    extra_exclusions=("ACTIVE_INTENT_OFFERING_UNAVAILABLE",),
                    recommendation=recommendation,
                )
            evaluation = self._evaluate(
                candidate, creator_profile_id=int(creator_profile_id),
                channel=channel, purchased=frozenset(),
                constraints=constraints,
            )
            if evaluation.eligible:
                recommendation = self._rank(
                    (candidate,), recommendation_context, rejection_count=0
                )
                return self._result(
                    started=started, channel=channel,
                    constraints=constraints,
                    selected=self._selected_projection(
                        (candidate,), recommendation
                    ),
                    reason=OfferingSelectionReason(
                        recommendation.selection_reason
                    ),
                    evaluations=(evaluation,), candidate_count=1,
                    purchased=purchased, active_intent=True,
                    recommendation=recommendation,
                )
            recommendation = self.recommendation_engine.rank(
                (), recommendation_context, rejection_count=1
            )
            return self._result(
                started=started, channel=channel, selected=None,
                constraints=constraints,
                reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                evaluations=(evaluation,), candidate_count=1,
                purchased=purchased, active_intent=True,
                recommendation=recommendation,
            )

        if context.get("controlled_test_commerce") is True:
            getter = getattr(self.repository, "get_controlled_test_candidate", None)
            candidate = getter(creator_profile_id=int(creator_profile_id)) if getter else None
            if candidate is None:
                recommendation = self.recommendation_engine.rank(
                    (), recommendation_context, rejection_count=0
                )
                return self._result(
                    started=started, channel=channel, selected=None,
                    constraints=constraints,
                    reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                    evaluations=(), candidate_count=0, purchased=purchased,
                    active_intent=False, extra_exclusions=("CONTROLLED_TEST_OFFERING_UNAVAILABLE",),
                    recommendation=recommendation, strategy="CONTROLLED_TEST_DESIGNATED",
                )
            evaluation = self._evaluate(
                candidate, creator_profile_id=int(creator_profile_id),
                channel=channel, purchased=purchased, constraints=constraints,
            )
            eligible = (candidate,) if evaluation.eligible else ()
            recommendation = self._rank(
                eligible, recommendation_context,
                rejection_count=0 if evaluation.eligible else 1,
            )
            return self._result(
                started=started, channel=channel,
                constraints=constraints,
                selected=(self._selected_projection(eligible, recommendation)
                          if evaluation.eligible else None),
                reason=(OfferingSelectionReason(recommendation.selection_reason)
                        if evaluation.eligible else OfferingSelectionReason.NO_ELIGIBLE_OFFERING),
                evaluations=(evaluation,), candidate_count=1, purchased=purchased,
                active_intent=False, recommendation=recommendation,
                strategy="CONTROLLED_TEST_DESIGNATED",
                bound_offering_id=bound_offering_id,
                offering_continuity_source=(
                    "PERSISTED_PROGRESSION"
                    if evaluation.eligible
                    and bound_offering_id == UUID(str(candidate["offering_id"]))
                    else "RESET_AFTER_INVALIDATION"
                    if bound_offering_id is not None else "NEW_SELECTION"
                ),
                offering_revalidated=bound_offering_id is not None,
            )

        history_rows = (
            tuple(self.repository.list_recommendation_history(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=account_id,
                external_fanvue_user_uuid=buyer_uuid,
                telegram_user_id=telegram_user_id,
            ))
            if hasattr(self.repository, "list_recommendation_history")
            else ()
        )
        history = tuple(self._history_entry(row) for row in history_rows)
        verified = tuple(
            item for item in history
            if item.status == "PURCHASED"
            and item.attribution_result == "ATTRIBUTED"
        )
        memory_affinity = getattr(commerce_memory, "affinity", None)
        historical_tags = tuple(
            getattr(memory_affinity, "tag_weights", {}).keys()
        )
        historical_types = tuple(
            getattr(memory_affinity, "offering_type_weights", {}).keys()
        )
        learning_profile = self._learning_context(
            self.repository.get_commerce_learning_profile(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=account_id,
                external_fanvue_user_uuid=buyer_uuid,
            )
            if hasattr(self.repository, "get_commerce_learning_profile")
            else None
        )
        recommendation_context = replace(
            recommendation_context,
            verified_affinity_tags=tuple(dict.fromkeys(
                (*historical_tags, *(tag for item in verified for tag in item.intelligence_tags))
            )),
            verified_affinity_offering_types=tuple(dict.fromkeys(
                (*historical_types, *(item.offering_type for item in verified))
            )),
            recent_offer_history=history,
            commerce_learning_profile=self._merge_memory_affinity(
                learning_profile, memory_affinity
            ),
        )
        candidates = tuple(self.repository.list_candidates(
            creator_profile_id=int(creator_profile_id),
            primary_sales_channel=channel,
        ))
        evaluations = tuple(
            self._evaluate(
                candidate, creator_profile_id=int(creator_profile_id),
                channel=channel, purchased=purchased,
                constraints=constraints,
            )
            for candidate in candidates
        )
        eligible = tuple(
            candidate for candidate, evaluation in zip(
                candidates, evaluations, strict=True
            ) if evaluation.eligible
        )
        lifecycle_context = self._lifecycle_context(
            creator_profile_id, customer_profile
        )
        terminal = {
            CustomerPhotoshootStatus.COMPLETED,
            CustomerPhotoshootStatus.CLOSED,
            CustomerPhotoshootStatus.DECLINED,
        }
        eligible = tuple(candidate for candidate in eligible if not (
            candidate.get("photoshoot_identifier")
            and lifecycle_context.get(str(candidate["photoshoot_identifier"]))
            and lifecycle_context[str(candidate["photoshoot_identifier"])].status in terminal
        ))
        active = next((item for item in lifecycle_context.values()
                       if item.status in {CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION}), None)
        if active is not None:
            # An ACTIVE opportunity is exclusive.  The deterministic first
            # unpaid chapter is the only Offering allowed to reach ranking.
            eligible = (() if active.status is CustomerPhotoshootStatus.OBJECTION else
                        self._active_opportunity_candidates(
                            eligible, active, creator_profile_id, customer_profile,
                        ))
        if not eligible:
            recommendation = self.recommendation_engine.rank(
                (), recommendation_context,
                rejection_count=sum(not item.eligible for item in evaluations),
            )
            return self._result(
                started=started, channel=channel, selected=None,
                constraints=constraints,
                reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                evaluations=evaluations, candidate_count=len(candidates),
                purchased=purchased, active_intent=False,
                recommendation=recommendation,
                strategy=strategy,
                lifecycle_active=(
                    active is not None
                    and active.status is CustomerPhotoshootStatus.ACTIVE
                ),
                bound_offering_id=bound_offering_id,
                offering_continuity_source=(
                    "RESET_AFTER_INVALIDATION"
                    if bound_offering_id is not None else "NEW_SELECTION"
                ),
                offering_revalidated=bound_offering_id is not None,
            )

        bound_candidate = next((
            candidate for candidate in eligible
            if bound_offering_id is not None
            and UUID(str(candidate["offering_id"])) == bound_offering_id
        ), None)
        continuity_source = (
            "PERSISTED_PROGRESSION" if bound_candidate is not None
            else "RESET_AFTER_INVALIDATION" if bound_offering_id is not None
            else "NEW_SELECTION"
        )
        ranked_candidates = (
            (bound_candidate,) if bound_candidate is not None else eligible
        )
        recommendation = self._rank(
            ranked_candidates, recommendation_context,
            rejection_count=sum(not item.eligible for item in evaluations),
        )
        selected = self._selected_projection(ranked_candidates, recommendation)
        return self._result(
            started=started, channel=channel, selected=selected,
            constraints=constraints,
            reason=OfferingSelectionReason(recommendation.selection_reason),
            evaluations=evaluations,
            candidate_count=len(candidates), purchased=purchased,
            active_intent=False,
            recommendation=recommendation,
            strategy=strategy,
            lifecycle_active=(
                active is not None
                and active.status is CustomerPhotoshootStatus.ACTIVE
            ),
            bound_offering_id=bound_offering_id,
            offering_continuity_source=continuity_source,
            offering_revalidated=bound_offering_id is not None,
        )

    def _lifecycle_context(self, creator_profile_id, customer_profile):
        profile_id = getattr(customer_profile, "customer_commerce_profile_id", None)
        if profile_id is None:
            return {}
        try:
            service = self.photoshoot_lifecycles
            if service is None:
                from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                service = CustomerPhotoshootLifecycleService()
            return service.context_for_customer(
                creator_profile_id=int(creator_profile_id),
                customer_commerce_profile_id=profile_id,
            )
        except Exception as error:
            logger.warning("event=photoshoot_lifecycle_context_unavailable error_type=%s", type(error).__name__)
            return {}

    def _active_opportunity_candidates(self, candidates, opportunity,
                                       creator_profile_id, customer_profile):
        bundle_candidates = tuple(
            candidate for candidate in candidates
            if str(candidate.get("photoshoot_selling_mode") or "") == "BUNDLE"
            and str(candidate.get("photoshoot_identifier") or "")
                == opportunity.photoshoot_id
            and str(candidate.get("offering_type") or "") == "BUNDLE"
        )
        if bundle_candidates:
            # Bundle opportunities have one canonical prepared fulfillment.
            # Never enter Session strategy/current-next Asset resolution.
            return bundle_candidates if len(bundle_candidates) == 1 else ()
        profile_id = getattr(customer_profile, "customer_commerce_profile_id", None)
        if profile_id is None:
            return ()
        repository = self.progression_repository
        if repository is None:
            from app.repositories.autonomous_sales_progression_repository import AutonomousSalesProgressionRepository
            repository = AutonomousSalesProgressionRepository()
        assets = repository.ordered_assets(
            creator_profile_id=int(creator_profile_id),
            customer_commerce_profile_id=profile_id,
            photoshoot_id=opportunity.photoshoot_id,
        )
        ordered = tuple(sorted(assets, key=lambda item: (item.position, item.asset_id)))
        paid = tuple(item for item in ordered if item.role.value in {"CORE_SESSION", "FINALE_IMAGE"})
        selected = next((item for item in paid if not item.owned and not item.rejected), None)
        if selected is None:
            videos = tuple(item for item in ordered if item.role.value == "FINALE_VIDEO")
            selected = next((item for item in videos if not item.owned and not item.rejected), None)
        if selected is None or selected.offering_id is None:
            return ()
        return tuple(candidate for candidate in candidates
                     if UUID(str(candidate["offering_id"])) == selected.offering_id
                     and str(candidate.get("photoshoot_identifier") or "") == opportunity.photoshoot_id)

    def _evaluate(
        self, candidate, *, creator_profile_id: int, channel: str,
        purchased: frozenset[UUID],
        constraints: StrategyConstraints | None = None,
    ) -> OfferingEligibilityEvaluation:
        constraints = constraints or StrategyConstraints()
        reasons: list[str] = []
        if candidate.get("commercially_eligible") is False:
            reasons.append(
                OfferingExclusionReason.CANONICAL_REFERENCE_ASSET.value
            )
        status = str(candidate.get("offering_status") or "")
        if int(candidate.get("creator_profile_id") or 0) != creator_profile_id:
            reasons.append(OfferingExclusionReason.CREATOR_MISMATCH.value)
        if status == "ARCHIVED":
            reasons.append(OfferingExclusionReason.OFFERING_ARCHIVED.value)
        elif status != "READY":
            reasons.append(OfferingExclusionReason.OFFERING_NOT_ACTIVE.value)
        if str(candidate.get("primary_sales_channel") or "") != channel:
            reasons.append(
                OfferingExclusionReason.SALES_CHANNEL_MISMATCH.value
            )
        if candidate.get("publication_status") != "LIVE":
            reasons.append(
                OfferingExclusionReason.PUBLICATION_NOT_LIVE.value
            )
        if not candidate.get("provider"):
            reasons.append(
                OfferingExclusionReason.PROVIDER_NOT_ENABLED.value
            )
        if candidate.get("provider_resource_status") != "PRESENT":
            reasons.append(
                OfferingExclusionReason.PROVIDER_RESOURCE_NOT_PRESENT.value
            )
        if not candidate.get("delivery_url"):
            reasons.append(
                OfferingExclusionReason.DELIVERY_URL_MISSING.value
            )
        if (
            candidate.get("price_minor") is None
            or not 300 <= int(candidate["price_minor"]) <= 50000
        ):
            reasons.append(OfferingExclusionReason.PRICE_INVALID.value)
        destination_reason = self._destination_reason(candidate)
        if destination_reason:
            reasons.append(destination_reason)
        offering_id = UUID(str(candidate["offering_id"]))
        offering_type = str(candidate.get("offering_type") or "")
        selling_mode = str(candidate.get("photoshoot_selling_mode") or "")
        if (
            constraints.required_selling_modes
            and selling_mode not in constraints.required_selling_modes
        ):
            reasons.append("STRATEGY_SELLING_MODE_MISMATCH")
        if selling_mode in constraints.excluded_selling_modes:
            reasons.append("STRATEGY_SELLING_MODE_EXCLUDED")
        if (
            offering_type == "SINGLE_IMAGE"
            and candidate.get("source_photoshoot_deliverable_id") is None
            and candidate.get("source_bundle_studio_bundle_id") is None
            and candidate.get("standalone_sale_destination") != "CHAT"
        ):
            reasons.append("STANDALONE_DESTINATION_NOT_CHAT")
        bundle_channel = str(
            candidate.get("photoshoot_bundle_sales_channel") or "CHAT"
        )
        if selling_mode == "BUNDLE" and bundle_channel != "CHAT":
            reasons.append("BUNDLE_CHANNEL_CONTENT_WALL")
        if selling_mode == "BUNDLE" and offering_type != "BUNDLE":
            reasons.append("BUNDLE_MEMBER_OFFERING_SUPPRESSED")
        if offering_type == "BUNDLE":
            if selling_mode != "BUNDLE":
                reasons.append("BUNDLE_SELLING_MODE_MISMATCH")
            if not (
                candidate.get("bundle_teaser_asset_id")
                and candidate.get("bundle_teaser_source_asset_id")
                and candidate.get("bundle_teaser_registered") is True
            ):
                reasons.append("BUNDLE_TEASER_NOT_READY")
        if (
            constraints.required_offering_types
            and offering_type not in constraints.required_offering_types
        ):
            reasons.append("STRATEGY_OFFERING_TYPE_MISMATCH")
        if offering_type in constraints.excluded_offering_types:
            reasons.append("STRATEGY_OFFERING_TYPE_EXCLUDED")
        photoshoot = (
            str(candidate["photoshoot_identifier"])
            if candidate.get("photoshoot_identifier") is not None else None
        )
        if (
            constraints.required_photoshoot_reference
            and photoshoot != constraints.required_photoshoot_reference
        ):
            reasons.append("STRATEGY_PHOTOSHOOT_MISMATCH")
        roles = frozenset(
            str(value) for value in candidate.get("commercial_roles") or ()
        )
        content_types = frozenset(
            str(value).lower() for value in candidate.get("asset_content_types") or ()
        )
        if photoshoot and (
            roles.intersection({"TEASER", "DISCOVERY"})
            or any(value.startswith("teaser") for value in content_types)
        ):
            reasons.append("PROTECTED_PHOTOSHOOT_TEASER_NOT_SELLABLE")
        if constraints.progression:
            if not roles:
                reasons.append("STRATEGY_ROLE_EVIDENCE_MISSING")
            elif constraints.progression not in roles:
                reasons.append("STRATEGY_PROGRESSION_MISMATCH")
        approved_roles = frozenset(constraints.approved_commercial_roles)
        if approved_roles and roles and not roles.intersection(approved_roles):
            reasons.append("STRATEGY_COMMERCIAL_ROLE_MISMATCH")
        asset_ids = frozenset(
            int(value) for value in candidate.get("asset_ids") or ()
        )
        owned_overlap = asset_ids.intersection(constraints.excluded_asset_ids)
        if owned_overlap:
            reasons.append(
                (
                    "BUNDLE_FULLY_OWNED"
                    if offering_type == "BUNDLE"
                    and asset_ids
                    and owned_overlap == asset_ids
                    else "BUNDLE_PARTIALLY_OWNED"
                )
                if offering_type == "BUNDLE"
                else "OFFERING_CONTAINS_OWNED_VALUE"
            )
        if constraints.complete_set_required and offering_type != "BUNDLE":
            reasons.append("COMPLETE_SET_REQUIRES_BUNDLE")
        if offering_type == "BUNDLE":
            bundle_studio_source = candidate.get("source_bundle_studio_bundle_id")
            if not bundle_studio_source:
                lineages = tuple(
                    str(value)
                    for value in candidate.get("photoshoot_identifiers") or ()
                )
                if len(lineages) != 1:
                    reasons.append("BUNDLE_PHOTOSHOOT_LINEAGE_INVALID")
        if offering_id in purchased:
            reasons.append(
                OfferingExclusionReason.OFFERING_ALREADY_PURCHASED.value
            )
        if offering_id in frozenset(constraints.excluded_offering_ids):
            reasons.append(
                OfferingExclusionReason.OFFERING_REJECTED_CURRENT_SEQUENCE.value
            )
        if (
            constraints.maximum_price_minor is not None
            and candidate.get("price_minor") is not None
            and int(candidate["price_minor"]) > int(constraints.maximum_price_minor)
        ):
            reasons.append(
                OfferingExclusionReason.PRICE_NOT_MATERIALLY_LOWER.value
            )
        unique_reasons = tuple(dict.fromkeys(reasons))
        evaluation = OfferingEligibilityEvaluation(
            offering_id=offering_id,
            title=str(candidate.get("title") or ""),
            eligible=not unique_reasons,
            exclusion_reasons=unique_reasons,
            publication_id=(
                UUID(str(candidate["publication_id"]))
                if candidate.get("publication_id") else None
            ),
            publication_provider=candidate.get("provider"),
            publication_status=candidate.get("publication_status"),
            delivery_url_available=bool(candidate.get("delivery_url")),
            offering_status=status,
            offering_type=str(candidate.get("offering_type") or ""),
            primary_sales_channel=str(
                candidate.get("primary_sales_channel") or ""
            ),
            published_at=(
                candidate["published_at"].isoformat()
                if candidate.get("published_at") else None
            ),
        )
        logger.info(
            "event=offer_evaluated offering_id=%s eligible=%s "
            "rejection_reasons=%s",
            offering_id, evaluation.eligible,
            ",".join(unique_reasons) or "NONE",
        )
        return evaluation

    @staticmethod
    def _destination_reason(candidate) -> str | None:
        offering_type = str(candidate.get("offering_type") or "")
        destinations = tuple(candidate.get("destinations") or ())
        expected = (
            "SINGLE_PPV" if offering_type in {"SINGLE_IMAGE", "VIDEO"}
            else "PHOTOSET" if offering_type == "PHOTOSET"
            else "BUNDLE" if offering_type == "BUNDLE" else None
        )
        if offering_type == "BUNDLE":
            allowed = {"BUNDLE", "PHOTOSET", "SINGLE_PPV", "VIDEOSET"}
            if destinations and all(value in allowed for value in destinations):
                return None
        if (
            expected is None
            or not destinations
            or any(value != expected for value in destinations)
        ):
            return (
                OfferingExclusionReason
                .DESTINATION_NOT_COMMERCIALLY_AVAILABLE.value
            )
        return None

    def _rank(self, eligible, context, *, rejection_count):
        candidates = tuple(
            RecommendationCandidate.from_eligible_projection(
                self._enriched_projection(candidate)
            )
            for candidate in eligible
        )
        photoshoot_groups: dict[str, list[RecommendationCandidate]] = {}
        for candidate in candidates:
            if candidate.photoshoot_identifier:
                photoshoot_groups.setdefault(
                    candidate.photoshoot_identifier, []
                ).append(candidate)
        standalone = tuple(
            candidate for candidate in candidates
            if not candidate.photoshoot_identifier
        )
        experiences = tuple(
            self._aggregate_photoshoot_candidate(group, context)
            for _, group in sorted(photoshoot_groups.items())
        )
        return self.recommendation_engine.rank(
            (*standalone, *experiences), context,
            rejection_count=rejection_count,
        )

    def _aggregate_photoshoot_candidate(self, group, context):
        """Aggregate one Photoshoot while retaining one Offering for fulfillment."""
        fulfillment = self.recommendation_engine.rank(tuple(group), context)
        selected = fulfillment.selected_candidate
        if selected is None:
            raise ValueError("Photoshoot has no eligible fulfillment Offering.")
        intelligence: dict[str, list[str]] = {}
        member_ids: list[int] = []
        for candidate in group:
            member_ids.extend(candidate.member_asset_ids)
            for key, values in candidate.intelligence.items():
                intelligence.setdefault(key, []).extend(values)
        return RecommendationCandidate(
            offering_id=selected.offering_id,
            creator_profile_id=selected.creator_profile_id,
            title=selected.title,
            description=selected.description,
            offering_type=selected.offering_type,
            price_minor=selected.price_minor,
            currency=selected.currency,
            published_at=max(
                (item.published_at for item in group if item.published_at),
                default=None,
            ),
            publication_id=selected.publication_id,
            delivery_url=selected.delivery_url,
            hero_asset_id=selected.hero_asset_id,
            member_asset_ids=tuple(dict.fromkeys(member_ids)),
            commercially_eligible=True,
            photoshoot_identifier=selected.photoshoot_identifier,
            intelligence={
                key: tuple(dict.fromkeys(values))
                for key, values in intelligence.items()
            },
            blurred_teaser_path=selected.blurred_teaser_path,
            selling_mode=selected.selling_mode,
            member_count=len(tuple(dict.fromkeys(member_ids))),
        )

    @staticmethod
    def _buyer_stage(customer_profile, context):
        explicit = str(context.get("buyer_stage") or "").strip().upper()
        if explicit:
            return explicit
        purchases = int(getattr(customer_profile, "purchase_count", 0) or 0)
        return "REPEAT_BUYER" if purchases >= 2 else "FIRST_BUYER" if purchases else "PROSPECT"

    @staticmethod
    def _merge_memory_affinity(learning_profile, affinity):
        result = dict(learning_profile or {})
        if affinity is None:
            return result
        preferences = {
            key: dict(value) if isinstance(value, dict) else value
            for key, value in dict(result.get("preferences") or {}).items()
        }
        tags = dict(getattr(affinity, "tag_weights", {}) or {})
        types = dict(getattr(affinity, "offering_type_weights", {}) or {})
        if tags:
            historical = dict(preferences.get("historical_purchase") or {})
            for tag, weight in tags.items():
                historical.setdefault(tag, {
                    "score": float(weight), "confidence": float(weight),
                    "source": "CustomerCommerceMemory",
                })
            preferences["historical_purchase"] = historical
        if types and not result.get("preferredOfferingType"):
            result["preferredOfferingType"] = next(iter(types))
        minimum = getattr(affinity, "typical_price_min_minor", None)
        maximum = getattr(affinity, "typical_price_max_minor", None)
        if minimum is not None and result.get("preferredPriceMinMinor") is None:
            result["preferredPriceMinMinor"] = minimum
        if maximum is not None and result.get("preferredPriceMaxMinor") is None:
            result["preferredPriceMaxMinor"] = maximum
        result["preferences"] = preferences
        result["customerCommerceMemory"] = {
            "historicalPurchaseCount": getattr(affinity, "historical_purchase_count", 0),
            "recentPurchaseCount": getattr(affinity, "recent_purchase_count", 0),
            "offeringTypeWeights": types,
            "tagWeights": tags,
            "channelWeights": dict(getattr(affinity, "channel_weights", {}) or {}),
        }
        return result

    @staticmethod
    def _engagement_score(context):
        raw = context.get("engagement_score", context.get("intent_score", 0))
        try:
            value = float(raw or 0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, value / 100 if value > 1 else value))

    @staticmethod
    def _price_sensitive(context):
        if context.get("price_sensitive") is not None:
            return bool(context["price_sensitive"])
        message = str(context.get("latest_message") or "").lower()
        return any(term in message for term in ProductTypeFitStrategy.PRICE_TERMS)

    @classmethod
    def _enriched_projection(cls, candidate):
        value = dict(candidate)
        intelligence: dict[str, list[str]] = {}
        for asset in cls._sequence(value.get("asset_intelligence")):
            profile = (
                asset.get("profile_data", {})
                if isinstance(asset, dict) else {}
            )
            cls._merge_intelligence(intelligence, profile)
        cls._merge_intelligence(
            intelligence, cls._mapping(value.get("photoshoot_intelligence")),
            prefix="photoshoot_",
        )
        value["recommendation_intelligence"] = {
            key: tuple(dict.fromkeys(items))
            for key, items in intelligence.items() if items
        }
        return value

    @classmethod
    def _history_entry(cls, row):
        value = dict(row)
        intelligence: dict[str, list[str]] = {}
        for profile in cls._sequence(value.get("asset_intelligence")):
            cls._merge_intelligence(intelligence, cls._mapping(profile))
        tags = tuple(dict.fromkeys(
            item.lower().strip()
            for items in intelligence.values() for item in items
            if item.strip()
        ))
        return RecommendationHistoryEntry(
            offering_id=UUID(str(value["commercial_offering_id"])),
            offering_type=str(value.get("offering_type") or ""),
            status=str(
                getattr(value.get("status"), "value", value.get("status") or "")
            ),
            presented_at=value.get("presented_at"),
            purchased_at=value.get("purchased_at"),
            attribution_result=str(
                getattr(
                    value.get("attribution_result"), "value",
                    value.get("attribution_result") or "",
                )
            ),
            photoshoot_identifier=(
                str(value["photoshoot_identifier"])
                if value.get("photoshoot_identifier") else None
            ),
            intelligence_tags=tags,
        )

    @staticmethod
    def _mapping(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _sequence(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return ()
        return tuple(value) if isinstance(value, (list, tuple)) else ()

    @classmethod
    def _merge_intelligence(cls, target, profile, prefix=""):
        aliases = {
            "location_type": "location", "short_description": "content_summary",
            "detailed_description": "content_summary",
            "suggested_collections": "themes", "tags": "keywords",
            "clothing": "clothing", "pose": "pose", "activity": "activity",
            "setting": "setting", "environment": "environment",
            "themes": "themes", "keywords": "keywords",
            "search_phrases": "search_phrases", "mood": "mood",
            "atmosphere": "atmosphere", "emotional_tone": "emotional_tone",
            "visual_style": "visual_style", "content_summary": "content_summary",
        }
        for source, destination in aliases.items():
            raw = profile.get(source) if isinstance(profile, dict) else None
            values = (
                raw if isinstance(raw, (list, tuple))
                else (raw,) if raw is not None else ()
            )
            clean = [
                str(item).strip() for item in values
                if str(item).strip()
            ]
            if clean:
                target.setdefault(prefix + destination, []).extend(clean)

    @staticmethod
    def _learning_context(profile):
        if profile is None:
            return {}
        return {
            "preferences": dict(profile.preferences or {}),
            "preferredOfferingType": profile.preferred_offering_type,
            "favoriteMediaType": profile.favorite_media_type,
            "averagePriceMinor": profile.average_price_minor,
            "preferredPriceMinMinor": profile.preferred_price_min_minor,
            "preferredPriceMaxMinor": profile.preferred_price_max_minor,
            "repeatPurchaseFrequency": profile.repeat_purchase_frequency,
            "confidence": profile.confidence,
            "evidenceCount": profile.evidence_count,
        }

    @staticmethod
    def _selected_projection(eligible, recommendation):
        selected = recommendation.selected_candidate
        if selected is None:
            return None
        return next(
            candidate for candidate in eligible
            if UUID(str(candidate["offering_id"])) == selected.offering_id
        )

    def _result(
        self, *, started, channel, selected, reason, evaluations,
        candidate_count, purchased, active_intent,
        constraints=None,
        extra_exclusions=(), recommendation=None, strategy=None,
        lifecycle_active=False,
        bound_offering_id=None, offering_continuity_source="NEW_SELECTION",
        offering_revalidated=False,
    ):
        constraints = constraints or StrategyConstraints()
        exclusion_counts = {}
        for evaluation in evaluations:
            for exclusion_reason in evaluation.exclusion_reasons:
                exclusion_counts[exclusion_reason] = (
                    exclusion_counts.get(exclusion_reason, 0) + 1
                )
        exclusions = tuple(dict.fromkeys((
            *extra_exclusions,
            *(
                value
                for evaluation in evaluations
                for value in evaluation.exclusion_reasons
            ),
        )))
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        experience = self._photoshoot_experience(recommendation)
        product_context = self._product_context(selected)
        asset_intelligence = dict(product_context.get("assetIntelligence") or {})
        result = SelectedOfferingResult(
            offering_id=(
                UUID(str(selected["offering_id"])) if selected else None
            ),
            publication_id=(
                UUID(str(selected["publication_id"]))
                if selected and selected.get("publication_id") else None
            ),
            publication_provider=(
                selected.get("provider") if selected else None
            ),
            delivery_url=(
                selected.get("delivery_url") if selected else None
            ),
            offering_type=(
                selected.get("offering_type") if selected else None
            ),
            primary_sales_channel=(
                selected.get("primary_sales_channel") if selected else None
            ),
            selection_reason=reason,
            exclusion_reasons=exclusions,
            evaluations=tuple(evaluations),
            selector_metadata=immutable_selector_metadata({
                "candidateCount": candidate_count,
                "eligibleCount": sum(
                    evaluation.eligible for evaluation in evaluations
                ),
                "rejectedCount": sum(
                    not evaluation.eligible for evaluation in evaluations
                ),
                "rejectedCandidateCountsByReason": exclusion_counts,
                "candidateEvaluations": [
                    {
                        "offeringId": str(evaluation.offering_id),
                        "title": evaluation.title,
                        "offeringType": evaluation.offering_type,
                        "offeringStatus": evaluation.offering_status,
                        "primarySalesChannel": evaluation.primary_sales_channel,
                        "publicationStatus": evaluation.publication_status,
                        "eligible": evaluation.eligible,
                        "exclusionReasons": list(evaluation.exclusion_reasons),
                    }
                    for evaluation in evaluations
                ],
                "purchasedOfferingCount": len(purchased),
                "activeIntentApplied": active_intent,
                "strategy": strategy,
                "primarySalesChannel": channel,
                "featuredSupported": False,
                "ordering": (
                    "ACTIVE_INTENT, FEATURED_IF_SUPPORTED, "
                    "PUBLISHED_AT_DESC, OFFERING_ID_ASC"
                ),
                "selectorTimingMs": elapsed,
                "evaluatedAt": self.clock().isoformat(),
                "recommendationEngineVersion": (
                    recommendation.engine_version if recommendation else None
                ),
                "recommendationTrace": (
                    [
                        {
                            "rank": ranked.rank,
                            "offeringId": str(ranked.candidate.offering_id),
                            "title": ranked.candidate.title,
                            "offeringType": ranked.candidate.offering_type,
                            "priceMinor": ranked.candidate.price_minor,
                            "currency": ranked.candidate.currency,
                            "publishedAt": (
                                ranked.candidate.published_at.isoformat()
                                if ranked.candidate.published_at else None
                            ),
                            "activeIntentMatch": (
                                next(
                                    component.raw_value
                                    for component in ranked.components
                                    if component.key
                                    == "active_purchase_intent"
                                )
                            ),
                            "components": [
                                {
                                    "key": component.key,
                                    "rawValue": component.raw_value,
                                    "weightedContribution": (
                                        component.contribution
                                    ),
                                    "weight": (
                                        self.recommendation_engine.weights.for_key(
                                            component.key
                                        )
                                        if component.key
                                        != "active_purchase_intent" else None
                                    ),
                                    "explanation": component.explanation,
                                    "affectedRanking": (
                                        component.affected_ranking
                                    ),
                                    "evidence": dict(component.evidence),
                                }
                                for component in ranked.components
                            ],
                            "reason": ranked.deterministic_reason,
                            "selected": ranked.selected,
                            "finalScore": ranked.final_score,
                            "tieBreak": {
                                "publishedAtDescending": (
                                    ranked.candidate.published_at.isoformat()
                                    if ranked.candidate.published_at else None
                                ),
                                "offeringIdAscending": str(
                                    ranked.candidate.offering_id
                                ),
                            },
                        }
                        for ranked in recommendation.ranked_candidates
                    ] if recommendation else []
                ),
                "recommendationSummary": (
                    recommendation.recommendation_summary
                    if recommendation else None
                ),
                "opportunityReasonCode": self._opportunity_reason_code(
                    recommendation, active_intent=active_intent,
                    lifecycle_active=lifecycle_active,
                ),
                "recommendationLayer": (
                    "PHOTOSHOOT_EXPERIENCE"
                    if experience else "COMMERCIAL_OFFERING_FALLBACK"
                ),
                "selectedPhotoshootId": (
                    experience.photoshoot_id if experience else None
                ),
                "fulfillmentOfferingId": (
                    str(experience.commercial_offering_id)
                    if experience else None
                ),
                "unsupportedSchemaRules": [
                    "offering_expiration",
                    "offering_withdrawn",
                    "offering_disabled",
                    "featured_flag",
                ],
                "boundOfferingId": (
                    str(bound_offering_id) if bound_offering_id else None
                ),
                "offeringContinuitySource": offering_continuity_source,
                "offeringRevalidated": bool(offering_revalidated),
                "recoveryConstraints": {
                    "excludedOfferingIds": [
                        str(value) for value in constraints.excluded_offering_ids
                    ],
                    "maximumPriceMinor": constraints.maximum_price_minor,
                    "requestedThemes": list(constraints.requested_themes),
                },
                "contentIntelligenceAvailable": bool(asset_intelligence),
                "contentIntelligenceSource": (
                    "ASSET_INTELLIGENCE_PROFILE"
                    if asset_intelligence else "NONE"
                ),
            }),
            title=(str(selected.get("title") or "") if selected else None),
            short_description=(
                str(selected.get("description") or "") if selected else None
            ),
            price_minor=(
                int(selected["price_minor"])
                if selected and selected.get("price_minor") is not None
                else None
            ),
            currency=(
                str(selected.get("currency") or "") if selected else None
            ),
            recommendation_result=recommendation,
            photoshoot_experience=experience,
            product_context=immutable_selector_metadata(
                product_context
            ),
        )
        logger.info(
            "event=offer_selected offering_id=%s selection_reason=%s "
            "selector_timing_ms=%s",
            result.offering_id, reason.value, elapsed,
        )
        return result

    @staticmethod
    def _opportunity_reason_code(
        recommendation, *, active_intent, lifecycle_active=False,
    ):
        if lifecycle_active:
            return "CONTINUE_ACTIVE_SESSION"
        if active_intent:
            return "CONTINUE_ACTIVE_PURCHASE_INTENT"
        if recommendation is None or not recommendation.ranked_candidates:
            return None
        selected = next(
            (item for item in recommendation.ranked_candidates if item.selected),
            recommendation.ranked_candidates[0],
        )
        component = next(
            (item for item in selected.components if item.key == "product_type_fit"),
            None,
        )
        return (
            str(component.evidence.get("reasonCode"))
            if component and component.evidence.get("reasonCode") else None
        )

    @classmethod
    def _product_context(cls, selected):
        if not selected:
            return {}
        offering_type = str(selected.get("offering_type") or "")
        selling_mode = str(selected.get("photoshoot_selling_mode") or "") or None
        context = {
            "offeringType": offering_type,
            "sellingMode": selling_mode,
            "heroAssetId": selected.get("hero_asset_id"),
            "memberCount": len(tuple(selected.get("asset_ids") or ())),
        }
        if offering_type != "SINGLE_IMAGE" or selling_mode:
            return context
        profiles = cls._sequence(selected.get("asset_intelligence"))
        hero_id = selected.get("hero_asset_id")
        profile = next((
            cls._mapping(item.get("profile_data"))
            for item in profiles if isinstance(item, dict)
            and int(item.get("asset_id") or 0) == int(hero_id or 0)
        ), {})
        aliases = {
            "title": ("title",),
            "contentSummary": ("content_summary", "short_description"),
            "sceneEnvironment": ("scene_environment", "environment", "setting"),
            "verifiedVisibleContent": ("verified_visible_content", "detailed_description"),
            "poseAction": ("pose_action", "pose", "activity"),
            "wardrobeState": ("wardrobe_state", "clothing"),
            "facialExpression": ("facial_expression", "expression"),
            "gaze": ("eye_contact", "gaze"),
            "explicitness": ("nudity_explicitness", "safety_classification", "explicit_content"),
            "moodTone": ("emotional_tone", "mood", "atmosphere"),
            "visualFocus": ("visual_focus",),
        }
        intelligence = {}
        for output, keys in aliases.items():
            value = next((profile.get(key) for key in keys
                          if profile.get(key) not in (None, "", [], {})), None)
            if value is not None:
                intelligence[output] = cls._bounded_intelligence_value(value)
        context["assetIntelligence"] = intelligence
        context["standaloneDestination"] = selected.get("standalone_sale_destination")
        return context

    @classmethod
    def _bounded_intelligence_value(cls, value):
        if isinstance(value, str):
            return value.strip()[:240]
        if isinstance(value, (list, tuple, set)):
            return tuple(
                str(item).strip()[:80] for item in tuple(value)[:8]
                if str(item).strip()
            )
        if isinstance(value, dict):
            return {
                str(key)[:40]: cls._bounded_intelligence_value(item)
                for key, item in list(value.items())[:8]
            }
        return value

    @staticmethod
    def _photoshoot_experience(recommendation):
        if recommendation is None or recommendation.selected_candidate is None:
            return None
        selected = recommendation.selected_candidate
        if not selected.photoshoot_identifier:
            return None
        ranked = next(
            item for item in recommendation.ranked_candidates if item.selected
        )
        themes = (
            selected.intelligence.get("photoshoot_themes")
            or selected.intelligence.get("themes")
            or ()
        )
        return PhotoshootExperienceRecommendation(
            photoshoot_id=selected.photoshoot_identifier,
            title=selected.title,
            theme=themes[0] if themes else None,
            description=selected.description,
            hero_asset_id=selected.hero_asset_id,
            supporting_asset_ids=tuple(
                asset_id
                for asset_id in selected.member_asset_ids
                if asset_id != selected.hero_asset_id
            ),
            photoshoot_intelligence=selected.intelligence,
            commercial_offering_id=selected.offering_id,
            commercial_publication_id=selected.publication_id,
            delivery_url=selected.delivery_url,
            recommendation_score=ranked.final_score,
            recommendation_explanation=ranked.deterministic_reason,
            fulfillment_offering_type=selected.offering_type,
            fulfillment_price_minor=selected.price_minor,
            fulfillment_currency=selected.currency,
            metadata={
                "recommendationLayer": "PHOTOSHOOT_EXPERIENCE",
                "fulfillmentLayer": "COMMERCIAL_OFFERING",
                "engineVersion": recommendation.engine_version,
            },
        )
