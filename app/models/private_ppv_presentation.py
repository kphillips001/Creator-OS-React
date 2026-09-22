"""Canonical customer-visible presentation for one private-chat PPV offer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrivatePpvPresentation:
    offering_id: str
    publication_id: str
    purchase_intent_id: str
    delivery_identity: str
    teaser_asset_id: int
    teaser_path: str
    message_text: str
    unlock_button_label: str
    unlock_button_url: str
    attribution_identity: str

    def apply_to(self, payload: dict) -> None:
        """Project the one canonical contract into the durable delivery payload."""
        payload.update({
            "asset_path": self.teaser_path,
            "message_text": self.message_text,
            "media_link": self.unlock_button_url,
            "delivery_url": self.unlock_button_url,
            "delivery_method": "private_ppv_media",
        })
        metadata = payload.setdefault("metadata", {})
        metadata.update({
            "private_ppv_presentation": {
                "offering_id": self.offering_id,
                "publication_id": self.publication_id,
                "purchase_intent_id": self.purchase_intent_id,
                "delivery_identity": self.delivery_identity,
                "attribution_identity": self.attribution_identity,
                "safe_teaser_asset_id": self.teaser_asset_id,
                "safe_teaser_path": self.teaser_path,
            },
            "private_chat_unlock_button": {
                "label": self.unlock_button_label,
                "url": self.unlock_button_url,
            },
        })
