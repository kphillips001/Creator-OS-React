from types import SimpleNamespace

import pytest

from app.services.engagement_teaser_intake_service import EngagementTeaserIntakeService


class FakeLibrary:
    def __init__(self, *, creator_profile_id=7, status="active"):
        self.record = SimpleNamespace(image_id="generation-1", creator_profile_id=creator_profile_id, status=status)
        self.events = []

    def get(self, image_id):
        assert image_id == "generation-1"
        return self.record

    def move_to_asset_library(self, image_id):
        self.events.append("staged")
        self.record = SimpleNamespace(**{**vars(self.record), "status": "staged_asset_library"})
        return self.record, False

    def mark_business_registered(self, image_id, asset_id):
        self.events.append(("finalized", asset_id))
        self.record = SimpleNamespace(**{**vars(self.record), "status": "business_asset_registered"})


class FakeRegistration:
    def __init__(self, library):
        self.library = library
        self.calls = []

    def register(self, record, **kwargs):
        self.calls.append(kwargs)
        self.library.events.append("intelligence")
        return SimpleNamespace(success=True, asset_id=42, already_registered=False, analysis_status="PENDING")


class FakeDestinations:
    def __init__(self, library, *, fail=False):
        self.library = library
        self.fail = fail
        self.calls = []

    def designate_engagement_teaser(self, asset_id, *, creator_profile_id):
        self.calls.append((asset_id, creator_profile_id))
        self.library.events.append("teaser")
        if self.fail:
            raise ValueError("destination conflict")


def service(*, creator_profile_id=7, status="active", destination_failure=False):
    library = FakeLibrary(creator_profile_id=creator_profile_id, status=status)
    registration = FakeRegistration(library)
    destinations = FakeDestinations(library, fail=destination_failure)
    intake = EngagementTeaserIntakeService(
        generation_library=library, registration=registration, destinations=destinations,
    )
    intake._assert_not_owned = lambda image_id: None
    return intake, library, registration, destinations


def test_intake_runs_canonical_registration_and_intelligence_before_teaser_disposition():
    intake, library, registration, destinations = service()
    result = intake.add("generation-1", creator_profile_id=7)
    assert result.asset_id == 42
    assert library.events == ["staged", "intelligence", "teaser", ("finalized", 42)]
    assert registration.calls == [{
        "creator_profile_id": 7,
        "registration_purpose": "ENGAGEMENT_TEASER",
        "finalize_generation": False,
    }]
    assert destinations.calls == [(42, 7)]


def test_retry_reuses_registered_asset_and_remains_idempotent():
    intake, library, registration, destinations = service(status="business_asset_registered")
    result = intake.add("generation-1", creator_profile_id=7)
    assert result.already_registered is True
    assert "staged" not in library.events
    assert destinations.calls == [(42, 7)]


def test_destination_failure_does_not_finalize_generation_disposition():
    intake, library, _, _ = service(destination_failure=True)
    with pytest.raises(ValueError, match="destination conflict"):
        intake.add("generation-1", creator_profile_id=7)
    assert not any(isinstance(event, tuple) and event[0] == "finalized" for event in library.events)


def test_cross_creator_intake_is_hidden():
    intake, _, _, _ = service(creator_profile_id=8)
    with pytest.raises(KeyError):
        intake.add("generation-1", creator_profile_id=7)
