from pathlib import Path

from app.services.mass_ppv_send_service import MassPPVSendService
from app.services.mass_ppv_worker_service import MassPPVWorkerService


class Safety:
    def check_global_safety(self): return {"allowed": True}
    def can_send_mass_ppv(self): return {"allowed": True}


def test_mass_ppv_live_send_defaults_off(monkeypatch):
    monkeypatch.delenv("MASS_PPV_LIVE_SEND_ENABLED", raising=False)
    assert MassPPVSendService.live_send_enabled() is False


def test_direct_live_invocation_fails_closed_before_provider(monkeypatch):
    monkeypatch.delenv("MASS_PPV_LIVE_SEND_ENABLED", raising=False)
    service = MassPPVSendService(fanvue_account_id=2)
    service.global_safety = Safety()
    result = service.send_mass_ppv_campaign(
        fanvue_account_id=2, targets=[{"fanvue_user": {"id": 7}}],
        content_item={"id": 3}, caption="x", price=3, dry_run=False)
    assert result["blocked"] is True
    assert result["reason"] == "mass_ppv_live_send_shelved"
    assert result["sent_count"] == 0


def test_worker_does_not_claim_queue_while_shelved(monkeypatch):
    monkeypatch.delenv("MASS_PPV_LIVE_SEND_ENABLED", raising=False)
    worker = MassPPVWorkerService()
    worker.send_service.global_safety = Safety()
    assert worker.process_pending_queue() == []
    assert worker.process_retryable_queue() == []


def test_future_enablement_is_explicit_and_contact_authority_remains_integrated(monkeypatch):
    monkeypatch.setenv("MASS_PPV_LIVE_SEND_ENABLED", "true")
    assert MassPPVSendService.live_send_enabled() is True
    source = Path("app/services/mass_ppv_send_service.py").read_text()
    assert "authorize_proactive" in source
    assert "ContactPurpose.MASS_PPV" in source
