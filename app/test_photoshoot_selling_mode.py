from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.asset_library import PhotoshootSellingModeRequest
from app.models.photoshoot_selling_mode import PhotoshootSellingMode
from app.models.bundle_sales_channel import BundleSalesChannel
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


class Repository:
    def __init__(self, row=None, protected=False):
        self.row = row
        self.protected = protected
        self.updates = []

    def get(self, _deliverable_id):
        return self.row

    def update_selling_mode(self, deliverable_id, creator_profile_id, selling_mode):
        self.updates.append((deliverable_id, creator_profile_id, selling_mode))
        if self.protected:
            return None
        self.row = {**self.row, "selling_mode": selling_mode}
        return self.row

    def has_protected_commercial_evidence(self, *_args):
        return self.protected

    def update_bundle_sales_channel(self, deliverable_id, creator_profile_id, channel):
        self.updates.append((deliverable_id, creator_profile_id, channel))
        if self.protected:
            return None
        self.row = {**self.row, "bundle_sales_channel": channel}
        return self.row

    def has_bundle_channel_use_evidence(self, *_args):
        return self.protected


def service(repository):
    return PhotoshootCommerceDeliverableService(
        repository=repository, queue=SimpleNamespace(), library=SimpleNamespace(),
        intelligence=SimpleNamespace(), commercial_intelligence=SimpleNamespace(),
        session_sales_strategy=SimpleNamespace(), workflows=SimpleNamespace(),
    )


def row(**changes):
    value = {"deliverable_id": "set-1", "creator_profile_id": 7, "selling_mode": "SESSION"}
    value.update(changes)
    return value


def test_missing_legacy_value_defaults_to_session_without_write():
    repository = Repository(row(selling_mode=None))
    result = service(repository).set_selling_mode("set-1", 7, "SESSION")
    assert (result.get("selling_mode") or "SESSION") == "SESSION"
    assert repository.updates == []


def test_safe_mode_changes_persist_in_both_directions():
    repository = Repository(row())
    subject = service(repository)
    assert subject.set_selling_mode("set-1", 7, "BUNDLE")["selling_mode"] == "BUNDLE"
    assert subject.set_selling_mode("set-1", 7, "SESSION")["selling_mode"] == "SESSION"
    assert repository.updates == [("set-1", 7, "BUNDLE"), ("set-1", 7, "SESSION")]


def test_invalid_mode_is_rejected_by_domain_and_api_contract():
    with pytest.raises(ValueError, match="SESSION or BUNDLE"):
        PhotoshootSellingMode.parse("OTHER")
    with pytest.raises(ValidationError):
        PhotoshootSellingModeRequest(sellingMode="OTHER")


def test_missing_or_other_creator_deliverable_is_not_disclosed():
    with pytest.raises(KeyError, match="not found"):
        service(Repository(None)).set_selling_mode("missing", 7, "BUNDLE")
    with pytest.raises(KeyError, match="not found"):
        service(Repository(row(creator_profile_id=8))).set_selling_mode("set-1", 7, "BUNDLE")


def test_protected_commercial_evidence_locks_mode_change():
    repository = Repository(row(), protected=True)
    with pytest.raises(ValueError, match="live publication or confirmed purchase"):
        service(repository).set_selling_mode("set-1", 7, "BUNDLE")


def test_existing_bundle_defaults_to_chat_and_channel_persists_both_directions():
    repository = Repository(row(selling_mode="BUNDLE", bundle_sales_channel=None))
    subject = service(repository)
    assert subject.set_bundle_sales_channel("set-1", 7, "CHAT").get("bundle_sales_channel") is None
    assert repository.updates == []
    assert subject.set_bundle_sales_channel("set-1", 7, "CONTENT_WALL")["bundle_sales_channel"] == "CONTENT_WALL"
    assert subject.set_bundle_sales_channel("set-1", 7, "CHAT")["bundle_sales_channel"] == "CHAT"


def test_bundle_channel_validation_scope_and_session_firewall():
    with pytest.raises(ValueError, match="CHAT or CONTENT_WALL"):
        BundleSalesChannel.parse("BOTH")
    with pytest.raises(ValidationError):
        from app.api.asset_library import BundleSalesChannelRequest
        BundleSalesChannelRequest(bundleSalesChannel="BOTH")
    with pytest.raises(ValueError, match="requires BUNDLE"):
        service(Repository(row())).set_bundle_sales_channel("set-1", 7, "CHAT")
    with pytest.raises(KeyError, match="not found"):
        service(Repository(row(selling_mode="BUNDLE", creator_profile_id=8))).set_bundle_sales_channel("set-1", 7, "CHAT")


def test_bundle_channel_use_locks_change_but_preparation_does_not():
    unlocked = Repository(row(selling_mode="BUNDLE", bundle_sales_channel="CHAT"))
    assert service(unlocked).set_bundle_sales_channel("set-1", 7, "CONTENT_WALL")["bundle_sales_channel"] == "CONTENT_WALL"
    protected = Repository(row(selling_mode="BUNDLE", bundle_sales_channel="CHAT"), protected=True)
    with pytest.raises(ValueError, match="presented or a purchase intent"):
        service(protected).set_bundle_sales_channel("set-1", 7, "CONTENT_WALL")
