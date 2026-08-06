from pathlib import Path
from types import SimpleNamespace

from app.services.conversation_gateway import ConversationGateway


class Engine:
    def process_message(self, *_args, **_kwargs):
        return {}


class Builder:
    def build(self, _decision):
        return None


class Assets:
    def get_by_id(self, asset_id):
        return {"id": asset_id, "file_path": "C:/vault/teaser.jpg"}


class Resolver:
    def resolve_original(self, asset, *, require_exists):
        assert asset["id"] == 51 and require_exists is True
        return SimpleNamespace(path=Path("C:/vault/teaser.jpg"), source="file_path")


def decision(role="FREE_TEASER"):
    action = SimpleNamespace(
        action=SimpleNamespace(value="CONTINUE_PHOTOSHOOT"), selected_asset_id=51,
        current_photoshoot_id="session-1",
        metadata={"sessionRuntime": {
            "lifecycleId": "life-1", "photoshootSessionId": "session-1",
            "currentAssetId": 51, "currentSalesRole": role,
        }},
    )
    return SimpleNamespace(next_sales_action=action)


def gateway():
    return ConversationGateway(
        Engine(), allowed_fanvue_hostnames=("fanvue.com",),
        photoshoot_conversation_context_builder=Builder(),
        asset_repository=Assets(), runtime_media_resolver=Resolver(),
    )


def test_authoritative_free_teaser_uses_canonical_asset_without_offering():
    result = gateway()._authoritative_delivery(
        response_text="A little preview", offering=None,
        customer_sales_decision=decision(),
    )
    _, delivery_type, delivery_mode, requires_payment, payload = result
    assert (delivery_type, delivery_mode, requires_payment) == ("FREE", "asset", False)
    assert payload["asset_path"] == "C:\\vault\\teaser.jpg" or payload["asset_path"] == "C:/vault/teaser.jpg"
    assert payload["message_text"] == "A little preview"
    assert payload["metadata"]["free_teaser_delivery"]["asset_id"] == 51
    assert payload["metadata"]["free_teaser_delivery"]["lifecycle_id"] == "life-1"
    assert "product_reference" not in payload


def test_non_free_step_does_not_receive_direct_asset_delivery():
    result = gateway()._authoritative_delivery(
        response_text="Continue", offering=None,
        customer_sales_decision=decision("FIRST_UNLOCK"),
    )
    assert result[1:4] == ("text", "conversation", False)
    assert "asset_path" not in result[4]


def test_migration_enforces_provider_delivery_idempotency():
    sql = Path(
        "migrations/forward/20260805_038_free_teaser_delivery_events.sql"
    ).read_text(encoding="utf-8")
    assert "provider_delivery_id TEXT" in sql
    assert "CREATE UNIQUE INDEX" in sql
    assert "lifecycle_id, event_type, asset_id, provider, provider_delivery_id" in sql
