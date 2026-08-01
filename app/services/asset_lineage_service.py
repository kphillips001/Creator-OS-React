"""Canonical relationship boundary for independently identified Assets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from uuid import uuid4

from app.models.asset_lineage import (
    Ancestor,
    AssetLineageDiagnostics,
    AssetLineageRelationship,
    ChildAsset,
    DerivationKind,
    Descendant,
    ParentAsset,
    PhotoshootLineageContext,
    RootAsset,
)
from app.repositories.asset_lineage_repository import AssetLineageRepository
from app.repositories.asset_repository import AssetRepository


class AssetLineageError(ValueError):
    pass


class AssetLineageService:
    def __init__(self, *, repository=None, asset_repository=None) -> None:
        self.repository = repository or AssetLineageRepository()
        self.assets = asset_repository or AssetRepository()

    def relate(
        self, *, source_asset_ids: Iterable[int], derived_asset_id: int,
        derivation_kind, provenance: Mapping | None = None,
        creator_profile_id: int,
    ) -> AssetLineageRelationship:
        sources = tuple(dict.fromkeys(int(value) for value in source_asset_ids))
        derived = int(derived_asset_id)
        if not sources:
            raise AssetLineageError("At least one source Asset is required.")
        if derived in sources:
            raise AssetLineageError("An Asset cannot derive from itself.")
        if self.repository.parents(derived):
            raise AssetLineageError(
                "A Derived Asset can have only one canonical derivation relationship."
            )
        for asset_id in (*sources, derived):
            self._canonical_asset(asset_id, creator_profile_id)
        descendants = {
            value for source in sources
            for value, _depth in self.repository.descendants(derived)
        }
        if any(source in descendants for source in sources):
            raise AssetLineageError("Asset Lineage relationships cannot create cycles.")
        try:
            kind = (
                derivation_kind if isinstance(derivation_kind, DerivationKind)
                else DerivationKind(str(derivation_kind).strip().upper())
            )
        except ValueError as error:
            raise AssetLineageError(
                f"Unsupported derivation kind: {derivation_kind}"
            ) from error
        relationship = AssetLineageRelationship(
            relationship_id=uuid4(), source_asset_ids=sources,
            derived_asset_id=derived, derivation_kind=kind,
            provenance=provenance or {},
        )
        return self.repository.create(relationship)

    def parents(self, asset_id: int) -> tuple[ParentAsset, ...]:
        return tuple(ParentAsset(value, 1) for value in self.repository.parents(asset_id))

    def children(self, asset_id: int) -> tuple[ChildAsset, ...]:
        return tuple(ChildAsset(value, 1) for value in self.repository.children(asset_id))

    def ancestors(self, asset_id: int) -> tuple[Ancestor, ...]:
        return tuple(Ancestor(value, depth) for value, depth in self.repository.ancestors(asset_id))

    def descendants(self, asset_id: int) -> tuple[Descendant, ...]:
        return tuple(Descendant(value, depth) for value, depth in self.repository.descendants(asset_id))

    def roots(self, asset_id: int) -> tuple[RootAsset, ...]:
        ancestors = self.ancestors(asset_id)
        if not ancestors:
            return (RootAsset(int(asset_id), 0),)
        roots = tuple(
            RootAsset(item.asset_id, item.depth)
            for item in ancestors
            if not self.repository.parents(item.asset_id)
        )
        return roots

    def photoshoot_context(self, asset_id: int) -> tuple[PhotoshootLineageContext, ...]:
        ancestors = self.ancestors(asset_id)
        depths = {int(asset_id): 0, **{item.asset_id: item.depth for item in ancestors}}
        rows = self.repository.photoshoot_memberships(depths)
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(row["photoshoot_session_id"])].append(int(row["asset_id"]))
        return tuple(
            PhotoshootLineageContext(
                photoshoot_session_id=session_id,
                source_asset_ids=tuple(dict.fromkeys(source_ids)),
                minimum_depth=min(depths[value] for value in source_ids),
                direct_membership=int(asset_id) in source_ids,
            )
            for session_id, source_ids in sorted(grouped.items())
        )

    def diagnostics(self, asset_id: int) -> AssetLineageDiagnostics:
        asset_id = int(asset_id)
        asset = self.assets.get_by_id(asset_id)
        if asset is None:
            raise KeyError(f"Canonical Asset not found: {asset_id}")
        parents = self.parents(asset_id)
        children = self.children(asset_id)
        sibling_ids = tuple(dict.fromkeys(
            sibling.asset_id
            for parent in parents
            for sibling in self.children(parent.asset_id)
            if sibling.asset_id != asset_id
        ))
        siblings = tuple(ChildAsset(value, 1) for value in sibling_ids)
        ancestors = self.ancestors(asset_id)
        descendants = self.descendants(asset_id)
        relationships = self.repository.relationships_for_asset(asset_id)
        roots = self.roots(asset_id)
        photoshoot_contexts = self.photoshoot_context(asset_id)
        source_ids = tuple(dict.fromkeys(
            source_id
            for relationship in relationships
            if relationship.derived_asset_id == asset_id
            for source_id in relationship.source_asset_ids
        ))
        source_media_types = {}
        for source_id in source_ids:
            source = self.assets.get_by_id(source_id)
            source_media_types[source_id] = str(
                getattr(source, "media_type", "unknown") if source else "unknown"
            )
        issues = []
        if parents and not relationships:
            issues.append("PARENT_RELATIONSHIP_DETAILS_UNAVAILABLE")
        if any(
            relationship.derived_asset_id in relationship.source_asset_ids
            for relationship in relationships
        ):
            issues.append("SELF_REFERENCE_DETECTED")
        if parents and not roots:
            issues.append("ROOT_UNRESOLVED")
        provenance_complete = all(
            bool(relationship.provenance) for relationship in relationships
        ) if relationships else True
        ambiguous = len(roots) > 1 or len(photoshoot_contexts) > 1
        return AssetLineageDiagnostics(
            asset_id=asset_id,
            classification="DERIVED" if parents else "ROOT",
            roots=roots, parents=parents, children=children, siblings=siblings,
            ancestors=ancestors, descendants=descendants,
            family_asset_ids=self.family(asset_id), relationships=relationships,
            photoshoot_contexts=photoshoot_contexts,
            source_media_types=source_media_types,
            derived_media_type=str(getattr(asset, "media_type", "unknown")),
            lineage_depth=max((item.depth for item in ancestors), default=0),
            ambiguous=ambiguous, complete=not issues,
            integrity_status="VALID" if not issues else "INVALID",
            provenance_complete=provenance_complete,
            completeness_issues=tuple(issues),
        )

    def family(self, asset_id: int) -> tuple[int, ...]:
        pending = [int(asset_id)]
        seen = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self.repository.parents(current))
            pending.extend(self.repository.children(current))
        return tuple(sorted(seen))

    def _canonical_asset(self, asset_id: int, creator_profile_id: int):
        asset = self.assets.get_by_id(int(asset_id))
        if asset is None:
            raise KeyError(f"Canonical Asset not found: {asset_id}")
        if int(getattr(asset, "creator_profile_id", 0) or 0) != int(creator_profile_id):
            raise AssetLineageError("All lineage Assets must share creator ownership.")
        return asset
