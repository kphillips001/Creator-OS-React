from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.repositories.ordinary_chat_reply_repository import (
    OrdinaryChatReplyRepository,
)
from app.services.gpt_service import GPTService
from app.test_phone_texting_style import memory_none, service_with, user_memory


JOHNNY_SIGNOFF = "See ya tomorrow cutie ;) Good night ❤️"


def relevance(candidate):
    return GPTService._foreground_semantic_relevance(
        JOHNNY_SIGNOFF,
        candidate,
        recent_transcript=[
            {"role": "user", "content": "Can you ski blue intermediate terrain?"},
            {"role": "user", "content": JOHNNY_SIGNOFF},
        ],
    )


def test_johnny_exact_signoff_rejects_stale_skiing_candidate():
    result = relevance(
        "I've skied some blue runs—not too shabby, I'd say. "
        "Keeping you warm sounds pretty perfect."
    )
    assert result["required"] is True
    assert result["satisfied"] is False
    assert result["intent"] == "ACKNOWLEDGE_SIGNOFF"
    assert result["currentTurnRelevanceReason"] == "CURRENT_SIGNOFF_IGNORED"


def test_signoff_acknowledgement_and_supported_callback_pass():
    assert relevance("Good night 😊 Sleep well.")["satisfied"] is True
    callback = relevance("Night 😊 Maybe dream about those mountains.")
    assert callback["satisfied"] is True
    assert callback["currentTurnConversationalFunction"] == "SIGNOFF"


def test_unrelated_old_topic_fails_current_signoff():
    assert relevance("Golf courses are always prettier at sunset.")["satisfied"] is False


def test_bounded_signoff_forms_create_obligation():
    for message in ("Good night", "See you tomorrow", "Sweet dreams"):
        obligations = GPTService._turn_obligations(
            message, new_relationship=False,
        )
        assert "ACKNOWLEDGE_SIGNOFF" in obligations


def test_signoff_style_obligation_is_binding():
    good = GPTService._style_analysis(
        "Night, you. Talk tomorrow.", JOHNNY_SIGNOFF,
        pressure={}, ordinary=True, memory_callback=False,
    )
    stale = GPTService._style_analysis(
        "I've skied blue runs before.", JOHNNY_SIGNOFF,
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert "ACKNOWLEDGE_SIGNOFF" in good["satisfiedTurnObligations"]
    assert "ACKNOWLEDGE_SIGNOFF" in stale["unsatisfiedTurnObligations"]


def test_signoff_fallback_remains_current_turn_relevant():
    fallback = GPTService._foreground_semantic_fallback(
        JOHNNY_SIGNOFF, effort_mode="NORMAL",
    )
    assert relevance(fallback)["satisfied"] is True


def test_current_turn_relevance_reruns_after_late_style_repair():
    memory = memory_none()
    service, completions = service_with(
        "I've skied some blue runs.",
        "Night, you. Talk tomorrow.",
    )
    response = service.generate_response(
        "default", "casual", JOHNNY_SIGNOFF, user_memory(memory), False,
        chat_history=[{
            "role": "user", "content": "Can you ski blue intermediate terrain?",
        }],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 2
    assert response == "Night, you. Talk tomorrow."
    assert style["currentTurnRelevanceSatisfied"] is True
    assert style["finalCandidateTransformationSource"] == "STYLE_REWRITE"


def test_archive_media_relevance_policy_is_explicit():
    relevant = OrdinaryChatReplyRepository._archive_row_relevant
    assert relevant({"customer_text": "new text", "has_media": False}) is True
    assert relevant({
        "customer_text": "", "has_media": True,
        "reconciliation_state": "LIVE_HANDLED",
    }) is True
    assert relevant({
        "customer_text": "", "has_media": True,
        "reconciliation_state": "NO_RESPONSE_REQUIRED",
    }) is False


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args):
        return self

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return Cursor(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def archive(rows):
    repository = OrdinaryChatReplyRepository(
        connection_factory=lambda: Connection(rows),
    )
    return repository.archive_freshness("operation")


def row(message_id, *, text="", media=False, state="LIVE_HANDLED",
        provenance="TELETHON_NEW_MESSAGE"):
    return {
        "authority_id": 100,
        "telegram_message_id": message_id,
        "received_at": datetime(2026, 9, 16, tzinfo=timezone.utc)
        + timedelta(seconds=message_id),
        "customer_text": text,
        "has_media": media,
        "media_types": ["PHOTO"] if media else [],
        "reconciliation_state": state,
        "ingestion_provenance": provenance,
    }


def test_newer_live_and_startup_text_are_stale():
    for provenance in (
        "TELETHON_NEW_MESSAGE", "TELETHON_STARTUP_HISTORY_RECOVERY",
    ):
        result = archive([row(100, text="old"),
                          row(101, text="new", provenance=provenance)])
        assert result["archiveFreshnessSatisfied"] is False
        assert result["newestRelevantArchivedInboundId"] == 101


def test_relevant_and_irrelevant_media_have_bounded_dispositions():
    superseding = archive([row(100, text="old"), row(101, media=True)])
    assert superseding["archiveFreshnessSatisfied"] is False
    assert superseding["mediaFreshnessDisposition"] == "CURRENT_SUPERSEDING"

    irrelevant = archive([
        row(100, text="old"),
        row(101, media=True, state="NO_RESPONSE_REQUIRED"),
    ])
    assert irrelevant["archiveFreshnessSatisfied"] is True
    assert irrelevant["mediaFreshnessDisposition"] == "IRRELEVANT_TO_CURRENT_REPLY"


def test_text_media_text_burst_coalesces_and_latest_text_governs():
    result = archive([
        row(100, text="gin and tonic"),
        row(101, media=True),
        row(102, text="See ya tomorrow. Good night."),
    ])
    assert result["newestRelevantArchivedInboundId"] == 102
    assert result["archiveFreshnessSatisfied"] is False
    assert result["mediaFreshnessDisposition"] == "COALESCED_INTO_CURRENT_TURN"


def test_atomic_send_claim_contains_archive_race_guard():
    source = Path(
        "app/repositories/ordinary_chat_reply_repository.py"
    ).read_text(encoding="utf-8")
    claim = source[source.index("def claim_send"):source.index(
        "def suppress_settled_follow_through_before_send"
    )]
    assert "telegram_private_inbound_messages archived" in claim
    assert "archived.telegram_message_id>" in claim
    assert "archived.has_media IS TRUE" in claim
    assert "NO_RESPONSE_REQUIRED" in claim
    assert "archivePreSendFreshness" in claim
