from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.asset_library import PhotoshootCommerceAssignmentRequest, PhotoshootSellingModeRequest
from app.models.photoshoot_selling_mode import PhotoshootSellingMode
from app.models.bundle_sales_channel import BundleSalesChannel
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


class Repository:
    def __init__(self, row=None, protected=False, blockers=None):
        self.row = row
        self.protected = protected
        self.blockers = blockers
        self.updates = []
        self.invalidations = []

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

    def selling_mode_reassignment_blockers(self, *_args):
        return self.blockers if self.blockers is not None else ({"purchase_intent_count": 1} if self.protected else {})

    def reassign_selling_mode(self, deliverable_id, creator_profile_id, selling_mode):
        blockers = self.selling_mode_reassignment_blockers(deliverable_id, creator_profile_id)
        protected_keys = {"publication_count", "purchase_intent_count", "lifecycle_count", "lifecycle_event_count", "sales_session_count"}
        if any(int(blockers.get(key) or 0) for key in protected_keys):
            return None, blockers
        updated = self.update_selling_mode(deliverable_id, creator_profile_id, selling_mode)
        self.invalidate_session_sales_strategies(deliverable_id, creator_profile_id)
        return updated, {}

    def invalidate_session_sales_strategies(self, deliverable_id, creator_profile_id):
        self.invalidations.append((deliverable_id, creator_profile_id))
        return ()

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
        bundle_preparation=SimpleNamespace(inspect=lambda *args, **kwargs: {
            "contentVaultPublication": {"status": "NOT_PUBLISHED"},
        }),
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


def test_generation_library_import_uses_the_same_canonical_modes():
    repository = Repository(row(
        selling_mode="BUNDLE", source_kind="GENERATION_LIBRARY_IMPORT"))
    assert service(repository).set_selling_mode("set-1", 7, "SESSION")["selling_mode"] == "SESSION"
    assert repository.updates == [("set-1", 7, "SESSION")]


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
    with pytest.raises(ValueError, match="purchase intent or purchase history"):
        service(repository).set_selling_mode("set-1", 7, "BUNDLE")


def test_successful_reassignment_invalidates_only_mode_specific_session_strategy():
    repository = Repository(row())
    result = service(repository).set_selling_mode("set-1", 7, "BUNDLE")
    assert result["selling_mode"] == "BUNDLE"
    assert repository.invalidations == [("set-1", 7)]


def test_unconsumed_preparation_is_safe_to_reassign_and_reprepare():
    repository = Repository(row(), blockers={"offering_count": 2, "teaser_count": 1})
    assert service(repository).set_selling_mode("set-1", 7, "BUNDLE")["selling_mode"] == "BUNDLE"
    assert repository.invalidations == [("set-1", 7)]


@pytest.mark.parametrize(("blocker", "expected"), [
    ("sales_session_count", "Photoshoot sales session"),
    ("lifecycle_count", "customer Photoshoot lifecycle"),
    ("publication_count", "publication state"),
])
def test_customer_and_mode_specific_commerce_blocks_reassignment(blocker, expected):
    repository = Repository(row(), blockers={blocker: 1})
    with pytest.raises(ValueError, match=expected):
        service(repository).set_selling_mode("set-1", 7, "BUNDLE")
    assert repository.updates == []
    assert repository.invalidations == []


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


def test_combined_assignment_changes_bundle_channel_without_changing_mode():
    repository = Repository(row(selling_mode="BUNDLE", bundle_sales_channel="CHAT"))
    result = service(repository).reassign_commerce(
        "set-1", 7, selling_mode="BUNDLE", bundle_sales_channel="CONTENT_WALL",
    )
    assert result["selling_mode"] == "BUNDLE"
    assert result["bundle_sales_channel"] == "CONTENT_WALL"
    assert repository.updates == [("set-1", 7, "CONTENT_WALL")]


def test_combined_assignment_rejects_session_channel_and_bundle_without_channel():
    subject = service(Repository(row()))
    with pytest.raises(ValueError, match="only for BUNDLE"):
        subject.reassign_commerce(
            "set-1", 7, selling_mode="SESSION", bundle_sales_channel="CHAT",
        )
    with pytest.raises(ValueError, match="requires CHAT or CONTENT_WALL"):
        subject.reassign_commerce("set-1", 7, selling_mode="BUNDLE")
    with pytest.raises(ValidationError):
        PhotoshootCommerceAssignmentRequest(
            sellingMode="BUNDLE", bundleSalesChannel="BOTH",
        )


def test_published_wall_bundle_cannot_be_reassigned_to_chat():
    repository = Repository(row(selling_mode="BUNDLE", bundle_sales_channel="CONTENT_WALL"))
    subject = PhotoshootCommerceDeliverableService(
        repository=repository, queue=SimpleNamespace(), library=SimpleNamespace(),
        intelligence=SimpleNamespace(), commercial_intelligence=SimpleNamespace(),
        session_sales_strategy=SimpleNamespace(), workflows=SimpleNamespace(),
        bundle_preparation=SimpleNamespace(inspect=lambda *args, **kwargs: {
            "contentVaultPublication": {"status": "PUBLISHED"},
        }),
    )
    with pytest.raises(ValueError, match="publishing has started"):
        subject.reassign_commerce(
            "set-1", 7, selling_mode="BUNDLE", bundle_sales_channel="CHAT",
        )
    assert repository.updates == []
