import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

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

from app.models.generation_engine import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.generation_ingestion import GENERATION_ASSET_METADATA_KEY
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class FakeAssetRepository:
    def __init__(self):
        self.updated = []
        self.assets = {
            101: SimpleNamespace(
                id=101,
                media_metadata={"local_vault_path": "vault/originals/images/101.png"},
            )
        }

    def get_by_id(self, asset_id):
        return self.assets[int(asset_id)]

    def update_media_metadata(self, asset_id, media_metadata):
        self.updated.append((asset_id, media_metadata))
        self.assets[int(asset_id)] = SimpleNamespace(
            id=int(asset_id),
            media_metadata=media_metadata,
        )


class FakeImportWorkflow:
    def __init__(self, assets):
        self.assets = assets
        self.calls = []

    def import_asset(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            success=True,
            content_id=101,
            legacy_result={"success": True, "db_save_result": {"content_id": 101}},
            asset=self.assets.get_by_id(101),
        )


class FakeResponse:
    def __init__(self, content=b"image-bytes", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("download failed")


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def successful_job(output_references=("https://cdn.test/generated.png",)):
    request = GenerationRequest(
        request_id="generation_request_1",
        creator_profile_id=7,
        prompt_plan_id="prompt_plan_1",
        prompt_text="Provider-neutral prompt text",
        reference_asset_id=55,
        reference_asset_path="https://cdn.test/reference.png",
        provider_id="seedream_4_5",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
        metadata={
            "creative_mode": "social_safe",
            "creative_tags": ("window light", "portrait"),
            "prompt_metadata": {"provider_neutral": True},
        },
    )
    result = GenerationResult(
        result_id="generation_result_1",
        request_id=request.request_id,
        job_id="generation_job_1",
        provider_id=request.provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        generation_metadata={"provider_request_id": "provider_123"},
        execution_metadata={"poll_attempts": 1},
        image_metadata={"output_count": len(output_references)},
        output_references=tuple(output_references),
    )
    return GenerationJob(
        job_id="generation_job_1",
        request=request,
        status=GenerationStatus.SUCCEEDED.value,
        result=result,
    )


class GenerationResultIngestionServiceTests(unittest.TestCase):
    def make_service(self, *, http_client=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        assets = FakeAssetRepository()
        importer = FakeImportWorkflow(assets)
        service = GenerationResultIngestionService(
            storage_dir=Path(temp_dir.name) / "state",
            download_dir=Path(temp_dir.name) / "downloads",
            import_workflow_service=importer,
            asset_repository=assets,
            http_client=http_client or FakeHttpClient(FakeResponse()),
        )
        return service, importer, assets

    def test_successful_generation_result_ingestion_imports_asset(self):
        service, importer, assets = self.make_service()

        result = service.ingest_job(successful_job())

        self.assertTrue(result.success)
        self.assertEqual(result.imported_asset_ids, (101,))
        self.assertEqual(len(importer.calls), 1)
        self.assertEqual(importer.calls[0]["creator_profile_id"], 7)
        self.assertFalse(importer.calls[0]["create_product_draft"])
        self.assertFalse(importer.calls[0]["provider_upload_enabled"])
        self.assertEqual(importer.calls[0]["import_session_id"], "generation:generation_job_1")
        self.assertTrue(Path(importer.calls[0]["media_path"]).exists())
        self.assertEqual(assets.updated[0][0], 101)

    def test_metadata_is_preserved_on_canonical_asset(self):
        service, _, assets = self.make_service()

        service.ingest_job(successful_job())

        metadata = assets.updated[0][1][GENERATION_ASSET_METADATA_KEY]
        self.assertEqual(metadata["source"], "content_studio")
        self.assertEqual(metadata["generation_provider"], "seedream_4_5")
        self.assertEqual(metadata["generation_job_id"], "generation_job_1")
        self.assertEqual(metadata["generation_request_id"], "generation_request_1")
        self.assertEqual(metadata["prompt_plan_id"], "prompt_plan_1")
        self.assertEqual(metadata["prompt_text"], "Provider-neutral prompt text")
        self.assertEqual(metadata["creative_mode"], "social_safe")
        self.assertEqual(metadata["reference_asset_id"], 55)
        self.assertEqual(metadata["creator_profile_id"], 7)
        self.assertEqual(metadata["provider_response_id"], "provider_123")
        self.assertEqual(metadata["generation_parameters"]["media_type"], "image")

    def test_duplicate_ingestion_is_prevented(self):
        service, importer, _ = self.make_service()
        job = successful_job()

        first = service.ingest_job(job)
        second = service.ingest_job(job)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(first.imported_asset_ids, (101,))
        self.assertEqual(second.imported_asset_ids, (101,))
        self.assertEqual(len(importer.calls), 1)

    def test_failed_download_is_recorded_cleanly(self):
        service, importer, _ = self.make_service(
            http_client=FakeHttpClient(FakeResponse(status_code=500))
        )

        result = service.ingest_job(successful_job())
        status = service.ingestion_status_for_job("generation_job_1")

        self.assertFalse(result.success)
        self.assertEqual(len(importer.calls), 0)
        self.assertEqual(status["status"], "failed")
        self.assertIn("download failed", status["failed_messages"][0])

    def test_local_file_output_is_copied_before_import(self):
        service, importer, _ = self.make_service()
        source_dir = tempfile.TemporaryDirectory()
        self.addCleanup(source_dir.cleanup)
        source = Path(source_dir.name) / "generated.png"
        source.write_bytes(b"local-image")

        result = service.ingest_job(successful_job((str(source),)))

        self.assertTrue(result.success)
        imported_path = Path(importer.calls[0]["media_path"])
        self.assertTrue(imported_path.exists())
        self.assertNotEqual(imported_path.resolve(), source.resolve())
        self.assertEqual(imported_path.read_bytes(), b"local-image")

    def test_generation_engine_remains_provider_neutral_and_not_asset_owner(self):
        source = Path("app/services/generation_engine_service.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("AIImportWorkflowService", source)
        self.assertNotIn("AssetIngestionService", source)
        self.assertNotIn("LocalVaultService", source)
        self.assertNotIn("content_studio_generation", source)

    def test_content_studio_displays_ingestion_status(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("GenerationResultIngestionService", source)
        self.assertIn("Completed Generation Jobs", source)
        self.assertIn("Imported Asset IDs", source)
        self.assertIn("failed_messages", source)
        self.assertIn("Import Generated Results", source)


if __name__ == "__main__":
    unittest.main()
