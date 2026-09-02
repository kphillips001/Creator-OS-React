from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from app.api import bundle_studio as api
from app.models.bundle_studio import BundleStudioBundle, BundleStudioMember
from app.repositories.generation_library_projection_repository import GenerationLibraryProjectionRepository
from app.models.generation_library import GenerationLibraryFilter


def bundle(*image_ids):
    now = datetime.now(timezone.utc)
    return BundleStudioBundle(
        bundle_id=uuid4(), creator_profile_id=2, name="Launch Bundle", status="ACTIVE",
        created_at=now, updated_at=now,
        members=tuple(BundleStudioMember(
            image_id=value, position=index, added_at=now, generation_job_id=f"job-{index}",
            generation_request_id=f"request-{index}", generation_recipe_id=f"recipe-{index}",
            provider_id="seedream_5_0_pro", output_reference=f"/media/{value}.png",
            prompt_text=f"Concept {index}", creative_mode="explicit", generation_date=now.isoformat(),
        ) for index, value in enumerate(image_ids, 1)),
    )


def test_batch_move_route_delegates_to_canonical_service(monkeypatch):
    calls = []
    class Service:
        def move_images(self, **values): return calls.append(values) or bundle("a", "b", "c")
    service = Service()
    monkeypatch.setattr(api, "BundleStudioService", lambda: service)
    monkeypatch.setattr(api, "_creator_id", lambda: 2)
    result = api.move_members(api.MoveImagesRequest(image_ids=["a", "b", "c"]))
    assert calls == [{"creator_profile_id": 2, "image_ids": ["a", "b", "c"], "bundle_name": "Untitled Bundle"}]
    assert [item["image_id"] for item in result["workspace"]["members"]] == ["a", "b", "c"]
    assert result["workspace"]["members"][0]["thumbnail_url"].startswith("/api/v1/generation-library/a/thumbnail")
    assert result["workspace"]["members"][0]["image_url"].startswith("/api/v1/generation-library/a/media")


def test_return_rename_reorder_and_abandon_use_same_workspace_service(monkeypatch):
    calls = []
    workspace = bundle("a", "b")
    class Service:
        def return_images(self, **values): return calls.append(("return", values)) or workspace
        def rename(self, **values): return calls.append(("rename", values)) or workspace
        def reorder(self, **values): return calls.append(("reorder", values)) or workspace
        def abandon(self, **values): return calls.append(("abandon", values)) or bundle()
    service = Service()
    monkeypatch.setattr(api, "BundleStudioService", lambda: service)
    monkeypatch.setattr(api, "_creator_id", lambda: 2)
    api.return_members(api.ImagesRequest(image_ids=["b"]))
    api.rename_workspace(api.RenameRequest(name="Renamed"))
    api.reorder_workspace(api.ImagesRequest(image_ids=["b", "a"]))
    api.abandon_workspace()
    assert [item[0] for item in calls] == ["return", "rename", "reorder", "abandon"]


def test_generation_library_filter_excludes_bundle_owned_images_before_pagination():
    clauses, _ = GenerationLibraryProjectionRepository._filters(GenerationLibraryFilter(creator_profile_id=2))
    sql = " ".join(clauses)
    assert "generation_image_dispositions" in sql
    assert "NOT EXISTS" in sql
    assert "d.image_id=generation_library_read_projection.image_id" in sql


def test_prepare_sale_route_stages_once_and_schedules_canonical_executor(monkeypatch):
    workspace = bundle("a", "b")
    calls = []
    class WorkspaceService:
        def active(self, **_): return workspace
    class Commerce:
        def stage(self, *args, **values): calls.append(("stage", args, values)); return ("publication-1",)
        def inspect(self, *args, **values): return {"status": "PREPARING", "destination": "CHAT"}
    commerce = Commerce()
    class Tasks:
        def add_task(self, fn, *args): calls.append(("task", fn, args))
    monkeypatch.setattr(api, "BundleStudioService", lambda: WorkspaceService())
    monkeypatch.setattr(api, "BundleStudioSalePreparationService", lambda: commerce)
    monkeypatch.setattr(api, "_creator_commerce_identity", lambda: (2, 7))
    result = api.prepare_sale(api.PrepareSaleRequest(destination="CHAT", price_minor=1499), Tasks())
    assert result["status"] == "PREPARING"
    assert calls[0][2]["destination"] == "CHAT"
    assert calls[0][2]["fanvue_account_id"] == 7
    assert calls[1][0] == "task" and calls[1][2][0] == ("publication-1",)


def test_bundle_commerce_identity_uses_active_creator_fanvue_account(monkeypatch):
    monkeypatch.setattr(api, "_current_account_id", lambda: 12)
    monkeypatch.setattr(api, "get_active_creator_profile", lambda account_id: {
        "id": 2, "fanvue_account_id": 7, "account_id": account_id,
    })
    assert api._creator_commerce_identity() == (2, 7)


def test_commerce_migration_preserves_explicit_bundle_source_identity():
    sql = open("migrations/forward/20260812_055_bundle_studio_commerce.sql", encoding="utf-8").read()
    assert "source_bundle_studio_bundle_id" in sql
    assert "REFERENCES public.bundle_studio_bundles" in sql
    assert "bundle_studio_teasers" in sql


def test_manual_bundle_caption_persists_without_caption_provider(monkeypatch):
    offering = SimpleNamespace(offering_id=uuid4())
    publication = SimpleNamespace(publication_id=uuid4(), publication_metadata={})
    context = ({"name":"Launch Bundle"}, ({"asset_id":11},{"asset_id":12}), offering, publication)
    monkeypatch.setattr(api, "_bundle_wall_context", lambda _id: ("bundle-1", 2, context))
    saved = {}
    class Repository:
        def update_metadata(self, _id, **values): saved.update(values["metadata"]); return publication
    monkeypatch.setattr(api, "CommercialPublicationRepository", Repository)
    class Service:
        def inspect(self, *_args, **_values): return {"contentVaultCaption":saved["content_vault_caption_draft"]}
    monkeypatch.setattr(api, "BundleStudioSalePreparationService", Service)
    result = api.save_commercial_bundle_caption("bundle-1", api.CaptionRequest(text="Two private photos for you.", source="MANUAL"))
    assert result["contentVaultCaption"]["text"] == "Two private photos for you."
    assert result["contentVaultCaption"]["paidImageCount"] == 2
    assert result["contentVaultCaption"]["source"] == "MANUAL"


def test_bundle_caption_generation_reuses_profile_with_exact_member_count(monkeypatch):
    offering = SimpleNamespace(
        offering_id=uuid4(), title="Launch Bundle", price_minor=1499, currency="USD")
    members = ({"asset_id": 11}, {"asset_id": 12}, {"asset_id": 13})
    context = ({"name": "Launch Bundle"}, members, offering, SimpleNamespace())
    monkeypatch.setattr(api, "_bundle_wall_context", lambda _id: ("bundle-1", 2, context))
    captured = {}

    class Builder:
        def build(self, **values):
            captured["context"] = values
            return {"paid_image_count": len(values["paid_asset_ids"])}

    class Captions:
        def generate(self, **values):
            captured["generation"] = values
            return {"captions": [{"text": "All 3 photos are waiting."}]}

    monkeypatch.setattr(api, "ContentVaultBundleCaptionContextBuilder", Builder)
    monkeypatch.setattr(api, "GrokCaptionService", Captions)
    monkeypatch.setattr(api, "BundleStudioTeaserService", lambda: SimpleNamespace(
        inspect=lambda *_args, **_values: {"status": "READY"}))
    result = api.generate_commercial_bundle_captions(
        "bundle-1", api.CaptionGenerateRequest(guidance="Keep it playful", tone="CLASSY"))
    assert result["captions"][0]["text"].startswith("All 3")
    assert captured["context"]["paid_asset_ids"] == (11, 12, 13)
    assert captured["generation"]["profile"] is api.CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE
    assert captured["generation"]["guidance"] == "Keep it playful"
