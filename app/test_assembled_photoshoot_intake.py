from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.assembled_photoshoot_intake_service import AssembledPhotoshootIntakeService
from app.services.assembled_photoshoot_background_executor import AssembledPhotoshootBackgroundExecutor
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


def record(image_id, *, owner=7, status="active", asset_id=None):
    return SimpleNamespace(
        image_id=image_id, creator_profile_id=owner, status=status,
        imported_asset_id=asset_id, output_reference=f"/media/{image_id}.png",
        prompt_text=f"prompt {image_id}", generation_recipe_id=f"recipe-{image_id}",
        generation_metadata={"regeneration_source": "original"}, prompt_metadata={},
    )


class Library:
    def __init__(self, records):
        self.records = {item.image_id: item for item in records}
        self.finalized = []
        self.links = []

    def get(self, image_id):
        if image_id not in self.records:
            raise KeyError(image_id)
        return self.records[image_id]

    def mark_business_registered(self, image_id, asset_id):
        self.finalized.append((image_id, asset_id))

    def mark_registered(self, image_id, asset_id):
        self.links.append((image_id, asset_id))


class IntakeRepository:
    def __init__(self):
        self.row = None
        self.member_rows = []
        self.finalized = None
        self.dispositions_reconciled = 0

    def create(self, **values):
        if self.row:
            return self.row, False
        self.row = {**values, "status": "QUEUED", "deliverable_id": None, "operation_id": None,
                    "ordered_image_ids": list(values["image_ids"])}
        self.member_rows = [{"image_id": value, "position": index, "asset_id": None}
                            for index, value in enumerate(values["image_ids"], 1)]
        return self.row, True

    def attach_operation(self, intake_id, operation_id):
        self.row["operation_id"] = operation_id; return self.row

    def get(self, intake_id): return self.row
    def members(self, intake_id): return tuple(self.member_rows)
    def start(self, intake_id): self.row["status"] = "PROCESSING"; return self.row
    def record_asset(self, intake_id, image_id, asset_id):
        next(item for item in self.member_rows if item["image_id"] == image_id)["asset_id"] = asset_id
    def waiting(self, intake_id): self.row["status"] = "WAITING_INTELLIGENCE"
    def fail(self, intake_id, error): self.row["status"] = "FAILED"
    def finalize(self, **values):
        self.finalized = values; self.row.update(status="SUCCEEDED", deliverable_id=values["deliverable_id"])
        self.dispositions_reconciled = len(self.member_rows)
        return self.row
    def reconcile_dispositions(self, intake_id):
        self.dispositions_reconciled = len(self.member_rows)
        return self.dispositions_reconciled


class Operations:
    def __init__(self):
        self.operation = SimpleNamespace(operation_id=uuid4(), status="QUEUED")
        self.succeeded = None
        self.repository = self

    def create(self, **values): return self.operation, True
    def get(self, *args, **kwargs): return self.operation
    def progress(self, *args, **kwargs): pass
    def stage(self, *args, **kwargs): pass
    def transition(self, *args, **kwargs): pass
    def succeed(self, operation_id, **values): self.succeeded = values


def test_intake_validates_batch_ownership_and_is_idempotent():
    library = Library([record("a"), record("b")])
    repository, operations = IntakeRepository(), Operations()
    service = AssembledPhotoshootIntakeService(
        repository=repository, generation_library=library, operations=operations)
    with pytest.raises(ValueError, match="at least two"):
        service.create(creator_profile_id=7, account_id=1, image_ids=["a"])
    with pytest.raises(ValueError, match="unique"):
        service.create(creator_profile_id=7, account_id=1, image_ids=["a", "a"])
    intake, operation, created = service.create(
        creator_profile_id=7, account_id=1,
        image_ids=["b", "a"], hero_image_id="a")
    assert created is True
    assert intake["ordered_image_ids"] == ["b", "a"]
    repeated, same_operation, repeated_created = service.create(
        creator_profile_id=7, account_id=1,
        image_ids=["b", "a"], hero_image_id="a")
    assert repeated_created is False
    assert same_operation.operation_id == operation.operation_id
    assert repeated["intake_id"] == intake["intake_id"]
    assert intake["display_name"] == f"internal:assembled-photoshoot:{intake['intake_id']}"


def test_executor_reuses_registration_and_finalizes_one_bundle_only_photoshoot():
    records = [record("b"), record("a")]
    library, repository, operations = Library(records), IntakeRepository(), Operations()
    intake_id = uuid4()
    repository.row = {"intake_id": intake_id, "creator_profile_id": 7,
                      "display_name": "Imported Set", "hero_image_id": "a",
                      "status": "QUEUED", "deliverable_id": None}
    repository.member_rows = [{"image_id": "b", "position": 1, "asset_id": None},
                              {"image_id": "a", "position": 2, "asset_id": None}]

    class Registration:
        def register(self, item, **kwargs):
            assert kwargs == {"creator_profile_id": 7, "registration_purpose": "PHOTOSHOOT_MEMBER",
                              "finalize_generation": False}
            return SimpleNamespace(success=True, asset_id={"b": 81, "a": 82}[item.image_id],
                                   analysis_status="READY", message="")

    class Photoshoots:
        def content_intelligence_for_assets(self, asset_ids):
            return tuple({"asset_id": value, "content_intelligence_status": "COMPLETE",
                          "content_profile": {"summary": f"Asset {value}"},
                          "normalized_context": {"setting": "studio"}} for value in asset_ids)

    class Deliverables:
        def __init__(self): self.call = None
        def run_source_neutral_intelligence(self, **values): self.call = values; return {"status": "READY", "commercial_title": "AI Imported Title"}

    deliverables = Deliverables()
    executor = AssembledPhotoshootBackgroundExecutor(
        repository=repository, library=library, registration=Registration(),
        photoshoots=Photoshoots(), deliverables=deliverables)
    operation = SimpleNamespace(operation_id=operations.operation.operation_id,
                                metadata={"intake_id": str(intake_id)}, subject_id=str(intake_id))
    executor.execute(operation, operations, worker_id="test")

    assert repository.finalized["asset_ids"] == [81, 82]
    assert repository.finalized["hero_asset_id"] == 82
    assert repository.finalized["session_key"] == f"assembled:{intake_id}"
    assert repository.finalized["display_name"] == "AI Imported Title"
    assert deliverables.call["display_name"] == ""
    assert [item["shot_order"] for item in deliverables.call["chapters"]] == [1, 2]
    assert library.links == [("b", 81), ("a", 82)]
    assert library.finalized == []
    assert operations.succeeded["metadata"]["source_kind"] == "GENERATION_LIBRARY_IMPORT"
    assert repository.dispositions_reconciled == 2


def test_source_neutral_intelligence_omits_internal_provisional_name():
    class Intelligence:
        def __init__(self): self.approved_metadata=None
        def generate(self, **values):
            self.approved_metadata=values["approved_metadata"]
            return {"commercial_title":"AI Title","subtitle":"Subtitle",
                    "commercial_summary":"Summary","buyer_profile":{"audience":"buyer"},
                    "sales_strategy":{"approach":"direct"},"sales_brain_brief":{"hook":"story"}}
    intelligence=Intelligence()
    service=PhotoshootCommerceDeliverableService(
        queue=object(),library=object(),repository=object(),intelligence=object(),
        commercial_intelligence=intelligence,session_sales_strategy=object(),workflows=object())
    result=service.build_source_neutral_intelligence(
        chapters=({"asset_id":1},),display_name="",hero_asset_id=1)
    assert result["commercial_title"] == "AI Title"
    assert "photoshoot_name" not in intelligence.approved_metadata
    assert intelligence.approved_metadata["source_kind"] == "GENERATION_LIBRARY_IMPORT"


def test_executor_waits_when_canonical_content_intelligence_is_incomplete():
    records = [record("a"), record("b")]
    library, repository, operations = Library(records), IntakeRepository(), Operations()
    intake_id = uuid4()
    repository.row = {"intake_id": intake_id, "creator_profile_id": 7, "display_name": "Set",
                      "hero_image_id": "a", "status": "WAITING_INTELLIGENCE", "deliverable_id": None}
    repository.member_rows = [{"image_id": "a", "position": 1, "asset_id": 1},
                              {"image_id": "b", "position": 2, "asset_id": 2}]

    class ReadyRegistration:
        calls = 0

        def register(self, item, **kwargs):
            self.calls += 1
            return SimpleNamespace(success=True, asset_id=1 if item.image_id == "a" else 2,
                                   analysis_status="READY", message="")

    class IncompleteContentIntelligence:
        def content_intelligence_for_assets(self, asset_ids):
            return ({"asset_id": 1, "content_intelligence_status": "COMPLETE"},
                    {"asset_id": 2, "content_intelligence_status": "RUNNING"})

    registration = ReadyRegistration()
    executor = AssembledPhotoshootBackgroundExecutor(
        repository=repository, library=library, registration=registration,
        photoshoots=IncompleteContentIntelligence(), deliverables=object())
    operation = SimpleNamespace(operation_id=operations.operation.operation_id,
                                metadata={"intake_id": str(intake_id)}, subject_id=str(intake_id))
    executor.execute(operation, operations, worker_id="test")

    assert registration.calls == 2
    assert repository.row["status"] == "WAITING_INTELLIGENCE"
    assert repository.finalized is None
    assert operations.succeeded is None


def test_executor_waits_without_hiding_generation_items_when_intelligence_is_pending():
    library, repository, operations = Library([record("a"), record("b")]), IntakeRepository(), Operations()
    intake_id = uuid4()
    repository.row = {"intake_id": intake_id, "creator_profile_id": 7, "display_name": "Set",
                      "hero_image_id": "a", "status": "QUEUED", "deliverable_id": None}
    repository.member_rows = [{"image_id": "a", "position": 1}, {"image_id": "b", "position": 2}]

    class Pending:
        def register(self, item, **kwargs):
            return SimpleNamespace(success=True, asset_id=1 if item.image_id == "a" else 2,
                                   analysis_status="GROK_RUNNING", message="")

    executor = AssembledPhotoshootBackgroundExecutor(
        repository=repository, library=library, registration=Pending(),
        photoshoots=object(), deliverables=object())
    operation = SimpleNamespace(operation_id=operations.operation.operation_id,
                                metadata={"intake_id": str(intake_id)}, subject_id=str(intake_id))
    executor.execute(operation, operations, worker_id="test")
    assert repository.row["status"] == "WAITING_INTELLIGENCE"
    assert repository.finalized is None
    assert library.finalized == []
    assert library.links == [("a", 1), ("b", 2)]
    assert repository.dispositions_reconciled == 0


def test_succeeded_intake_reconciles_dispositions_without_recreating_photoshoot():
    library, repository, operations = Library([record("a"), record("b")]), IntakeRepository(), Operations()
    intake_id, deliverable_id = uuid4(), uuid4()
    repository.row = {"intake_id": intake_id, "creator_profile_id": 7,
                      "status": "SUCCEEDED", "deliverable_id": deliverable_id}
    repository.member_rows = [{"image_id": "a", "position": 1, "asset_id": 1},
                              {"image_id": "b", "position": 2, "asset_id": 2}]
    executor = AssembledPhotoshootBackgroundExecutor(
        repository=repository, library=library, registration=object(),
        photoshoots=object(), deliverables=object())
    operation = SimpleNamespace(operation_id=operations.operation.operation_id,
                                metadata={"intake_id": str(intake_id)}, subject_id=str(intake_id))

    executor.execute(operation, operations, worker_id="test")

    assert repository.dispositions_reconciled == 2
    assert repository.finalized is None
    assert operations.succeeded["result_reference"] == str(deliverable_id)


def test_failed_intake_does_not_create_photoshoot_dispositions():
    library, repository, operations = Library([record("a"), record("b")]), IntakeRepository(), Operations()
    intake_id = uuid4()
    repository.row = {"intake_id": intake_id, "creator_profile_id": 7,
                      "display_name": "Set", "hero_image_id": "a",
                      "status": "QUEUED", "deliverable_id": None}
    repository.member_rows = [{"image_id": "a", "position": 1, "asset_id": None},
                              {"image_id": "b", "position": 2, "asset_id": None}]

    class Registration:
        def register(self, item, **kwargs):
            return SimpleNamespace(success=True, asset_id=1 if item.image_id == "a" else 2,
                                   analysis_status="READY", message="")
    class Photoshoots:
        def content_intelligence_for_assets(self, asset_ids):
            return tuple({"asset_id": value, "content_intelligence_status": "COMPLETE"}
                         for value in asset_ids)
    class FailingDeliverables:
        def run_source_neutral_intelligence(self, **values):
            raise RuntimeError("intelligence failed")

    executor = AssembledPhotoshootBackgroundExecutor(
        repository=repository, library=library, registration=Registration(),
        photoshoots=Photoshoots(), deliverables=FailingDeliverables())
    operation = SimpleNamespace(operation_id=operations.operation.operation_id,
                                metadata={"intake_id": str(intake_id)}, subject_id=str(intake_id))

    with pytest.raises(RuntimeError, match="intelligence failed"):
        executor.execute(operation, operations, worker_id="test")

    assert repository.row["status"] == "FAILED"
    assert repository.finalized is None
    assert repository.dispositions_reconciled == 0
