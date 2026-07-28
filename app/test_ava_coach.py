from datetime import datetime, timezone
from uuid import uuid4

from app.services.ava_coach_service import AvaCoachService


def message(id, thread, direction, text, day=1):
    return {
        "id": id, "thread_id": thread, "fanvue_user_id": thread,
        "direction": direction,
        "sender_type": "bot" if direction == "outbound" else "user",
        "text": text,
        "sent_at": datetime(2026, 7, day, 12, tzinfo=timezone.utc),
    }


class Repository:
    def __init__(self, messages):
        self.messages = messages
        self.snapshot = None
        self.insight_rows = []
        self.recommendation_rows = []
        self.improvement_rows = []
        self.versions_rows = [
            {"version_id": uuid4(), "version_label": "Ava v1.0", "status": "BASELINE"},
            {"version_id": uuid4(), "version_label": "Ava v1.1", "status": "DRAFT"},
        ]

    def conversation_messages(self, account_id):
        return self.messages

    def create_snapshot(self, **values):
        self.snapshot = {"snapshot_id": uuid4(), "created_at": datetime.now(timezone.utc), **values}
        return self.snapshot

    def add_insight(self, *, snapshot_id, account_id, insight):
        row = {"insight_id": uuid4(), **insight}
        self.insight_rows.append(row)
        return row

    def target_version(self):
        return self.versions_rows[1]

    def upsert_recommendation(self, *, account_id, target_version_id, recommendation):
        row = {
            "recommendation_id": uuid4(), "status": "PENDING",
            "version_label": "Ava v1.1", "approved_at": None,
            **recommendation,
        }
        self.recommendation_rows.append(row)
        return row

    def latest_snapshot(self, account_id):
        return self.snapshot

    def insights(self, snapshot_id):
        return self.insight_rows

    def recommendations(self, account_id):
        return self.recommendation_rows

    def improvements(self, account_id):
        return self.improvement_rows

    def versions(self):
        return self.versions_rows

    def approve_and_apply(self, recommendation_id):
        row = next(item for item in self.recommendation_rows if item["recommendation_id"] == recommendation_id)
        row["status"] = "APPROVED_FOR_VERSION"
        improvement = {
            "improvement_id": uuid4(), "recommendation_id": recommendation_id,
            "version_label": "Ava v1.1", "status": "APPROVED_FOR_VERSION",
        }
        self.improvement_rows.append(improvement)
        return {"recommendation": row, "improvement": improvement}

    def transition(self, recommendation_id, status):
        row = next(item for item in self.recommendation_rows if item["recommendation_id"] == recommendation_id)
        row["status"] = status
        return row

    def edit_recommendation(self, recommendation_id, *, title, description):
        row = next(item for item in self.recommendation_rows if item["recommendation_id"] == recommendation_id)
        row.update(title=title, description=description)
        return row


def evidence_messages():
    return [
        message(1, 10, "inbound", "I went hiking by the beach", 1),
        message(2, 10, "outbound", "How was hiking?", 1),
        message(3, 10, "outbound", "Did you enjoy the beach?", 1),
        message(4, 10, "inbound", "The beach was lovely", 2),
        message(5, 10, "outbound", "Hey tell me more", 2),
        message(6, 10, "outbound", "Hey what happened next?", 2),
    ]


def test_conversation_summary_uses_persisted_message_evidence():
    repository = Repository(evidence_messages())
    result = AvaCoachService(repository).analyze(1)
    assert result["overview"]["totalConversationsReviewed"] == 1
    assert result["overview"]["totalMessagesReviewed"] == 6
    assert result["overview"]["averageConversationLength"] == 6
    assert result["overview"]["returningVisitors"] == 1
    assert result["overview"]["questionsAsked"] == 3
    assert any(item["topic"] == "beach" for item in result["overview"]["topicsDiscussed"])
    topic = next(item for item in result["overview"]["topicsDiscussed"] if item["topic"] == "beach")
    assert topic["conversationCount"] == 1
    assert topic["messageCount"] == 3
    assert topic["trend"] is None


def test_recommendations_are_generated_only_with_cited_evidence():
    repository = Repository(evidence_messages())
    result = AvaCoachService(repository).analyze(1)
    consecutive = next(
        item for item in result["recommendations"]
        if item["recommendation_key"] == "reduce_consecutive_questions"
    )
    assert consecutive["evidence"]["messageIdPairs"] == [[2, 3]]
    assert 0 <= consecutive["confidence"] <= 1
    assert all(item["evidence"] for item in result["recommendations"])


def test_no_evidence_produces_no_recommendations():
    repository = Repository([])
    result = AvaCoachService(repository).analyze(1)
    assert result["recommendations"] == []
    assert result["overview"]["totalMessagesReviewed"] == 0


def test_approval_records_version_history_without_runtime_mutation():
    repository = Repository(evidence_messages())
    service = AvaCoachService(repository)
    dashboard = service.analyze(1)
    recommendation = dashboard["recommendations"][0]
    service.transition(recommendation["recommendation_id"], "approve")
    refreshed = service.dashboard(1)
    assert refreshed["appliedImprovements"][0]["status"] == "APPROVED_FOR_VERSION"
    assert refreshed["recommendations"][0]["status"] == "APPROVED_FOR_VERSION"
    assert refreshed["versions"][1]["version_label"] == "Ava v1.1"
    assert refreshed["observationalOnly"] is True


def test_reject_and_dismiss_remain_in_history():
    for action, expected in (("reject", "REJECTED"), ("dismiss", "DISMISSED")):
        repository = Repository(evidence_messages())
        service = AvaCoachService(repository)
        recommendation = service.analyze(1)["recommendations"][0]
        result = service.transition(recommendation["recommendation_id"], action)
        assert result["status"] == expected


def test_pending_recommendation_can_be_edited_before_approval():
    repository = Repository(evidence_messages())
    service = AvaCoachService(repository)
    recommendation = service.analyze(1)["recommendations"][0]
    edited = service.edit_recommendation(
        recommendation["recommendation_id"],
        title="  A clearer title  ", description="  Operator-edited guidance.  ",
    )
    assert edited["title"] == "A clearer title"
    assert edited["description"] == "Operator-edited guidance."
