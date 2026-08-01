"""Canonical read-only ownership questions over existing authorities."""

from __future__ import annotations

from types import MappingProxyType
from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID

from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer,
    CoverageState,
    OwnershipAnswerState,
    OwnershipCoverage,
    OwnershipEvidence,
    OwnershipIdentity,
    OwnershipLifecycle,
    OwnershipLineageContext,
    OwnershipSource,
    OwnershipWorkspaceView,
    SessionOwnershipCoverage,
    SessionPurchaseChronology,
    immutable_details,
)
from app.repositories.ownership_intelligence_repository import (
    OwnershipIntelligenceRepository,
)
from app.services.asset_lineage_service import AssetLineageService


class OwnershipIntelligenceService:
    def __init__(self, repository=None, lineage_service=None) -> None:
        self.repository = repository or OwnershipIntelligenceRepository()
        self.lineage = lineage_service or AssetLineageService()

    def answer(self, identity: OwnershipIdentity) -> CanonicalOwnershipAnswer:
        insufficiencies = list(self._identity_insufficiencies(identity))
        evidence = ()
        if not insufficiencies:
            try:
                evidence = self.repository.evidence_for(identity)
            except Exception as error:
                insufficiencies.append(
                    f"OWNERSHIP_SOURCE_UNAVAILABLE:{type(error).__name__}"
                )
                evidence = (OwnershipEvidence(
                    source=OwnershipSource.SOURCE_UNAVAILABLE,
                    lifecycle=OwnershipLifecycle.INCOMPLETE,
                    identity_path=self._identity_path(identity),
                    supporting_record_id=None,
                    creator_profile_id=(
                        identity.creator_profile_id
                        if identity.creator_profile_id > 0 else None
                    ),
                    fanvue_account_id=(
                        identity.fanvue_account_id
                        if identity.fanvue_account_id > 0 else None
                    ),
                    details=immutable_details({
                        "source": "OwnershipIntelligenceRepository",
                        "errorType": type(error).__name__,
                    }),
                ),)
        positive = tuple(item for item in evidence if item.proves_ownership)
        offerings = tuple(sorted({
            item.offering_id for item in positive if item.offering_id is not None
        }, key=str))
        products = tuple(sorted({
            item.product_id for item in positive if item.product_id is not None
        }, key=str))
        assets = tuple(sorted({
            asset_id for item in positive for asset_id in item.asset_ids
        }))
        insufficiencies.extend(
            "LEGACY_CANONICAL_ASSET_MAPPING_MISSING"
            for item in evidence
            if item.source is OwnershipSource.LEGACY_OWNERSHIP
            and item.lifecycle is OwnershipLifecycle.INCOMPLETE
        )
        insufficiencies = tuple(dict.fromkeys(insufficiencies))
        conflicts = self._conflicts(evidence)
        state = (
            OwnershipAnswerState.CONFLICTING if conflicts
            else OwnershipAnswerState.INSUFFICIENT if insufficiencies
            else OwnershipAnswerState.CONFIRMED_OWNERSHIP if positive
            else OwnershipAnswerState.NO_DEMONSTRATED_OWNERSHIP
        )
        lifecycle_summary = {
            lifecycle.value: sum(
                item.lifecycle is lifecycle for item in evidence
            )
            for lifecycle in OwnershipLifecycle
            if any(item.lifecycle is lifecycle for item in evidence)
        }
        asset_provenance = {
            str(asset_id): tuple(
                {
                    "source": item.source.value,
                    "recordId": item.supporting_record_id,
                    "identityPath": item.identity_path,
                    "lifecycle": item.lifecycle.value,
                }
                for item in evidence if asset_id in item.asset_ids
            )
            for asset_id in assets
        }
        answer = CanonicalOwnershipAnswer(
            identity=identity, evidence=evidence,
            owned_offering_ids=offerings, owned_product_ids=products,
            owned_asset_ids=assets, conflicts=conflicts,
            insufficiencies=insufficiencies,
            state=state,
            diagnostics=MappingProxyType({
                "question": "CUSTOMER_OWNERSHIP",
                "answerState": state.value,
                "evaluatedAt": datetime.now(timezone.utc).isoformat(),
                "creatorProfileId": identity.creator_profile_id,
                "fanvueAccountId": identity.fanvue_account_id,
                "identityPaths": tuple(dict.fromkeys(
                    item.identity_path for item in evidence
                )) or (self._identity_path(identity),),
                "evidenceCount": len(evidence),
                "positiveEvidenceCount": len(positive),
                "ownedOfferingCount": len(offerings),
                "ownedProductCount": len(products),
                "ownedAssetCount": len(assets),
                "conflictCount": len(conflicts),
                "insufficiencyCount": len(insufficiencies),
                "lifecycleSummary": MappingProxyType(lifecycle_summary),
                "assetProvenance": MappingProxyType(asset_provenance),
                "conflicts": conflicts,
                "insufficiencies": insufficiencies,
            }),
        )
        contexts = {}
        for asset_id in answer.owned_asset_ids:
            try:
                contexts[int(asset_id)] = self.lineage_context(
                    answer, asset_id, self.lineage
                )
            except Exception:
                # Lineage is optional context and cannot weaken or invalidate
                # an otherwise authoritative ownership answer.
                continue
        return replace(
            answer, lineage_contexts=MappingProxyType(contexts)
        )

    def owns_offering(self, answer, offering_id) -> bool:
        return UUID(str(offering_id)) in answer.owned_offering_ids

    def owns_product(self, answer, product_id) -> bool:
        return UUID(str(product_id)) in answer.owned_product_ids

    @staticmethod
    def owns_asset(answer, asset_id) -> bool:
        return int(asset_id) in answer.owned_asset_ids

    def offering_coverage(self, answer, offering_id) -> OwnershipCoverage:
        try:
            represented = self.repository.offering_assets(
                offering_id,
                creator_profile_id=answer.identity.creator_profile_id,
            )
        except Exception as error:
            return self._coverage(
                answer, (), insufficiencies=(
                    f"OFFERING_COMPOSITION_UNAVAILABLE:{type(error).__name__}",
                ),
            )
        return self.asset_coverage(answer, represented)

    def product_coverage(self, answer, product_id) -> OwnershipCoverage:
        try:
            represented = self.repository.product_assets(
                product_id,
                creator_profile_id=answer.identity.creator_profile_id,
            )
        except Exception as error:
            return self._coverage(
                answer, (), insufficiencies=(
                    f"PRODUCT_COMPOSITION_UNAVAILABLE:{type(error).__name__}",
                ),
            )
        return self.asset_coverage(answer, represented)

    def bundle_coverage(self, answer, represented_asset_ids) -> OwnershipCoverage:
        return self.asset_coverage(answer, represented_asset_ids)

    def owns_bundle(self, answer, represented_asset_ids) -> bool:
        return self.bundle_coverage(answer, represented_asset_ids).complete

    def remaining_assets(self, answer, represented_asset_ids) -> tuple[int, ...]:
        return self.asset_coverage(
            answer, represented_asset_ids
        ).remaining_asset_ids

    @staticmethod
    def lineage_context(answer, asset_id, lineage) -> OwnershipLineageContext:
        """Expose related Assets without changing the canonical ownership answer."""

        asset_id = int(asset_id)
        ancestors = tuple(item.asset_id for item in lineage.ancestors(asset_id))
        descendants = tuple(item.asset_id for item in lineage.descendants(asset_id))
        parents = tuple(item.asset_id for item in lineage.parents(asset_id))
        sibling_values = []
        for parent_id in parents:
            sibling_values.extend(
                item.asset_id for item in lineage.children(parent_id)
                if item.asset_id != asset_id
            )
        siblings = tuple(dict.fromkeys(sibling_values))
        family = tuple(lineage.family(asset_id))
        related = tuple(value for value in family if value != asset_id)
        owned = frozenset(answer.owned_asset_ids)
        return OwnershipLineageContext(
            asset_id=asset_id, ancestor_asset_ids=ancestors,
            descendant_asset_ids=descendants, sibling_asset_ids=siblings,
            family_asset_ids=family,
            owned_related_asset_ids=tuple(value for value in related if value in owned),
            unowned_related_asset_ids=tuple(value for value in related if value not in owned),
        )

    def session_coverage(self, answer, session_id) -> SessionOwnershipCoverage:
        try:
            session = self.repository.session_assets(
                session_id,
                creator_profile_id=answer.identity.creator_profile_id,
            )
        except Exception as error:
            coverage = self._coverage(
                answer, (), insufficiencies=(
                    f"SALES_SESSION_SOURCE_UNAVAILABLE:{type(error).__name__}",
                ),
            )
            return SessionOwnershipCoverage(
                sales_session_id=UUID(str(session_id)), foundation=None,
                coverage=coverage, session_purchased_asset_ids=(),
                overlapping_external_asset_ids=(),
                remaining_asset_ids=(), chronology=(),
            )
        if not session:
            coverage = self._coverage(
                answer, (), insufficiencies=("SALES_SESSION_NOT_FOUND",)
            )
            return SessionOwnershipCoverage(
                sales_session_id=UUID(str(session_id)), foundation=None,
                coverage=coverage, session_purchased_asset_ids=(),
                overlapping_external_asset_ids=(),
                remaining_asset_ids=coverage.remaining_asset_ids,
                chronology=(),
            )
        represented = tuple(session["represented_asset_ids"])
        result = self.asset_coverage(answer, represented)
        purchased = frozenset(session["purchased_asset_ids"])
        coverage = OwnershipCoverage(
            state=result.state,
            represented_asset_ids=result.represented_asset_ids,
            owned_asset_ids=result.owned_asset_ids,
            remaining_asset_ids=result.remaining_asset_ids,
            evidence=result.evidence,
            conflicts=result.conflicts,
            insufficiencies=tuple(dict.fromkeys((
                *result.insufficiencies,
                *(
                    ("SESSION_PURCHASE_COMPOSITION_MISMATCH",)
                    if purchased.difference(represented) else ()
                ),
            ))),
        )
        chronology = tuple(
            SessionPurchaseChronology(
                purchase_intent_id=UUID(str(row["purchase_intent_id"])),
                sequence=int(row["sequence_index"]),
                associated_at=row["associated_at"],
                asset_ids=tuple(int(value) for value in row["asset_ids"]),
            )
            for row in session.get("purchase_chronology") or ()
        )
        session_purchased = tuple(dict.fromkeys(
            int(value) for value in session["purchased_asset_ids"]
        ))
        overlapping_external = tuple(
            value for value in coverage.owned_asset_ids
            if value not in frozenset(session_purchased)
        )
        return SessionOwnershipCoverage(
            sales_session_id=UUID(str(session_id)),
            foundation=session.get("foundation"),
            coverage=coverage,
            session_purchased_asset_ids=session_purchased,
            overlapping_external_asset_ids=overlapping_external,
            remaining_asset_ids=coverage.remaining_asset_ids,
            chronology=chronology,
        )

    def asset_coverage(self, answer, represented_asset_ids) -> OwnershipCoverage:
        represented = tuple(dict.fromkeys(
            int(value) for value in represented_asset_ids
        ))
        if not represented:
            return self._coverage(
                answer, represented,
                insufficiencies=("REPRESENTED_ASSET_COMPOSITION_MISSING",),
            )
        return self._coverage(answer, represented)

    @staticmethod
    def ownership_evidence(answer):
        return answer.evidence

    @staticmethod
    def ownership_conflicts(answer):
        return answer.conflicts

    @staticmethod
    def ownership_insufficiency(answer):
        return answer.insufficiencies

    def workspace_view(self, answer) -> OwnershipWorkspaceView:
        if not answer.evidence_sufficient:
            return OwnershipWorkspaceView(
                answer=answer, bundle_coverage=MappingProxyType({}),
                session_coverage=MappingProxyType({}),
                remaining_asset_ids=(),
            )
        try:
            bundle_rows = self.repository.bundle_compositions(
                creator_profile_id=answer.identity.creator_profile_id
            )
            session_ids = self.repository.customer_session_ids(answer.identity)
        except Exception as error:
            answer = self._with_insufficiency(
                answer,
                f"WORKSPACE_OWNERSHIP_SOURCE_UNAVAILABLE:{type(error).__name__}",
            )
            return OwnershipWorkspaceView(
                answer=answer, bundle_coverage=MappingProxyType({}),
                session_coverage=MappingProxyType({}),
                remaining_asset_ids=(),
            )
        bundles = {
            str(row["offering_id"]): self.bundle_coverage(
                answer, row["asset_ids"]
            ) for row in bundle_rows
        }
        sessions = {
            str(session_id): self.session_coverage(answer, session_id)
            for session_id in session_ids
        }
        remaining = tuple(dict.fromkeys(
            asset_id
            for coverage in bundles.values()
            for asset_id in coverage.remaining_asset_ids
        ))
        return OwnershipWorkspaceView(
            answer=answer,
            bundle_coverage=MappingProxyType(bundles),
            session_coverage=MappingProxyType(sessions),
            remaining_asset_ids=remaining,
        )

    @staticmethod
    def _with_insufficiency(answer, reason):
        insufficiencies = tuple(dict.fromkeys((
            *answer.insufficiencies, reason,
        )))
        diagnostics = dict(answer.diagnostics)
        diagnostics.update({
            "answerState": OwnershipAnswerState.INSUFFICIENT.value,
            "insufficiencyCount": len(insufficiencies),
            "insufficiencies": insufficiencies,
        })
        return replace(
            answer, insufficiencies=insufficiencies,
            state=OwnershipAnswerState.INSUFFICIENT,
            diagnostics=MappingProxyType(diagnostics),
        )

    @staticmethod
    def _coverage(answer, represented, insufficiencies=()):
        represented = tuple(represented)
        represented_set = frozenset(represented)
        owned = represented_set.intersection(answer.owned_asset_ids)
        remaining = represented_set.difference(owned)
        combined_insufficiencies = tuple(dict.fromkeys((
            *answer.insufficiencies, *insufficiencies,
        )))
        if answer.conflicts:
            state = CoverageState.CONFLICTING
        elif combined_insufficiencies:
            state = CoverageState.INSUFFICIENT
        elif represented_set and not remaining:
            state = CoverageState.COMPLETE
        elif owned:
            state = CoverageState.PARTIAL
        else:
            state = CoverageState.NONE
        evidence = tuple(
            item for item in answer.evidence
            if represented_set.intersection(item.asset_ids)
        )
        return OwnershipCoverage(
            state=state,
            represented_asset_ids=represented,
            owned_asset_ids=tuple(
                value for value in represented if value in owned
            ),
            remaining_asset_ids=tuple(
                value for value in represented if value in remaining
            ),
            evidence=evidence, conflicts=answer.conflicts,
            insufficiencies=combined_insufficiencies,
        )

    @staticmethod
    def _conflicts(evidence):
        conflicts = []
        by_product = {}
        for item in evidence:
            if item.product_id is not None:
                by_product.setdefault(item.product_id, []).append(item)
        for product_id, items in by_product.items():
            if any(item.proves_ownership for item in items) and any(
                item.lifecycle.value in {"REVOKED", "REFUNDED"}
                for item in items
            ):
                conflicts.append(
                    f"PRODUCT_LIFECYCLE_CONFLICT:{product_id}"
                )
        return tuple(conflicts)

    @staticmethod
    def _identity_insufficiencies(identity):
        values = []
        if int(identity.creator_profile_id or 0) <= 0:
            values.append("CREATOR_SCOPE_UNRESOLVED")
        if int(identity.fanvue_account_id or 0) <= 0:
            values.append("ACCOUNT_SCOPE_UNRESOLVED")
        if not any((
            identity.external_fanvue_user_uuid,
            identity.telegram_user_id,
            identity.legacy_fanvue_user_id,
            identity.core_user_id,
        )):
            values.extend((
                "CUSTOMER_IDENTITY_UNRESOLVED",
                "SUPPORTED_IDENTITY_PATH_MISSING",
            ))
        return tuple(values)

    @staticmethod
    def _identity_path(identity):
        return "+".join(
            name for name, value in (
                ("external_fanvue_user_uuid", identity.external_fanvue_user_uuid),
                ("telegram_user_id", identity.telegram_user_id),
                ("legacy_fanvue_identity", identity.legacy_fanvue_user_id),
                ("core_user_id", identity.core_user_id),
            ) if value is not None
        ) or "unresolved"
