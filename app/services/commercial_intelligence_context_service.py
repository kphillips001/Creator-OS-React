"""Read-only assembly of facts consumed by Commercial Intelligence."""

from __future__ import annotations

from app.models.commercial_intelligence import (
    BundleCompositionEvidence,
    CommercialIntelligenceContext,
    OwnershipCoverage,
    immutable_mapping,
)
from app.models.ownership_intelligence import OwnershipIdentity
from app.services.ownership_intelligence_service import (
    OwnershipIntelligenceService,
)
from app.services.asset_lineage_service import AssetLineageService


class CommercialIntelligenceContextService:
    def __init__(self, ownership_repository=None, lineage_service=None) -> None:
        self.ownership = ownership_repository
        self.lineage = lineage_service or AssetLineageService()
        self.ownership_intelligence = OwnershipIntelligenceService(
            lineage_service=self.lineage
        )

    def assemble(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid, telegram_user_id: int | None,
        core_user_id=None,
        legacy_fanvue_user_id=None, active_sales_session=None,
        relevant_historical_session=None,
        session_purchase_intents=(), available_offering_types=(),
        intended_photoshoot_reference=None, bundle_compositions=(),
        approved_commercial_roles=(), conversation_context=None,
        lineage_asset_ids=(), lineage_evidence=None,
    ) -> CommercialIntelligenceContext:
        conversation = dict(conversation_context or {})
        memory = conversation.get("_customer_commerce_memory")
        answer = getattr(memory, "ownership", None)
        try:
            if answer is not None:
                coverage = {
                    "owned_offering_ids": answer.owned_offering_ids,
                    "owned_asset_ids": answer.owned_asset_ids,
                    "purchase_asset_ids": tuple(sorted({
                        asset_id for item in answer.evidence
                        if item.offering_id is not None and item.proves_ownership
                        for asset_id in item.asset_ids
                    })),
                    "evidence_sources": tuple(dict.fromkeys(
                        item.source.value for item in answer.evidence if item.proves_ownership
                    )),
                    "incomplete": bool(answer.insufficiencies),
                    "conflicts": answer.conflicts,
                }
            elif self.ownership is not None:
                coverage = self.ownership.get(
                    creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,
                    external_fanvue_user_uuid=external_fanvue_user_uuid,
                    telegram_user_id=telegram_user_id,
                    legacy_fanvue_user_id=legacy_fanvue_user_id,
                    core_user_id=core_user_id,
                )
            else:
                answer = self.ownership_intelligence.answer(
                    OwnershipIdentity(
                        creator_profile_id=int(creator_profile_id),
                        fanvue_account_id=int(fanvue_account_id),
                        external_fanvue_user_uuid=external_fanvue_user_uuid,
                        telegram_user_id=telegram_user_id,
                        legacy_fanvue_user_id=(
                            str(legacy_fanvue_user_id)
                            if legacy_fanvue_user_id is not None else None
                        ),
                        core_user_id=core_user_id,
                    )
                )
                coverage = {
                    "owned_offering_ids": answer.owned_offering_ids,
                    "owned_asset_ids": answer.owned_asset_ids,
                    "purchase_asset_ids": tuple(sorted({
                        asset_id for item in answer.evidence
                        if item.offering_id is not None
                        and item.proves_ownership
                        for asset_id in item.asset_ids
                    })),
                    "evidence_sources": tuple(dict.fromkeys(
                        item.source.value for item in answer.evidence
                        if item.proves_ownership
                    )),
                    "incomplete": bool(answer.insufficiencies),
                    "conflicts": answer.conflicts,
                }
        except Exception as error:
            coverage = {
                "owned_offering_ids": (), "owned_asset_ids": (),
                "purchase_asset_ids": (), "evidence_sources": (),
                "incomplete": True,
                "conflicts": (f"OWNERSHIP_EVIDENCE_UNAVAILABLE:{type(error).__name__}",),
            }
        purchased = tuple(
            row for row in session_purchase_intents
            if str(getattr(row.get("status"), "value", row.get("status") or ""))
            == "PURCHASED"
            and str(getattr(
                row.get("attribution_result"), "value",
                row.get("attribution_result") or "",
            )) == "ATTRIBUTED"
        )
        session_owned = set()
        for row in purchased:
            session_owned.update(int(value) for value in row.get("asset_ids") or ())
        session_id = getattr(active_sales_session, "sales_session_id", None)
        compositions = tuple(
            value if isinstance(value, BundleCompositionEvidence)
            else BundleCompositionEvidence(
                photoshoot_reference=str(value["photoshoot_reference"]),
                asset_ids=tuple(sorted({
                    int(item) for item in value.get("asset_ids") or ()
                })),
                complete_set=bool(value.get("complete_set", True)),
                provenance=tuple(value.get("provenance") or ()),
            )
            for value in bundle_compositions
        )
        relevant_compositions = tuple(
            item for item in compositions
            if (
                intended_photoshoot_reference is None
                or item.photoshoot_reference
                == str(intended_photoshoot_reference)
            )
        )
        canonical_bundle_coverage = (
            self.ownership_intelligence.bundle_coverage(
                answer, relevant_compositions[0].asset_ids
            )
            if answer is not None
            and len(relevant_compositions) == 1
            and relevant_compositions[0].complete_set
            else None
        )
        evidence_session_id = getattr(
            active_sales_session or relevant_historical_session,
            "sales_session_id", None,
        )
        canonical_session_coverage = (
            self.ownership_intelligence.session_coverage(
                answer, evidence_session_id
            )
            if answer is not None and evidence_session_id is not None else None
        )
        canonical_lineage_evidence = self._lineage_evidence(lineage_asset_ids)
        return CommercialIntelligenceContext(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=int(fanvue_account_id),
            telegram_user_id=telegram_user_id,
            active_sales_session_id=session_id,
            sales_session_state=(
                active_sales_session.state.value if active_sales_session else None
            ),
            sales_session_progression=(
                active_sales_session.progression_stage.value
                if active_sales_session else None
            ),
            sales_session_foundation_type=(
                getattr(
                    getattr(
                        active_sales_session or relevant_historical_session,
                        "commercial_foundation_type", None,
                    ),
                    "value",
                    getattr(
                        active_sales_session or relevant_historical_session,
                        "commercial_foundation_type", None,
                    ),
                )
            ),
            sales_session_foundation=getattr(
                active_sales_session or relevant_historical_session,
                "commercial_foundation_reference", None,
            ),
            session_participated=bool(
                active_sales_session or relevant_historical_session
                or conversation.get("session_participated")
            ),
            session_purchase_count=len(purchased),
            approved_commercial_roles=tuple(dict.fromkeys(
                str(value) for value in approved_commercial_roles
            )),
            latest_message=conversation.get("latest_message"),
            requested_media_type=conversation.get("requested_media_type"),
            requested_themes=tuple(conversation.get("requested_themes") or ()),
            recent_conversation_requests=tuple(
                conversation.get("recent_conversation_requests") or ()
            )[-3:],
            available_offering_types=tuple(dict.fromkeys(
                str(value) for value in available_offering_types
            )),
            intended_photoshoot_reference=(
                str(intended_photoshoot_reference)
                if intended_photoshoot_reference else None
            ),
            bundle_compositions=compositions,
            canonical_bundle_coverage=canonical_bundle_coverage,
            canonical_session_coverage=canonical_session_coverage,
            canonical_ownership_answer=answer,
            customer_commerce_memory=memory,
            ownership=OwnershipCoverage(
                owned_offering_ids=tuple(coverage.get("owned_offering_ids") or ()),
                owned_asset_ids=tuple(coverage.get("owned_asset_ids") or ()),
                session_owned_asset_ids=tuple(sorted(session_owned)),
                evidence_sources=tuple(coverage.get("evidence_sources") or ()),
                incomplete=bool(coverage.get("incomplete")),
                conflicts=tuple(coverage.get("conflicts") or ()),
            ),
            lineage_evidence=immutable_mapping({
                **dict(lineage_evidence or {}),
                **canonical_lineage_evidence,
            }),
            durable_evidence=immutable_mapping({
                "activeSalesSession": bool(active_sales_session),
                "sessionAttributedPurchaseCount": len(purchased),
                "ownershipEvidenceAvailable": not bool(coverage.get("incomplete")),
                "customerCommerceMemory": conversation.get(
                    "customer_commerce_memory_summary", {}
                ),
            }),
            conversation_evidence=immutable_mapping({
                "latestMessage": conversation.get("latest_message"),
                "requestedMediaType": conversation.get("requested_media_type"),
                "requestedThemes": tuple(
                    conversation.get("requested_themes") or ()
                ),
            }),
            provenance=immutable_mapping({
                "salesSession": ("SalesSessionRepository",),
                "purchaseHistory": (
                    ("CustomerCommerceMemoryService",)
                    if memory is not None else ("PurchaseIntentRepository",)
                ),
                "ownership": tuple(coverage.get("evidence_sources") or ()),
                "customerRequest": ("ConversationGateway",),
                "commercialInventory": ("CommercialOfferingSelectorRepository",),
                "assetLineage": (
                    ("AssetLineage",)
                    if canonical_lineage_evidence or lineage_evidence else ()
                ),
            }),
        )

    def _lineage_evidence(self, asset_ids) -> dict:
        evidence = {}
        for asset_id in tuple(dict.fromkeys(int(value) for value in asset_ids)):
            try:
                diagnostics = self.lineage.diagnostics(asset_id)
            except (KeyError, ValueError):
                continue
            evidence[str(asset_id)] = {
                "assetId": diagnostics.asset_id,
                "classification": diagnostics.classification,
                "rootAssetIds": tuple(item.asset_id for item in diagnostics.roots),
                "parentAssetIds": tuple(item.asset_id for item in diagnostics.parents),
                "siblingAssetIds": tuple(item.asset_id for item in diagnostics.siblings),
                "ancestorAssetIds": tuple(item.asset_id for item in diagnostics.ancestors),
                "descendantAssetIds": tuple(item.asset_id for item in diagnostics.descendants),
                "familyAssetIds": diagnostics.family_asset_ids,
                "lineageDepth": diagnostics.lineage_depth,
                "sourceMediaTypes": dict(diagnostics.source_media_types),
                "derivedMediaType": diagnostics.derived_media_type,
                "ambiguous": diagnostics.ambiguous,
                "complete": diagnostics.complete,
                "integrityStatus": diagnostics.integrity_status,
                "provenanceComplete": diagnostics.provenance_complete,
            }
        return evidence
