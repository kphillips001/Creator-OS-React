"""Disabled compatibility boundary for retired CMS upload-link execution."""

from app.services.legacy_commerce_path import disabled_legacy_commerce_path


class CMSFanvueUploadLinkService:
    create_upload_link = disabled_legacy_commerce_path
    get_upload_link = disabled_legacy_commerce_path
    mark_uploading = disabled_legacy_commerce_path
    mark_uploaded = disabled_legacy_commerce_path
    mark_failed = disabled_legacy_commerce_path
