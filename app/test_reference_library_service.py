import sys
import types
import unittest
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit
    sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
    sys.modules["streamlit.components.v1"] = types.ModuleType("streamlit.components.v1")

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.models.asset import Asset
from app.models.asset_library import (
    AssetLibraryFilter,
    AssetLibraryItem,
    AssetLibraryResult,
    AssetPublishingSummary,
    AssetRelationshipSummary,
)
from app.models.reference_library import ReferenceLibraryFilter
from app.services.ai_import_workflow_service import AIImportAssetResult
from app.services.asset_library_service import AssetLibraryService
from app.services.reference_library_service import ReferenceLibraryService


def asset_row(asset_id, *, creator_profile_id=1, file_name=None, metadata=None):
    return {
        "id": asset_id,
        "file_path": f"data/uploads/{file_name or f'asset_{asset_id}.png'}",
        "file_name": file_name or f"asset_{asset_id}.png",
        "classification": "TEASE",
        "confidence": 1.0,
        "status": "approved",
        "is_active": True,
        "is_test": False,
        "ready_for_rotation": True,
        "upload_intent": "teaser_image",
        "content_tier": "VIP",
        "distribution_type": "both",
        "blurred_preview_path": None,
        "suggested_tags": ["reference"],
        "detected_themes": ["studio"],
        "is_explicit": False,
        "fanvue_media_preview_uuid": None,
        "fanvue_media_full_uuid": None,
        "fanvue_upload_status": "not_requested",
        "fanvue_upload_error": None,
        "created_at": datetime.now(timezone.utc),
        "short_safe_summary": "Reference image",
        "risk_flags": [],
        "analysis_reasoning": "",
        "analysis_provenance": {},
        "media_metadata": metadata
        or {
            "local_vault_path": f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
        },
        "local_vault_path": f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
        "creator_profile_id": creator_profile_id,
        "nudity_labels": [],
        "nudity_level": "none",
        "sexual_intensity": "low",
        "gpt_vision_result": {},
        "nudenet_result": {},
        "classification_result": {},
    }


class FakeAssetRepository:
    def __init__(self):
        self.assets = {}

    def add_asset(self, asset_id, **kwargs):
        asset = Asset.from_row(asset_row(asset_id, **kwargs))
        self.assets[asset_id] = asset
        return asset

    def get_by_id(self, asset_id, *, connection=None):
        return self.assets.get(asset_id)

    def get_active_canonical_reference_asset_id(self, creator_profile_id, *, connection=None):
        for asset in self.assets.values():
            metadata = (asset.media_metadata or {}).get("reference_library") or {}
            if (
                asset.creator_profile_id == creator_profile_id
                and metadata.get("is_reference")
                and metadata.get("active")
                and metadata.get("canonical")
            ):
                return asset.id
        return None

    def get_active_canonical_reference_asset(self, creator_profile_id, *, connection=None):
        asset_id = self.get_active_canonical_reference_asset_id(
            creator_profile_id,
            connection=connection,
        )
        return self.get_by_id(asset_id, connection=connection) if asset_id else None

    def clear_active_reference_flags(self, creator_profile_id, *, connection=None):
        changed = 0
        for asset in tuple(self.assets.values()):
            metadata = dict((asset.media_metadata or {}).get("reference_library") or {})
            if asset.creator_profile_id == creator_profile_id and metadata.get("active"):
                self.update_reference_metadata(asset.id, {**metadata, "active": False})
                changed += 1
        return changed

    def search_assets(self, **kwargs):
        values = list(self.assets.values())
        creator_profile_id = kwargs.get("creator_profile_id")
        if creator_profile_id is not None:
            values = [
                asset
                for asset in values
                if asset.creator_profile_id == creator_profile_id
            ]
        search = (kwargs.get("search") or "").lower()
        if search:
            values = [
                asset
                for asset in values
                if search in (asset.file_name or "").lower()
            ]
        if kwargs.get("is_reference_image") is True:
            values = [
                asset
                for asset in values
                if (asset.media_metadata or {})
                .get("reference_library", {})
                .get("is_reference")
            ]
        return values[: kwargs.get("limit", 500)]

    def update_media_metadata(self, asset_id, media_metadata, *, connection=None):
        asset = self.assets[asset_id]
        row = asset_row(
            asset_id,
            creator_profile_id=asset.creator_profile_id,
            file_name=asset.file_name,
            metadata=dict(media_metadata),
        )
        self.assets[asset_id] = Asset.from_row(row)

    def update_reference_metadata(self, asset_id, reference_metadata, *, connection=None):
        asset = self.assets[asset_id]
        metadata = dict(asset.media_metadata or {})
        metadata["reference_library"] = dict(reference_metadata)
        self.update_media_metadata(asset_id, metadata)


class FakeAssetLibraryService:
    def __init__(self, repo):
        self.repo = repo

    def build_item(self, asset):
        reference_metadata = (asset.media_metadata or {}).get("reference_library") or {}
        return AssetLibraryItem(
            asset_id=asset.id,
            file_name=asset.file_name,
            media_type=asset.media_type,
            classification=asset.classification,
            status=asset.status,
            is_active=asset.is_active,
            created_at=asset.created_at,
            preview_path=asset.local_vault_path,
            original_path=asset.local_vault_path,
            tags=asset.suggested_tags,
            themes=asset.detected_themes,
            ready_for_rotation=asset.ready_for_rotation,
            relationship=AssetRelationshipSummary(),
            publishing=AssetPublishingSummary(status="Local asset only"),
            is_reference_image=bool(reference_metadata.get("is_reference")),
        )

    def search_assets(self, filters):
        assets = self.repo.search_assets(
            search=filters.search,
            creator_profile_id=filters.creator_profile_id,
            limit=filters.limit,
        )
        return AssetLibraryResult(
            items=tuple(self.build_item(asset) for asset in assets),
            filters=filters,
            total=len(assets),
        )


class FakeAIImportWorkflow:
    def __init__(self, repo):
        self.repo = repo
        self.calls = []
        self.next_id = 100

    def import_asset(self, **kwargs):
        self.calls.append(kwargs)
        self.next_id += 1
        self.repo.add_asset(
            self.next_id,
            creator_profile_id=kwargs["creator_profile_id"],
            file_name=kwargs.get("original_filename") or Path(kwargs["media_path"]).name,
        )
        return AIImportAssetResult(
            success=True,
            media_path=str(kwargs["media_path"]),
            upload_intent=kwargs["upload_intent"],
            legacy_result={
                "success": True,
                "db_save_result": {"content_id": self.next_id},
            },
            content_id=self.next_id,
        )


class ReferenceLibraryServiceTests(unittest.TestCase):
    def make_service(self):
        repo = FakeAssetRepository()
        asset_library = FakeAssetLibraryService(repo)
        ai_import = FakeAIImportWorkflow(repo)
        service = ReferenceLibraryService(
            asset_repository=repo,
            asset_library_service=asset_library,
            ai_import_workflow=ai_import,
        )
        return service, repo, ai_import

    def test_add_reference_imports_normal_asset_and_marks_reference(self):
        service, repo, ai_import = self.make_service()

        result = service.add_reference(
            media_path="data/uploads/reference.png",
            creator_profile_id=7,
            original_filename="reference.png",
            fanvue_account_id=3,
            favorite=True,
            make_active=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(ai_import.calls[0]["upload_intent"], "teaser_image")
        self.assertFalse(ai_import.calls[0]["create_product_draft"])
        asset = repo.get_by_id(result.asset_id)
        metadata = asset.media_metadata["reference_library"]
        self.assertTrue(metadata["is_reference"])
        self.assertTrue(metadata["favorite"])
        self.assertTrue(metadata["active"])
        self.assertEqual(metadata["creator_profile_id"], 7)
        self.assertIn("vault/originals/images", asset.local_vault_path)

    def test_active_reference_is_creator_specific(self):
        service, repo, _ = self.make_service()
        repo.add_asset(1, creator_profile_id=1, file_name="creator_one_a.png")
        repo.add_asset(2, creator_profile_id=1, file_name="creator_one_b.png")
        repo.add_asset(3, creator_profile_id=2, file_name="creator_two.png")

        service.mark_asset_as_reference(1, creator_profile_id=1, make_active=True)
        service.mark_asset_as_reference(2, creator_profile_id=1, make_active=True)
        service.mark_asset_as_reference(3, creator_profile_id=2, make_active=True)

        self.assertEqual(
            service.get_active_reference(creator_profile_id=1).asset_id,
            2,
        )
        self.assertEqual(
            service.get_active_reference(creator_profile_id=2).asset_id,
            3,
        )
        self.assertFalse(
            repo.get_by_id(1).media_metadata["reference_library"]["active"]
        )

    def test_active_canonical_id_is_direct_creator_scoped_lookup(self):
        service, repo, _ = self.make_service()
        repo.add_asset(10, creator_profile_id=1)
        repo.add_asset(20, creator_profile_id=2)
        service.mark_asset_as_reference(10, creator_profile_id=1, make_active=True)
        service.mark_asset_as_reference(20, creator_profile_id=2, make_active=True)
        for asset_id in (10, 20):
            metadata = dict(repo.get_by_id(asset_id).media_metadata["reference_library"])
            repo.update_reference_metadata(asset_id, {**metadata, "canonical": True})

        service.list_references = lambda *_args, **_kwargs: self.fail(
            "direct canonical lookup must not enumerate Reference Library"
        )

        self.assertEqual(
            service.get_active_canonical_asset_id(creator_profile_id=1),
            10,
        )
        self.assertEqual(
            service.get_active_canonical_asset_id(creator_profile_id=2),
            20,
        )

    def test_active_canonical_id_returns_none_safely(self):
        service, repo, _ = self.make_service()
        repo.add_asset(10, creator_profile_id=1)
        service.mark_asset_as_reference(10, creator_profile_id=1, make_active=True)

        self.assertIsNone(
            service.get_active_canonical_asset_id(creator_profile_id=1)
        )
        self.assertIsNone(service.get_active_canonical_asset_id(creator_profile_id=None))

    def test_active_reference_context_avoids_reference_library_enrichment(self):
        service, repo, _ = self.make_service()
        repo.add_asset(10, creator_profile_id=1)
        service.mark_asset_as_reference(10, creator_profile_id=1, make_active=True)
        metadata = dict(repo.get_by_id(10).media_metadata["reference_library"])
        repo.update_reference_metadata(10, {**metadata, "canonical": True, "last_used_at": "2026-07-21T19:00:00Z"})
        service.list_references = lambda *_args, **_kwargs: self.fail(
            "lightweight context must not enumerate Reference Library"
        )

        self.assertEqual(service.get_active_reference_context(creator_profile_id=1), {
            "asset_id": 10,
            "last_used_at": "2026-07-21T19:00:00Z",
        })

    def test_active_canonical_projection_is_scoped_and_avoids_enrichment(self):
        service, repo, _ = self.make_service()
        repo.add_asset(10, creator_profile_id=1)
        repo.add_asset(20, creator_profile_id=2)
        service.mark_asset_as_reference(10, creator_profile_id=1, make_active=True)
        service.mark_asset_as_reference(20, creator_profile_id=2, make_active=True)
        for asset_id in (10, 20):
            metadata = dict(repo.get_by_id(asset_id).media_metadata["reference_library"])
            repo.update_reference_metadata(asset_id, {**metadata, "canonical": True})
        service.list_references = lambda *_args, **_kwargs: self.fail(
            "canonical projection must not enumerate Reference Library"
        )
        service.asset_library.build_item = lambda *_args, **_kwargs: self.fail(
            "canonical projection must not build enriched Asset Library items"
        )

        projection = service.get_active_canonical_reference(creator_profile_id=2)

        self.assertIsNotNone(projection)
        self.assertEqual(projection.asset_id, 20)
        self.assertEqual(projection.creator_profile_id, 2)
        self.assertEqual(projection.asset.file_name, "asset_20.png")
        self.assertIsNone(service.get_active_canonical_reference(creator_profile_id=3))

    def test_owned_reference_validation_is_lightweight_and_creator_scoped(self):
        service, repo, _ = self.make_service()
        repo.add_asset(30, creator_profile_id=1)
        service.mark_asset_as_reference(30, creator_profile_id=1)
        service.asset_library.build_item = lambda *_args, **_kwargs: self.fail(
            "owned-reference validation must not enrich Asset Library items"
        )

        reference = service.get_owned_reference(30, creator_profile_id=1)

        self.assertIsNotNone(reference)
        self.assertEqual(reference.asset_id, 30)
        self.assertIsNone(service.get_owned_reference(30, creator_profile_id=2))
        self.assertIsNone(service.get_owned_reference(999, creator_profile_id=1))

    def test_canonical_replacement_check_and_clear_avoid_collection_enrichment(self):
        service, repo, _ = self.make_service()
        repo.add_asset(40, creator_profile_id=1)
        repo.add_asset(41, creator_profile_id=1)
        repo.add_asset(50, creator_profile_id=2)
        service.mark_asset_as_reference(40, creator_profile_id=1, make_active=True)
        service.mark_asset_as_reference(41, creator_profile_id=1)
        service.mark_asset_as_reference(50, creator_profile_id=2, make_active=True)
        metadata = dict(repo.get_by_id(40).media_metadata["reference_library"])
        repo.update_reference_metadata(40, {**metadata, "canonical": True})
        service.get_active_reference = lambda **_kwargs: self.fail(
            "replacement check must not use enriched active reference"
        )
        service.list_references = lambda *_args, **_kwargs: self.fail(
            "mutation must not enumerate Reference Library"
        )

        blocked = service.set_active_reference(41, creator_profile_id=1)
        replaced = service.set_active_reference(
            41,
            creator_profile_id=1,
            confirm_replace_canonical=True,
        )

        self.assertFalse(blocked.success)
        self.assertTrue(replaced.success)
        self.assertFalse(repo.get_by_id(40).media_metadata["reference_library"]["active"])
        self.assertTrue(repo.get_by_id(41).media_metadata["reference_library"]["active"])
        self.assertTrue(repo.get_by_id(50).media_metadata["reference_library"]["active"])

    def test_remove_reference_preserves_asset(self):
        service, repo, _ = self.make_service()
        repo.add_asset(4, creator_profile_id=1)
        service.mark_asset_as_reference(4, creator_profile_id=1, make_active=True)

        result = service.remove_reference(4, creator_profile_id=1)

        self.assertTrue(result.success)
        self.assertIsNotNone(repo.get_by_id(4))
        metadata = repo.get_by_id(4).media_metadata["reference_library"]
        self.assertFalse(metadata["is_reference"])
        self.assertFalse(metadata["active"])
        self.assertIsNotNone(metadata["removed_at"])

    def test_protected_reference_cannot_be_removed_even_with_confirmation(self):
        service, repo, _ = self.make_service()
        repo.add_asset(84, creator_profile_id=1)
        service.mark_asset_as_reference(84, creator_profile_id=1, make_active=True)
        metadata = dict(repo.get_by_id(84).media_metadata["reference_library"])
        repo.update_reference_metadata(84, {**metadata, "canonical": True, "protected": True, "role": "creator_identity"})

        result = service.remove_reference(84, creator_profile_id=1, confirm_canonical=True)

        self.assertFalse(result.success)
        self.assertIn("Protected Reference", result.message)
        self.assertTrue(repo.get_by_id(84).media_metadata["reference_library"]["is_reference"])

    def test_search_and_favorite_filters(self):
        service, repo, _ = self.make_service()
        repo.add_asset(5, creator_profile_id=1, file_name="red_dress.png")
        repo.add_asset(6, creator_profile_id=1, file_name="blue_room.png")
        service.mark_asset_as_reference(
            5,
            creator_profile_id=1,
            favorite=True,
        )
        service.mark_asset_as_reference(6, creator_profile_id=1)

        search_result = service.list_references(
            ReferenceLibraryFilter(search="red", creator_profile_id=1)
        )
        favorite_result = service.list_references(
            ReferenceLibraryFilter(creator_profile_id=1, favorites_only=True)
        )

        self.assertEqual([ref.asset_id for ref in search_result.references], [5])
        self.assertEqual([ref.asset_id for ref in favorite_result.references], [5])

    def test_asset_library_identifies_reference_images(self):
        repo = FakeAssetRepository()
        asset = repo.add_asset(
            8,
            metadata={
                "local_vault_path": "C:/Creator-OS/data/cms/vault/originals/images/8.png",
                "reference_library": {"is_reference": True},
            },
        )
        service = AssetLibraryService.__new__(AssetLibraryService)

        self.assertTrue(service._is_reference_image(asset))

    def test_content_studio_consumes_active_reference_service(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("get_active_canonical_reference", source)
        self.assertNotIn(".get_active_reference(", source)
        self.assertIn('"Social Studio", "Premium Studio", "Creative Director"', source)
        self.assertIn("ReferenceLibraryService", source)

    def test_streamlit_active_reference_render_accepts_resolved_context(self):
        from app.dashboard.pages import content_studio

        rendered = []
        original_st = content_studio.st
        content_studio.st = SimpleNamespace(
            markdown=lambda value: rendered.append(("markdown", value)),
            success=lambda value: rendered.append(("success", value)),
            caption=lambda value: rendered.append(("caption", value)),
            warning=lambda value: rendered.append(("warning", value)),
            info=lambda value: rendered.append(("info", value)),
        )
        service = SimpleNamespace(
            get_active_canonical_reference=lambda **_kwargs: self.fail(
                "resolved render context must not perform a duplicate lookup"
            ),
            get_active_reference=lambda **_kwargs: self.fail(
                "render must not use enriched active reference"
            ),
        )
        reference = SimpleNamespace(asset_id=84, last_used_at="2026-07-21T20:00:00Z")
        try:
            content_studio._render_active_reference(
                creator_profile={"id": 2},
                reference_service=service,
                show_preview=False,
                reference=reference,
            )
        finally:
            content_studio.st = original_st

        self.assertIn(("success", "Active Reference selected: Asset #84"), rendered)


if __name__ == "__main__":
    unittest.main()
