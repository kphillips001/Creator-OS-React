import json
from datetime import datetime, timezone
from uuid import uuid4

from app.models.background_operation import BackgroundOperation
from app.models.generation_library import GeneratedImageRecord, GenerationLibraryFilter
from app.services.background_operation_service import BackgroundOperationService
from app.services.generation_library_service import GenerationLibraryService


def record(image_id="image-1", *, status="active", provider="seedream", mode="premium"):
    return GeneratedImageRecord(
        image_id=image_id, generation_job_id=f"job-{image_id}", generation_request_id="request",
        generation_result_id="result", output_reference=f"C:/{image_id}.png", creator_profile_id=7,
        provider_id=provider, prompt_plan_id="plan", prompt_text="portrait", creative_mode=mode,
        reference_asset_id=93, generation_date="2026-08-11T12:00:00Z", status=status,
    )


class Projection:
    def __init__(self):
        self.version = None
        self.records = ()
        self.syncs = 0

    def source_version(self): return self.version
    def synchronize(self, records, *, source_version):
        self.records = tuple(records); self.version = source_version; self.syncs += 1
    def browse_page(self, filters, *, page, page_size):
        values = [item for item in self.records if item.creator_profile_id == filters.creator_profile_id and item.status == "active"]
        return tuple(values[(page - 1) * page_size:page * page_size]), len(values), ("seedream",), ("premium",)
    def staged(self, *, creator_profile_id, search=None):
        return tuple(item for item in self.records if item.creator_profile_id == creator_profile_id and item.status == "staged_asset_library")
    def staged_count(self, creator_profile_id): return len(self.staged(creator_profile_id=creator_profile_id))
    def get(self, image_id): return next((item for item in self.records if item.image_id == image_id), None)


def test_projection_backfill_is_idempotent_and_browse_is_bounded(tmp_path):
    projection = Projection()
    service = GenerationLibraryService(storage_dir=tmp_path / "library", projection_repository=projection)
    service._write_records([record(f"image-{index}") for index in range(100)])
    assert projection.syncs == 1
    page, total, providers, modes = service.browse_page(
        GenerationLibraryFilter(creator_profile_id=7), page=3, page_size=20,
    )
    assert len(page) == 20 and total == 100
    assert providers == ("seedream",) and modes == ("premium",)
    service.ensure_read_projection()
    assert projection.syncs == 1


def test_canonical_write_updates_staged_projection_without_duplicate(tmp_path):
    projection = Projection()
    service = GenerationLibraryService(storage_dir=tmp_path / "library", projection_repository=projection)
    staged = record("staged", status="staged_asset_library")
    service._write_records([staged])
    service._write_records([staged])
    assert service.staged_count(7) == 1
    assert service.staged_records(creator_profile_id=7) == (staged,)
    assert len(projection.records) == 1


def test_operation_summary_omits_heavy_metadata_but_detail_keeps_it():
    operation = BackgroundOperation(
        operation_id=uuid4(), operation_type="content_studio_generation",
        originating_workspace="content_studio", creator_profile_id=7, account_id=1,
        subject_type="creator_profile", subject_id="7", idempotency_key="key", executor_key="worker",
        status="RUNNING", metadata={"phase": "GENERATING", "providerPayload": "x" * 100_000,
                                    "prompt": "private", "completedCount": 2},
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    service = BackgroundOperationService(repository=object())
    summary = service.summary_payload(operation)
    detail = service.payload(operation)
    assert summary["metadata"] == {"phase": "GENERATING", "completedCount": 2}
    assert "providerPayload" not in json.dumps(summary, default=str)
    assert detail["metadata"]["providerPayload"] == "x" * 100_000
    assert len(json.dumps(summary, default=str)) < 2_000


class Canonical:
    def __init__(self, values): self.values={item.image_id: item for item in values}; self.revision=2; self.upserts=[]; self.deletes=[]
    def count(self): return len(self.values)
    def state(self): return self.revision, "legacy"
    def list_payloads(self): return tuple(item.__dict__ for item in self.values.values())
    def get_payload(self, image_id): return self.values.get(image_id).__dict__ if image_id in self.values else None
    def upsert(self, values):
        values=tuple(values); self.upserts.append(tuple(item.image_id for item in values)); self.values.update({item.image_id:item for item in values}); self.revision+=1; return self.revision
    def delete(self, ids):
        ids=tuple(ids); self.deletes.append(ids); [self.values.pop(value,None) for value in ids]; self.revision+=1; return self.revision
    def replace_all(self, values, legacy_version=None, bootstrap=False):
        raise AssertionError("runtime canonical mutations must not replace the collection")


class IncrementalProjection(Projection):
    def upsert(self, values, *, source_version): self.records=tuple(values); self.version=source_version
    def delete(self, ids, *, source_version): self.records=tuple(item for item in self.records if item.image_id not in ids); self.version=source_version


def test_canonical_single_record_mutation_does_not_rewrite_legacy_snapshot(tmp_path):
    initial = record("image-1")
    canonical = Canonical((initial,))
    projection = IncrementalProjection()
    service = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical, projection_repository=projection)
    service.records_path.parent.mkdir(parents=True)
    service.records_path.write_text("legacy snapshot", encoding="utf-8")
    before = service.records_path.read_bytes()
    service.move_to_asset_library("image-1")
    assert canonical.upserts == [("image-1",)]
    assert canonical.values["image-1"].status == "staged_asset_library"
    assert service.records_path.read_bytes() == before


def test_photoshoot_candidate_isolation_upserts_only_candidate(tmp_path):
    historical, candidate = record("historical"), record("candidate")
    source = tmp_path / "candidate.png"; source.write_bytes(b"candidate")
    candidate = GeneratedImageRecord(**{**candidate.__dict__, "output_reference": str(source)})
    canonical = Canonical((historical, candidate)); projection = IncrementalProjection()
    service = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical,
                                       projection_repository=projection)
    result = service.mark_photoshoot_session_records((candidate.image_id,), session_id="session-1")
    assert result.success
    assert canonical.upserts == [("candidate",)]
    assert canonical.values["historical"] == historical
    assert canonical.values["candidate"].status == "photoshoot_session"


def test_already_moved_photoshoot_candidate_reconciles_idempotently(tmp_path):
    missing = tmp_path / "old" / "candidate.png"
    destination = tmp_path / "library" / "photoshoot_sessions" / "active" / "Photoshoot_2026-08-11_abc"
    destination.mkdir(parents=True)
    moved = destination / "Candidate_candidate.png"; moved.write_bytes(b"candidate")
    candidate = GeneratedImageRecord(**{**record("candidate").__dict__, "output_reference": str(missing)})
    canonical = Canonical((candidate,)); projection = IncrementalProjection()
    service = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical,
                                       projection_repository=projection)
    service._photoshoot_session_dir = lambda *_args, **_kwargs: destination
    first = service.mark_photoshoot_session_records((candidate.image_id,), session_id="session-1")
    second = service.mark_photoshoot_session_records((candidate.image_id,), session_id="session-1")
    assert first.success and second.success
    assert canonical.values["candidate"].output_reference == str(moved)
    assert moved.is_file() and len(tuple(destination.glob("Candidate_candidate*"))) == 1


def test_canonical_write_records_guard_rejects_runtime_collection_replacement(tmp_path):
    canonical = Canonical((record("protected"),))
    service = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical,
                                       projection_repository=IncrementalProjection())
    try:
        service._write_records([record("protected")])
    except RuntimeError as error:
        assert "bootstrap-only" in str(error)
    else:
        raise AssertionError("whole-library replacement was not rejected")


def test_projection_failure_after_canonical_commit_converges_on_restart(tmp_path):
    initial = record("image-1")
    canonical = Canonical((initial,))
    projection = IncrementalProjection()
    projection.version = "db:0"
    service = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical, projection_repository=projection)
    service._replace_record(GeneratedImageRecord(**{**initial.__dict__, "status": "staged_asset_library"}))
    projection.version = "db:2"  # simulate stale projection after canonical revision 3
    restarted = GenerationLibraryService(storage_dir=tmp_path / "library", canonical_repository=canonical, projection_repository=projection)
    restarted.ensure_read_projection()
    assert projection.version == "db:3"
    assert projection.records[0].status == "staged_asset_library"
