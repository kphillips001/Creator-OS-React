from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.asset_lineage import AssetLineageRelationship, DerivationKind
from app.models.commercial_intelligence import CommercialIntelligenceContext
from app.models.commercial_role import (
    CommercialRole,
    CommercialRoleActorType,
    CommercialRoleAssignment,
    CommercialRoleOrigin,
    CommercialRoleState,
)
from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer,
    OwnershipAnswerState,
    OwnershipIdentity,
)
from app.services.asset_lineage_service import AssetLineageError, AssetLineageService
from app.services.commercial_intelligence_service import CommercialIntelligenceService
from app.services.commercial_intelligence_context_service import (
    CommercialIntelligenceContextService,
)
from app.services.commercial_role_service import (
    CommercialRoleService,
    CommercialRoleSuggestionService,
)
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


class MemoryLineageRepository:
    def __init__(self, memberships=None):
        self.relationships = []
        self.memberships = dict(memberships or {})

    def create(self, relationship):
        self.relationships.append(relationship)
        return relationship

    def get(self, relationship_id):
        return next((item for item in self.relationships if item.relationship_id == relationship_id), None)

    def relationships_for_asset(self, asset_id):
        return tuple(item for item in self.relationships if asset_id == item.derived_asset_id or asset_id in item.source_asset_ids)

    def parents(self, asset_id):
        return tuple(dict.fromkeys(
            source for item in self.relationships if item.derived_asset_id == asset_id
            for source in item.source_asset_ids
        ))

    def children(self, asset_id):
        return tuple(dict.fromkeys(
            item.derived_asset_id for item in self.relationships if asset_id in item.source_asset_ids
        ))

    def ancestors(self, asset_id):
        return self._walk(asset_id, self.parents)

    def descendants(self, asset_id):
        return self._walk(asset_id, self.children)

    @staticmethod
    def _walk(asset_id, next_values):
        pending = [(value, 1) for value in next_values(asset_id)]
        depths = {}
        while pending:
            value, depth = pending.pop(0)
            if value in depths and depths[value] <= depth:
                continue
            depths[value] = depth
            pending.extend((child, depth + 1) for child in next_values(value))
        return tuple(sorted(depths.items(), key=lambda item: (item[1], item[0])))

    def photoshoot_memberships(self, asset_ids):
        values = []
        for asset_id in asset_ids:
            for session_id in self.memberships.get(asset_id, ()):
                values.append({"photoshoot_session_id": session_id, "asset_id": asset_id})
        return tuple(values)


class FakeAssets:
    def __init__(self, *asset_ids):
        self.values = {
            value: SimpleNamespace(id=value, creator_profile_id=7, media_type=(
                "video" if value >= 20 else "image"
            )) for value in asset_ids
        }

    def get_by_id(self, asset_id):
        return self.values.get(asset_id)


class AssetLineageTests(unittest.TestCase):
    def make_service(self, memberships=None):
        repository = MemoryLineageRepository(memberships)
        service = AssetLineageService(
            repository=repository,
            asset_repository=FakeAssets(*range(1, 50)),
        )
        return service, repository

    def relate(self, service, sources, derived, kind=DerivationKind.IMAGE_TO_VIDEO):
        return service.relate(
            source_asset_ids=sources, derived_asset_id=derived,
            derivation_kind=kind, provenance={"provider": "test"},
            creator_profile_id=7,
        )

    def test_one_source_can_produce_many_derivatives(self):
        service, _ = self.make_service()
        self.relate(service, (1,), 20)
        self.relate(service, (1,), 21)
        self.assertEqual([item.asset_id for item in service.children(1)], [20, 21])

    def test_many_sources_create_one_immutable_relationship(self):
        service, _ = self.make_service()
        relationship = self.relate(
            service, (1, 2, 1), 20, DerivationKind.MULTI_IMAGE_TO_VIDEO
        )
        self.assertEqual(relationship.source_asset_ids, (1, 2))
        self.assertTrue(relationship.multi_source)
        with self.assertRaises(TypeError):
            relationship.provenance["provider"] = "changed"
        with self.assertRaises(AssetLineageError):
            self.relate(service, (3,), 20)

    def test_arbitrary_depth_root_and_descendant_traversal(self):
        service, _ = self.make_service()
        self.relate(service, (1,), 20)
        self.relate(service, (20,), 21, DerivationKind.VIDEO_TO_CLIP)
        self.relate(service, (21,), 22, DerivationKind.VIDEO_TO_GIF)
        self.assertEqual([(item.asset_id, item.depth) for item in service.ancestors(22)], [(21, 1), (20, 2), (1, 3)])
        self.assertEqual([(item.asset_id, item.depth) for item in service.descendants(1)], [(20, 1), (21, 2), (22, 3)])
        self.assertEqual([(item.asset_id, item.depth) for item in service.roots(22)], [(1, 3)])

    def test_self_reference_and_cycles_are_rejected(self):
        service, _ = self.make_service()
        with self.assertRaises(AssetLineageError):
            self.relate(service, (1,), 1)
        self.relate(service, (1,), 20)
        self.relate(service, (20,), 21, DerivationKind.VIDEO_TO_CLIP)
        with self.assertRaises(AssetLineageError):
            self.relate(service, (21,), 1, DerivationKind.VIDEO_TO_GIF)

    def test_canonical_assets_and_creator_scope_are_required(self):
        service, _ = self.make_service()
        with self.assertRaises(KeyError):
            self.relate(service, (99,), 20)
        service.assets.values[2] = SimpleNamespace(id=2, creator_profile_id=8)
        with self.assertRaises(AssetLineageError):
            self.relate(service, (1, 2), 20)

    def test_photoshoot_context_is_inherited_without_membership_mutation(self):
        service, repository = self.make_service({1: ("shoot-a",)})
        self.relate(service, (1,), 20)
        context = service.photoshoot_context(20)
        self.assertEqual(context[0].photoshoot_session_id, "shoot-a")
        self.assertEqual(context[0].source_asset_ids, (1,))
        self.assertFalse(context[0].direct_membership)
        self.assertNotIn(20, repository.memberships)

    def test_multi_source_preserves_multi_photoshoot_context(self):
        service, _ = self.make_service({1: ("shoot-a",), 2: ("shoot-b",)})
        self.relate(service, (1, 2), 20, DerivationKind.MULTI_IMAGE_TO_VIDEO)
        contexts = service.photoshoot_context(20)
        self.assertEqual({item.photoshoot_session_id for item in contexts}, {"shoot-a", "shoot-b"})

    def test_diagnostics_separate_relationship_and_photoshoot_facts(self):
        service, _ = self.make_service({1: ("shoot-a",)})
        relationship = self.relate(service, (1,), 20)
        diagnostics = service.diagnostics(20)
        self.assertEqual(diagnostics.root.asset_id, 1)
        self.assertEqual(diagnostics.classification, "DERIVED")
        self.assertEqual(diagnostics.derived_media_type, "video")
        self.assertEqual(dict(diagnostics.source_media_types), {1: "image"})
        self.assertEqual(diagnostics.family_asset_ids, (1, 20))
        self.assertEqual(diagnostics.siblings, ())
        self.assertEqual(diagnostics.relationships, (relationship,))
        self.assertEqual(diagnostics.lineage_depth, 1)
        self.assertTrue(diagnostics.complete)
        self.assertEqual(diagnostics.integrity_status, "VALID")
        self.assertTrue(diagnostics.provenance_complete)

    def test_diagnostics_expose_siblings_family_and_ambiguity(self):
        service, _ = self.make_service({1: ("shoot-a",), 2: ("shoot-b",)})
        self.relate(service, (1,), 20)
        self.relate(service, (1,), 21)
        self.relate(service, (1, 2), 22, DerivationKind.MULTI_IMAGE_TO_VIDEO)
        sibling_diagnostics = service.diagnostics(20)
        self.assertEqual([item.asset_id for item in sibling_diagnostics.siblings], [21, 22])
        self.assertEqual(set(sibling_diagnostics.family_asset_ids), {1, 2, 20, 21, 22})
        ambiguous = service.diagnostics(22)
        self.assertTrue(ambiguous.ambiguous)
        self.assertEqual({item.asset_id for item in ambiguous.roots}, {1, 2})

    def test_isolated_asset_is_classified_as_root(self):
        service, _ = self.make_service()
        diagnostics = service.diagnostics(3)
        self.assertEqual(diagnostics.classification, "ROOT")
        self.assertEqual(diagnostics.family_asset_ids, (3,))
        self.assertEqual(diagnostics.integrity_status, "VALID")


class LineageCommercialIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.lineage, _ = AssetLineageTests().make_service()
        AssetLineageTests().relate(self.lineage, (1,), 20)

    def test_ownership_context_does_not_infer_ownership(self):
        answer = CanonicalOwnershipAnswer(
            identity=OwnershipIdentity(7, 4), evidence=(),
            owned_offering_ids=(), owned_product_ids=(), owned_asset_ids=(1,),
            state=OwnershipAnswerState.CONFIRMED_OWNERSHIP,
        )
        context = OwnershipIntelligenceService.lineage_context(answer, 20, self.lineage)
        self.assertEqual(context.ancestor_asset_ids, (1,))
        self.assertEqual(context.owned_related_asset_ids, (1,))
        self.assertNotIn(20, answer.owned_asset_ids)

    def test_ownership_answer_automatically_assembles_lineage_context(self):
        class EvidenceRepository:
            @staticmethod
            def evidence_for(identity):
                from app.models.ownership_intelligence import (
                    OwnershipEvidence, OwnershipLifecycle, OwnershipSource,
                )
                return (OwnershipEvidence(
                    source=OwnershipSource.LEGACY_OWNERSHIP,
                    lifecycle=OwnershipLifecycle.ACTIVE,
                    identity_path="legacy", supporting_record_id="owned-20",
                    asset_ids=(20,), proves_ownership=True,
                ),)

        answer = OwnershipIntelligenceService(
            EvidenceRepository(), lineage_service=self.lineage
        ).answer(OwnershipIdentity(
            creator_profile_id=7, fanvue_account_id=4,
            legacy_fanvue_user_id="customer-1",
        ))
        self.assertIn(20, answer.lineage_contexts)
        self.assertEqual(answer.lineage_contexts[20].ancestor_asset_ids, (1,))
        self.assertEqual(answer.owned_asset_ids, (20,))

    def test_lineage_family_includes_sibling_branches(self):
        AssetLineageTests().relate(self.lineage, (1,), 21)
        AssetLineageTests().relate(
            self.lineage, (21,), 22, DerivationKind.VIDEO_TO_CLIP
        )
        context = OwnershipIntelligenceService.lineage_context(
            CanonicalOwnershipAnswer(
                identity=OwnershipIdentity(7, 4), evidence=(),
                owned_offering_ids=(), owned_product_ids=(), owned_asset_ids=(),
            ),
            20, self.lineage,
        )
        self.assertEqual(context.sibling_asset_ids, (21,))
        self.assertEqual(set(context.family_asset_ids), {1, 20, 21, 22})

    def test_commercial_intelligence_exposes_lineage_without_strategy_authority(self):
        base = CommercialIntelligenceContext(
            creator_profile_id=7, fanvue_account_id=4, telegram_user_id=None,
            latest_message="show me a video", requested_media_type="VIDEO",
        )
        with_lineage = CommercialIntelligenceContext(
            creator_profile_id=7, fanvue_account_id=4, telegram_user_id=None,
            latest_message="show me a video", requested_media_type="VIDEO",
            lineage_evidence={"assetId": 20, "ancestorAssetIds": (1,), "lineageDepth": 1},
        )
        plain = CommercialIntelligenceService().recommend(base)
        related = CommercialIntelligenceService().recommend(with_lineage)
        self.assertEqual(plain.strategy, related.strategy)
        self.assertEqual(plain.reason, related.reason)
        self.assertEqual(related.diagnostic_context["assetLineageEvidence"]["assetId"], 20)

    def test_commercial_context_automatically_assembles_canonical_lineage(self):
        context_service = CommercialIntelligenceContextService(
            ownership_repository=SimpleNamespace(get=lambda **values: {
                "owned_offering_ids": (), "owned_asset_ids": (),
                "evidence_sources": (), "incomplete": False, "conflicts": (),
            }),
            lineage_service=self.lineage,
        )
        context = context_service.assemble(
            creator_profile_id=7, fanvue_account_id=4,
            external_fanvue_user_uuid=None, telegram_user_id=5,
            conversation_context={
                "latest_message": "show me a video",
                "requested_media_type": "VIDEO",
            },
            lineage_asset_ids=(20,),
        )
        evidence = context.lineage_evidence["20"]
        self.assertEqual(evidence["ancestorAssetIds"], (1,))
        self.assertEqual(evidence["derivedMediaType"], "video")
        decision = CommercialIntelligenceService().recommend(context)
        self.assertEqual(decision.strategy.value, "LIBRARY_SELLING")
        self.assertIn("20", decision.diagnostic_context["assetLineageEvidence"])

    def test_role_lineage_creates_suggestion_not_inheritance(self):
        now = datetime.now(timezone.utc)
        parent = CommercialRoleAssignment(
            assignment_id=uuid4(), asset_id=1, creator_profile_id=7,
            role=CommercialRole.PREMIUM, state=CommercialRoleState.APPROVED,
            origin=CommercialRoleOrigin.CREATOR_ASSIGNED, rationale=None,
            suggestion_confidence=None, created_at=now, updated_at=now,
        )

        class Roles:
            def __init__(self): self.created = []
            def get(self, **values): return None
            def list_for_asset(self, *, asset_id, states=None, **values):
                return (parent,) if asset_id == 1 else ()
            def create(self, **values):
                self.created.append(values)
                return SimpleNamespace(**values)

        roles = Roles()
        role_service = CommercialRoleService(repository=roles, asset_repository=FakeAssets(1, 20))
        intelligence = SimpleNamespace(get_profile=lambda asset_id: SimpleNamespace(
            creator_profile_id=7, overall_confidence=0.5,
            suggested_use_cases=(), preview_suitability=None,
            quality_score=0.0, content_uniqueness=0.0,
        ))
        photoshoots = SimpleNamespace(commercial_role_context_for_asset=lambda *args: None)
        suggestions = CommercialRoleSuggestionService(
            role_service=role_service, intelligence_repository=intelligence,
            photoshoot_repository=photoshoots, lineage_service=self.lineage,
        ).suggest(asset_id=20, creator_profile_id=7)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(roles.created[0]["state"], CommercialRoleState.SUGGESTED)
        self.assertEqual(roles.created[0]["role"], CommercialRole.PREMIUM)
        self.assertFalse(roles.created[0]["evidence"]["inherited"])

    def test_production_role_composition_uses_canonical_lineage(self):
        from app.api.commercial_roles import _suggestions

        service = _suggestions()
        self.assertIsInstance(service.lineage, AssetLineageService)

    def test_offerings_products_and_publication_remain_canonical_asset_based(self):
        offering = Path("app/models/commercial_offering.py").read_text(encoding="utf-8")
        product_asset = Path("app/models/product_asset.py").read_text(encoding="utf-8")
        publication = Path("app/models/commercial_publication.py").read_text(encoding="utf-8")
        executor = Path("app/services/fanvue_media_link_publication_executor.py").read_text(encoding="utf-8")
        self.assertIn("asset_id: int", offering)
        self.assertIn("asset_id: int", product_asset)
        self.assertIn("commercial_offering_id", publication)
        self.assertIn('{"image", "video"}', executor)
        self.assertNotIn("AssetLineage", publication)


class AssetLineageMigrationTests(unittest.TestCase):
    def test_additive_forward_and_rollback_migrations(self):
        forward = Path("migrations/forward/20260731_028_asset_lineage.sql")
        rollback = Path("migrations/rollback/20260731_028_asset_lineage.sql")
        sql = forward.read_text(encoding="utf-8")
        self.assertTrue(forward.exists() and rollback.exists())
        self.assertIn("CREATE TABLE IF NOT EXISTS public.asset_lineage_relationships", sql)
        self.assertIn("REFERENCES public.content_items(id) ON DELETE RESTRICT", sql)
        self.assertIn("CHECK (source_asset_id <> derived_asset_id)", sql)
        self.assertNotIn("ALTER TABLE public.content_items", sql)
        self.assertIn("DROP TABLE IF EXISTS public.asset_lineage_relationships", rollback.read_text(encoding="utf-8"))

    def test_database_hardening_rejects_multiple_relationship_sets(self):
        forward = Path(
            "migrations/forward/20260731_029_asset_lineage_derived_set_integrity.sql"
        ).read_text(encoding="utf-8")
        rollback = Path(
            "migrations/rollback/20260731_029_asset_lineage_derived_set_integrity.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("trg_asset_lineage_single_derivation_set", forward)
        self.assertIn("existing.relationship_id <> NEW.relationship_id", forward)
        self.assertIn("DROP TRIGGER IF EXISTS", rollback)


if __name__ == "__main__":
    unittest.main()
