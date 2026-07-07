"""Future provider-neutral PublishingRecord contract.

A.3.2 contract only. This module does not define a persistent model, database
table, repository, or workflow. It documents how legacy Fanvue-specific
publishing fields should map to a future provider-neutral PublishingRecord.
"""

from __future__ import annotations


PUBLISHING_RECORD_FIELDS = (
    "id",
    "product_id",
    "asset_id",
    "provider",
    "provider_account_id",
    "provider_status",
    "provider_preview_status",
    "provider_full_status",
    "provider_media_id",
    "provider_preview_media_id",
    "provider_full_media_id",
    "provider_set_id",
    "provider_set_status",
    "provider_message_id",
    "provider_output_url",
    "destination",
    "delivery_method",
    "delivery_type",
    "provider_folder_id",
    "provider_metadata",
    "provider_error",
    "uploaded_at",
    "created_at",
    "updated_at",
)


PROVIDER_NEUTRAL_FIELD_NAMES = {
    "fanvue_account_id": "provider_account_id",
    "fanvue_upload_status": "provider_status",
    "fanvue_preview_upload_status": "provider_preview_status",
    "fanvue_full_upload_status": "provider_full_status",
    "fanvue_media_uuid": "provider_media_id",
    "fanvue_media_preview_uuid": "provider_preview_media_id",
    "fanvue_media_full_uuid": "provider_full_media_id",
    "fanvue_preview_media_uuid": "provider_preview_media_id",
    "fanvue_full_media_uuid": "provider_full_media_id",
    "fanvue_ptv_set_id": "provider_set_id",
    "fanvue_set_status": "provider_set_status",
    "last_fanvue_message_uuid": "provider_message_id",
    "fanvue_upload_error": "provider_error",
    "fanvue_upload_metadata": "provider_metadata",
    "fanvue_uploaded_at": "uploaded_at",
    "media_link": "provider_output_url",
    "delivery_type": "delivery_type",
    "vault_folder_id": "provider_folder_id",
}


CONTENT_ITEMS_TO_PUBLISHING_RECORD = {
    "id": "asset_id",
    "fanvue_account_id": "provider_account_id",
    "fanvue_upload_status": "provider_status",
    "fanvue_preview_upload_status": "provider_preview_status",
    "fanvue_full_upload_status": "provider_full_status",
    "fanvue_media_preview_uuid": "provider_preview_media_id",
    "fanvue_media_full_uuid": "provider_full_media_id",
    "fanvue_ptv_set_id": "provider_set_id",
    "fanvue_set_status": "provider_set_status",
    "last_fanvue_message_uuid": "provider_message_id",
    "fanvue_upload_metadata": "provider_metadata",
    "fanvue_upload_error": "provider_error",
    "fanvue_uploaded_at": "uploaded_at",
}


PRODUCTS_TO_PUBLISHING_RECORD = {
    "id": "product_id",
    "media_link": "provider_output_url",
    "fulfillment_status": "provider_status",
    "fulfillment_strategy": "delivery_method",
    "delivery_type": "delivery_type",
}


LEGACY_UPLOAD_LINK_TO_PUBLISHING_RECORD = {
    "content_item_id": "asset_id",
    "fanvue_account_id": "provider_account_id",
    "upload_status": "provider_status",
    "fanvue_media_uuid": "provider_media_id",
    "fanvue_preview_media_uuid": "provider_preview_media_id",
    "fanvue_full_media_uuid": "provider_full_media_id",
    "destination": "destination",
    "delivery_method": "delivery_method",
    "vault_folder_id": "provider_folder_id",
    "error_message": "provider_error",
}


PUBLISHING_RECORD_LEGACY_FIELD_MAP = {
    "content_items": CONTENT_ITEMS_TO_PUBLISHING_RECORD,
    "products": PRODUCTS_TO_PUBLISHING_RECORD,
    "legacy_upload_link": LEGACY_UPLOAD_LINK_TO_PUBLISHING_RECORD,
}


PUBLISHING_RECORD_INTENTIONALLY_EXCLUDED_FIELDS = {
    "file_path": "Asset storage field; belongs to Asset and RuntimeMediaResolver.",
    "local_vault_path": "Asset storage field; belongs to Local Vault ownership.",
    "classification": "Asset/Product metadata, not provider publishing state.",
    "price_cents": "Product commerce field.",
    "mass_ppv_price": "Product/campaign pricing field.",
    "ready_for_rotation": "Legacy CMS availability flag, not provider state.",
    "upload_intent": "Import/Product planning field; may inform publishing but is not output state.",
    "content_tier": "Product catalog segmentation, not provider state.",
    "distribution_type": "Product/customer distribution planning, not provider state.",
}
