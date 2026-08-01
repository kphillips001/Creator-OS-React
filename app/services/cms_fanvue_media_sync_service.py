"""Disabled compatibility boundary for retired CMS/Fanvue media sync."""

from app.services.legacy_commerce_path import disabled_legacy_commerce_path


class CMSFanvueMediaSyncService:
    def __init__(self, **_kwargs):
        pass

    upload_and_store_media_ids = disabled_legacy_commerce_path
