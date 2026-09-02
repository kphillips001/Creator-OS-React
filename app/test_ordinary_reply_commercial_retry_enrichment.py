from pathlib import Path


def test_commercial_retry_enrichment_returns_unsent_retryable_to_generated():
    source = Path(
        "app/repositories/ordinary_chat_reply_repository.py"
    ).read_text(encoding="utf-8")

    method = source.split("def update_generated_payload", 1)[1].split(
        "def fail_generation", 1
    )[0]
    assert "state='GENERATED'" in method
    assert "state IN ('GENERATED','RETRYABLE')" in method
    assert "send_attempt_count=0" in method
    assert "outbound_telegram_message_id IS NULL" in method
    assert "response_payload IS NOT NULL" in method
    assert "next_retry_at=NULL" in method
    assert "last_error=NULL" in method


def test_commercial_retry_enrichment_does_not_claim_or_confirm_the_send():
    source = Path(
        "app/repositories/ordinary_chat_reply_repository.py"
    ).read_text(encoding="utf-8")
    method = source.split("def update_generated_payload", 1)[1].split(
        "def fail_generation", 1
    )[0]

    assert "send_attempt_count=send_attempt_count+1" not in method
    assert "outbound_telegram_message_id=%s" not in method
    assert "SENT_CONFIRMED" not in method
