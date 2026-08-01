"""Disabled compatibility boundary for legacy content-item delivery lookup."""

from app.services.legacy_commerce_path import disabled_legacy_commerce_path


class ContentMediaDeliveryService:
    def __init__(self, **_kwargs):
        pass

    get_media_for_delivery = disabled_legacy_commerce_path
