import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.photoshoot_queue import PhotoshootSession
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_summary_service import PhotoshootSummaryService


def _session():
    return PhotoshootSession(
        session_id="session-1", creator_profile_id=7, title="Photoshoot Studio",
        reference_asset_id=None, creative_mode="premium", status="running", provider_id="flux",
        creator_notes=None,
        creative_continuity={
            "seed_image_id": "seed-1",
            "original_photoshoot_direction": "Cinematic hotel editorial with a warm, intimate mood.",
        },
        request_ids=("seed", "approved", "rejected", "candidate"), current_request_id=None,
        created_at="2026-07-18T12:00:00Z", updated_at=None, metadata={},
    )


def _request(request_id, status, prompt, direction=None):
    return SimpleNamespace(
        request_id=request_id, session_id="session-1", status=status, prompt_text=prompt,
        metadata={"creative_direction": direction or {}},
    )


class FakeQueue:
    def __init__(self):
        self.session = _session()
        self.requests = [
            _request("seed", "approved", "Warm hotel bedroom, standing full body editorial portrait."),
            _request("approved", "approved", "Same hotel, seated medium shot in a black dress.", {
                "title": "Quiet cinematic progression", "pose_composition": "Seated at the window",
                "camera_framing": "Medium shot", "lighting": "Warm window light",
            }),
            _request("rejected", "rejected", "Rejected neon beach overhead pose."),
            _request("candidate", "awaiting_review", "Candidate kitchen mirror close-up in a bikini."),
        ]
        self.recorded = []

    def get_session(self, session_id):
        assert session_id == self.session.session_id
        return self.session

    def requests_for_session(self, session_id):
        assert session_id == self.session.session_id
        return tuple(self.requests)

    def record_photoshoot_summary(self, *, session_id, summary):
        self.recorded.append(dict(summary))
        continuity = {**self.session.creative_continuity, "photoshoot_summary": dict(summary)}
        self.session = replace(self.session, creative_continuity=continuity)
        return self.session


def test_summary_uses_only_approved_shots_and_synthesizes_repeated_prompts():
    queue = FakeQueue()
    queue.requests.insert(2, _request(
        "duplicate", "approved", "Same hotel, seated medium shot in a black dress.",
        {"pose_composition": "Seated at the window", "camera_framing": "Medium shot"},
    ))

    summary = PhotoshootSummaryService(queue=queue).build("session-1")
    serialized = json.dumps(summary).lower()

    assert summary["approved_shot_count"] == 3
    assert summary["major_poses_explored"] == ["Seated at the window", "standing", "seated"]
    assert summary["camera_compositions_explored"] == ["Medium shot", "full body"]
    assert "rejected" not in serialized and "neon" not in serialized and "beach" not in serialized
    assert "candidate" not in serialized and "kitchen" not in serialized and "bikini" not in serialized
    assert "Same hotel, seated medium shot in a black dress." not in summary["summary_text"]


def test_summary_refresh_persists_and_evolves_after_approval():
    queue = FakeQueue()
    service = PhotoshootSummaryService(queue=queue)
    before = service.refresh("session-1")
    queue.requests[-1].status = "approved"
    after = service.refresh("session-1")

    assert before["approved_shot_count"] == 2
    assert after["approved_shot_count"] == 3
    assert after["current_location"] == "mirror"
    assert len(queue.recorded) == 2
    assert queue.session.creative_continuity["photoshoot_summary"] == after


def test_approving_a_candidate_automatically_refreshes_summary():
    session = _session()
    candidate = SimpleNamespace(
        request_id="candidate", session_id="session-1", status="awaiting_review",
        sequence_index=3, prompt_plan_id="plan-3", metadata={"generated_image_ids": ("shot-3",)},
    )
    approved = SimpleNamespace(request_id="candidate", status="approved")
    queue = Mock()
    queue.get_session.return_value = session
    queue.get_request.return_value = candidate
    queue.approve_request.return_value = approved
    library = Mock()
    library.approve_creator_content.return_value = SimpleNamespace(success=True, imported_asset_ids=(101,), errors=(), message="")
    library.approve_photoshoot_records.return_value = SimpleNamespace(success=True, errors=(), message="")
    summary = Mock()
    service = PhotoshootManualService(
        queue=queue, engine=Mock(), library=library, ingestion=Mock(), summary_service=summary,
    )

    result = service.approve(creator_profile_id=7, session_id="session-1", request_id="candidate")

    assert result is approved
    summary.refresh.assert_called_once_with("session-1")
