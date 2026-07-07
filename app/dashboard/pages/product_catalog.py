"""Streamlit Product Catalog management page."""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

import streamlit as st

from app.dashboard.components.asset_picker import render_asset_picker
from app.models.product import (
    ProductDeliveryType,
    ProductFulfillmentStatus,
    ProductStatus,
    ProductType,
    default_fulfillment_strategy,
    fulfillment_status_for_media_link,
)
from app.services.product_catalog_service import (
    ProductCatalogCommand,
    ProductCatalogError,
    ProductCatalogService,
    ProductCatalogValidationError,
)
from app.services.media_processing_service import MediaProcessingService
from app.services.publishing_service import PublishingService
from app.services.runtime_media_resolver import RuntimeMediaResolver


_RUNTIME_MEDIA_RESOLVER = RuntimeMediaResolver()
_MEDIA_PROCESSING_SERVICE = MediaProcessingService()
_PUBLISHING_SERVICE = PublishingService()


def _catalog_boundary_service() -> ProductCatalogService:
    return ProductCatalogService(
        media_processing_service=_MEDIA_PROCESSING_SERVICE,
        runtime_media_resolver=_RUNTIME_MEDIA_RESOLVER,
        publishing_service=_PUBLISHING_SERVICE,
    )


def _parse_price_cents(value: str) -> int | None:
    clean = (value or "").strip()
    if not clean:
        return None
    try:
        amount = Decimal(clean)
    except InvalidOperation as error:
        raise ProductCatalogValidationError(
            ["Price must be a valid decimal amount."]
        ) from error
    if amount.as_tuple().exponent < -2:
        raise ProductCatalogValidationError(
            ["Price may contain at most two decimal places."]
        )
    return int(amount * 100)


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _set_mode(mode: str, product_id: UUID | None = None) -> None:
    st.session_state["product_catalog_mode"] = mode
    st.session_state["product_catalog_selected_product_id"] = (
        str(product_id) if product_id else None
    )
    for key in list(st.session_state):
        if key.startswith("product_catalog_editor_"):
            del st.session_state[key]


def _render_validation_error(error: Exception) -> None:
    if isinstance(error, ProductCatalogValidationError):
        for message in error.errors:
            st.error(message)
    else:
        st.error(str(error))


def _ai_metadata(product) -> dict:
    metadata = product.metadata or {}
    return {
        "is_ai_draft": bool(metadata.get("ai_product_draft"))
        or metadata.get("draft_source") == "ai_cms_asset",
        "classification": metadata.get("classification"),
        "confidence": metadata.get("confidence"),
        "source_asset_id": (
            metadata.get("source_asset_id") or product.legacy_content_item_id
        ),
    }


def _format_confidence(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_price(cents: int | None, currency: str = "USD") -> str:
    if cents is None:
        return "Not set"
    return f"{currency} {cents / 100:.2f}"


def _asset_preview_path(asset) -> str | None:
    return _catalog_boundary_service().asset_preview_path(asset)


def _resolve_existing_media_path(value: str | Path | None) -> Path | None:
    return _catalog_boundary_service().resolve_existing_media_path(value)


def _resolve_runtime_original_asset_path(asset) -> Path | None:
    return _catalog_boundary_service().resolve_runtime_original_asset_path(asset)


def _asset_fanvue_status(asset) -> tuple[str, str]:
    summary = _catalog_boundary_service().asset_publishing_summary(asset)
    return summary.status, summary.detail


def _asset_fanvue_upload_action_state(asset) -> tuple[bool, bool, str]:
    return _catalog_boundary_service().asset_upload_action_state(asset)


def _product_fanvue_status(product, assets) -> tuple[str, str]:
    summary = _catalog_boundary_service().product_publishing_summary(
        product,
        assets,
    )
    return summary.status, summary.detail


def _display_tags(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "—"


def _render_fulfillment_status(status: ProductFulfillmentStatus) -> None:
    if status == ProductFulfillmentStatus.READY:
        st.success(status.value)
    elif status == ProductFulfillmentStatus.FAILED:
        st.error(status.value)
    else:
        st.warning(status.value)


def _render_asset_thumbnail(asset, *, caption: str | None = None) -> None:
    preview_path = _asset_preview_path(asset)
    if preview_path:
        st.image(preview_path, caption=caption, use_container_width=True)
        return
    if asset:
        st.caption(caption or "Preview unavailable")
        st.caption(f"#{asset.id} · {asset.media_type}")
    else:
        st.caption("No cover image")


def _ordered_assets(links, assets, experience=None) -> list:
    if experience:
        return list(
            _catalog_boundary_service().order_assets_for_experience(
                experience,
                assets,
            )
        )
    assets_by_id = {asset.id: asset for asset in assets}
    return [
        assets_by_id[link.asset_id]
        for link in sorted(links, key=lambda item: item.position)
        if link.asset_id in assets_by_id
    ]


def _cover_asset(ordered_assets: list, experience=None):
    return _catalog_boundary_service().cover_asset_for_experience(
        experience,
        ordered_assets,
    )


def _classification_label(product, assets) -> str:
    return _catalog_boundary_service().classification_label(product, assets)
    return "—"


def _render_product_visual_summary(product, assets) -> None:
    cover = _cover_asset(list(assets))
    cover_col, detail_col = st.columns([1, 3])
    with cover_col:
        _render_asset_thumbnail(cover, caption="Cover Image")
    with detail_col:
        st.subheader(product.display_name)
        c1, c2, c3 = st.columns(3)
        c1.metric("Classification", _classification_label(product, assets))
        c2.metric("Price", _format_price(product.price_cents, product.currency))
        c3.metric("Status", product.status.value)
        st.caption(f"Delivery Type: {product.delivery_type.value}")
        st.caption(f"Fulfillment Strategy: {product.fulfillment_strategy.value}")
        st.caption(f"Fulfillment Status: {product.fulfillment_status.value}")
        fanvue_status, fanvue_detail = _product_fanvue_status(product, assets)
        st.caption(f"Provider Vault: {fanvue_status} · {fanvue_detail}")
        st.caption(f"Tags: {_display_tags(product.tags)}")
        st.caption(f"Themes: {_display_tags(product.themes)}")


def _render_experience_presentation(display) -> None:
    experience = getattr(display, "experience_presentation", None)
    if not experience:
        return
    st.markdown("### Experience")
    c1, c2, c3 = st.columns(3)
    c1.metric("Type", experience.experience_type or "-")
    c2.metric("Assets", len(experience.asset_ids))
    readiness = experience.publishing_readiness
    c3.metric("Publishing", getattr(readiness, "status", None) or "-")
    st.write(f"**{experience.title or experience.experience_id or 'Experience'}**")
    if experience.summary:
        st.caption(experience.summary)
    if experience.experience_id:
        st.caption(f"Experience ID: {experience.experience_id}")
    if experience.cover_asset_id:
        st.caption(f"Cover Asset: #{experience.cover_asset_id}")
    if experience.themes:
        st.caption(f"Themes: {_display_tags(experience.themes)}")
    if experience.keywords:
        st.caption(f"Keywords: {_display_tags(experience.keywords)}")
    if experience.mood:
        st.caption(f"Mood: {experience.mood}")
    if experience.story_progression:
        st.caption(f"Story Progression: {experience.story_progression}")
    if experience.technical_continuity:
        st.caption(f"Technical Continuity: {experience.technical_continuity}")
    if experience.relationship_source:
        source = experience.relationship_source
        if experience.compatibility:
            source = f"{source} (compatibility)"
        st.caption(f"Relationship Source: {source}")
    if readiness:
        st.caption(readiness.detail)


def _render_photo_set_assets(assets) -> None:
    if not assets:
        return
    st.markdown("### Asset Thumbnails")
    st.caption(f"Asset Count: {len(assets)}")
    columns = st.columns(min(4, max(1, len(assets))))
    for index, asset in enumerate(assets):
        with columns[index % len(columns)]:
            _render_asset_thumbnail(
                asset,
                caption=f"{index + 1}. #{asset.id}",
            )
            status, detail = _asset_fanvue_status(asset)
            st.caption(f"Provider: {status}")
            if status != "Not uploaded to Fanvue":
                st.caption(detail)


def _render_asset_fanvue_upload_button(
    *,
    fanvue_account_id: int,
    asset,
    key: str,
    read_only: bool = False,
) -> None:
    visible, enabled, note = _asset_fanvue_upload_action_state(asset)
    if not visible:
        return
    if st.button(
        "Upload to Provider Vault",
        disabled=read_only or not fanvue_account_id or not enabled,
        key=key,
    ):
        try:
            result = _upload_asset_to_fanvue_vault(
                fanvue_account_id=fanvue_account_id,
                asset=asset,
            )
            if result.get("success"):
                st.success("Asset uploaded to Provider Vault.")
            else:
                st.error(
                    "Provider Vault upload failed: "
                    f"{result.get('error') or result}"
                )
            st.rerun()
        except Exception as error:
            st.error(f"Provider Vault upload failed: {error}")
    if read_only or not fanvue_account_id or not enabled:
        st.caption(note)


def _upload_assets_to_fanvue_vault(
    *,
    fanvue_account_id: int,
    assets,
) -> list[dict]:
    return [
        _upload_asset_to_fanvue_vault(
            fanvue_account_id=fanvue_account_id,
            asset=asset,
        )
        for asset in assets
    ]


def _upload_asset_to_fanvue_vault(
    *,
    fanvue_account_id: int,
    asset,
) -> dict:
    catalog = _catalog_boundary_service()
    status, _ = _asset_fanvue_status(asset)
    if status == "Uploaded to Fanvue":
        return {
            "asset_id": asset.id,
            "success": True,
            "skipped": True,
            "reason": "already_uploaded",
        }

    upload_item = catalog.build_asset_upload_item(asset)
    if not upload_item:
        error = "Local Vault original not found for this asset."
        result = {
            "asset_id": asset.id,
            "success": False,
            "error": error,
        }
        payload = catalog.build_upload_failure_payload(
            result,
            error=error,
        )
        catalog.publishing.record_asset_upload_payload(
            asset_id=asset.id,
            upload_payload=payload,
        )
        return result

    upload_result = catalog.publishing.upload_asset_media_item(
        fanvue_account_id=fanvue_account_id,
        item=upload_item,
    )
    if upload_result.get("success"):
        payload = catalog.build_upload_success_payload(
            upload_result,
            default_status="uploaded",
        )
        catalog.publishing.record_asset_upload_payload(
            asset_id=asset.id,
            upload_payload=payload,
        )
    else:
        payload = catalog.build_upload_failure_payload(
            upload_result,
        )
        catalog.publishing.record_asset_upload_payload(
            asset_id=asset.id,
            upload_payload=payload,
        )
    return {
        "asset_id": asset.id,
        **upload_result,
    }


def _render_catalog_list(
    service: ProductCatalogService,
    creator_profile_id: int,
) -> None:
    counts = service.products.count_by_status(creator_profile_id)
    cols = st.columns(4)
    for col, status in zip(cols, ProductStatus):
        col.metric(status.value.title(), counts.get(status.value, 0))

    action_col, _ = st.columns([1, 4])
    with action_col:
        if st.button("Create Manual Product", type="primary", use_container_width=True):
            _set_mode("CREATE")
            st.rerun()

    with st.expander("Filters", expanded=True):
        f1, f2, f3 = st.columns(3)
        search = f1.text_input("Search", key="product_catalog_search")
        status_value = f2.selectbox(
            "Status",
            ["ALL"] + [status.value for status in ProductStatus],
            key="product_catalog_status_filter",
        )
        type_value = f3.selectbox(
            "Product Type",
            ["ALL"] + [value.value for value in ProductType],
            key="product_catalog_type_filter",
        )
        f4, f5, f6 = st.columns(3)
        tag = f4.text_input("Tag", key="product_catalog_tag_filter")
        theme = f5.text_input("Theme", key="product_catalog_theme_filter")
        include_archived = f6.checkbox(
            "Include archived",
            key="product_catalog_include_archived",
        )

    products = service.products.list_products(
        creator_profile_id=creator_profile_id,
        search=search or None,
        status=None if status_value == "ALL" else ProductStatus(status_value),
        product_type=None if type_value == "ALL" else ProductType(type_value),
        tag=tag or None,
        theme=theme or None,
        include_archived=include_archived,
    )

    if products:
        st.markdown("### Products")
        for product in products:
            ai_metadata = _ai_metadata(product)
            display = service.load_display_model(product)

            with st.container():
                cover_col, name_col, type_col, status_col, action_col = st.columns(
                    [1.1, 2.8, 1.4, 1.1, 1]
                )
                with cover_col:
                    _render_asset_thumbnail(
                        display.cover_asset,
                        caption="Cover Image",
                    )
                with name_col:
                    st.write(f"**{product.display_name}**")
                    st.caption(product.internal_name)
                    if display.experience_presentation:
                        experience = display.experience_presentation
                        st.caption(
                            "Experience: "
                            f"{experience.title or experience.experience_id}"
                        )
                        if experience.mood:
                            st.caption(f"Mood: {experience.mood}")
                    st.caption(
                        f"Classification: "
                        f"{display.classification_label}"
                    )
                    st.caption(f"Tags: {_display_tags(product.tags)}")
                    st.caption(f"Themes: {_display_tags(product.themes)}")
                with type_col:
                    st.write("Product Type")
                    st.caption(product.product_type.value)
                    st.caption(f"Delivery: {product.delivery_type.value}")
                    st.caption(product.fulfillment_strategy.value)
                    if product.product_type == ProductType.PHOTO_SET:
                        st.caption(f"{len(display.ordered_assets)} assets")
                with status_col:
                    st.write("Status")
                    st.caption(product.status.value)
                    _render_fulfillment_status(product.fulfillment_status)
                    st.caption(_format_price(product.price_cents, product.currency))
                    st.caption(f"Provider: {display.publishing.status}")
                with action_col:
                    if st.button(
                        "Open Product",
                        key=f"open_product_{product.id}",
                        use_container_width=True,
                    ):
                        _set_mode("EDIT", product.id)
                        st.rerun()
                st.caption(
                    f"AI Draft: {'Yes' if ai_metadata['is_ai_draft'] else 'No'} · "
                    f"Source Asset: {ai_metadata['source_asset_id'] or '—'} · "
                    f"Updated: {product.updated_at}"
                )
                st.divider()

        st.markdown("### Product Details")
        rows = []
        for product in products:
            ai_metadata = _ai_metadata(product)
            display = service.load_display_model(product)
            rows.append(
                {
                    "Thumbnail": display.thumbnail_path or "",
                    "Display Name": product.display_name,
                    "Internal Name": product.internal_name,
                    "Type": product.product_type.value,
                    "Delivery Type": product.delivery_type.value,
                    "Fulfillment Strategy": product.fulfillment_strategy.value,
                    "Fulfillment Status": product.fulfillment_status.value,
                    "Status": product.status.value,
                    "Price": _format_price(product.price_cents, product.currency),
                    "Base Price": _format_price(
                        product.base_price_cents,
                        product.currency,
                    ),
                    "Min Price": _format_price(
                        product.min_price_cents,
                        product.currency,
                    ),
                    "Max Price": _format_price(
                        product.max_price_cents,
                        product.currency,
                    ),
                    "Provider Vault": display.publishing.status,
                    "Experience": (
                        display.experience_presentation.title
                        or display.experience_presentation.experience_id
                        if display.experience_presentation
                        else "None"
                    ),
                    "Experience Type": (
                        display.experience_presentation.experience_type
                        if display.experience_presentation
                        else "None"
                    ),
                    "Experience Readiness": (
                        display.experience_presentation.publishing_readiness.status
                        if display.experience_presentation
                        and display.experience_presentation.publishing_readiness
                        else "Unknown"
                    ),
                    "Assets": service.count_product_experience_assets(product.id),
                    "AI Draft": "Yes" if ai_metadata["is_ai_draft"] else "No",
                    "Source Asset": ai_metadata["source_asset_id"] or "—",
                    "Classification": ai_metadata["classification"] or "—",
                    "Confidence": _format_confidence(ai_metadata["confidence"]),
                    "Activation Source": product.activation_source or "—",
                    "Media Link": "Configured" if product.media_link else "Missing",
                    "Tags": ", ".join(product.tags),
                    "Updated": product.updated_at,
                }
            )
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Thumbnail": st.column_config.ImageColumn(
                    "Cover Image",
                    width="small",
                )
            },
        )
        labels = {
            f"{product.display_name} — {product.internal_name} [{product.status.value}]": product
            for product in products
        }
        selected_label = st.selectbox("Select product", list(labels))
        if st.button("Open Product"):
            _set_mode("EDIT", labels[selected_label].id)
            st.rerun()
    else:
        st.info("No products match the current filters.")

    unassigned = service.products.list_unassigned_drafts()
    if unassigned:
        with st.expander(f"Unassigned legacy drafts ({len(unassigned)})"):
            st.caption(
                "Phase 1C drafts have no creator scope. Assign them explicitly "
                "before editing them in this account's catalog."
            )
            labels = {
                f"#{product.legacy_content_item_id} — {product.display_name}": product
                for product in unassigned
            }
            selected = st.selectbox(
                "Legacy draft",
                list(labels),
                key="product_catalog_legacy_draft",
            )
            if st.button("Assign to current creator"):
                try:
                    product = service.assign_legacy_draft(
                        labels[selected].id,
                        creator_profile_id,
                    )
                    st.success("Legacy draft assigned.")
                    _set_mode("EDIT", product.id)
                    st.rerun()
                except ProductCatalogError as error:
                    _render_validation_error(error)

    with st.expander("Retry AI Draft Creation from Approved Asset"):
        st.caption(
            "Creates or refreshes a DRAFT product from an approved CMS asset. "
            "This does not activate products or set price/media link."
        )
        retry_asset_id = st.number_input(
            "Source Asset ID",
            min_value=1,
            step=1,
            key="product_catalog_retry_asset_id",
        )
        if st.button("Retry Draft Creation"):
            try:
                result = service.retry_ai_draft_for_asset(
                    int(retry_asset_id),
                    creator_profile_id,
                )
                st.success("AI Product Draft ready.")
                _set_mode("EDIT", result.product.id)
                st.rerun()
            except ProductCatalogError as error:
                _render_validation_error(error)
            except Exception as error:
                st.error(str(error))


def _render_asset_picker(
    service: ProductCatalogService,
    fanvue_account_id: int,
    editor_key: str,
    initial_asset_ids: tuple[int, ...],
) -> tuple[int, ...]:
    st.markdown("### Assets")
    asset_library = service.build_asset_library_service()
    asset_cache = {}

    def render_upload_action(asset_id, _item) -> None:
        if asset_id not in asset_cache:
            asset_cache[asset_id] = service.load_asset_by_id(asset_id)
        asset = asset_cache.get(asset_id)
        if asset:
            _render_asset_fanvue_upload_button(
                fanvue_account_id=fanvue_account_id,
                asset=asset,
                key=f"asset_upload_to_fanvue_{editor_key}_{asset_id}",
            )

    selection = render_asset_picker(
        asset_library_service=asset_library,
        picker_key=f"product_catalog_editor_{editor_key}",
        initial_asset_ids=initial_asset_ids,
        render_action=render_upload_action,
    )
    return selection.ordered_asset_ids


def _render_editor(
    service: ProductCatalogService,
    fanvue_account_id: int,
    creator_profile_id: int,
    mode: str,
) -> None:
    product = None
    initial_assets: tuple[int, ...] = ()
    initial_ordered_assets = []
    entitlement_count = 0
    editor_display = None
    if mode == "EDIT":
        product_id = UUID(st.session_state["product_catalog_selected_product_id"])
        editor = service.load_editor(product_id, creator_profile_id)
        product = editor.product
        initial_assets = service.experiences.get_ordered_asset_ids(
            editor.experience
        )
        initial_ordered_assets = list(editor.assets)
        editor_display = service.build_editor_display_model(editor)
        entitlement_count = editor.entitlement_count
        st.subheader(f"Edit Product: {product.display_name}")
    else:
        product_id = None
        st.subheader("Create Manual Product")

    editor_key = str(product_id or "new")
    if st.button("← Back to Catalog"):
        _set_mode("LIST")
        st.rerun()

    if entitlement_count:
        st.warning(
            f"This product has {entitlement_count} entitlement(s). Internal name, "
            "product type, and asset composition are locked."
        )
    if product and product.status == ProductStatus.ARCHIVED:
        st.warning("Archived products are read-only.")
    read_only = bool(product and product.status == ProductStatus.ARCHIVED)

    if product:
        _render_product_visual_summary(product, initial_ordered_assets)
        _render_experience_presentation(editor_display)
        if product.product_type == ProductType.PHOTO_SET:
            _render_photo_set_assets(initial_ordered_assets)

        st.markdown("### Publishing: Provider Vault")
        fanvue_status, fanvue_detail = _product_fanvue_status(
            product,
            initial_ordered_assets,
        )
        st.info(f"{fanvue_status}: {fanvue_detail}")
        has_uploadable_local_assets = any(
            _asset_fanvue_status(asset)[0] != "Uploaded to Fanvue"
            and _resolve_runtime_original_asset_path(asset)
            for asset in initial_ordered_assets
        )
        if st.button(
            "Upload to Provider Vault",
            disabled=(
                read_only
                or not fanvue_account_id
                or not initial_ordered_assets
                or not has_uploadable_local_assets
            ),
            key=f"upload_to_fanvue_vault_{product.id}",
        ):
            try:
                results = _upload_assets_to_fanvue_vault(
                    fanvue_account_id=fanvue_account_id,
                    assets=initial_ordered_assets,
                )
                successes = sum(1 for result in results if result.get("success"))
                failures = [
                    result for result in results if not result.get("success")
                ]
                if failures:
                    st.warning(
                        f"Provider upload completed with {len(failures)} failure(s)."
                    )
                    st.write(results)
                else:
                    st.success(f"Uploaded {successes} asset(s) to Provider Vault.")
                st.rerun()
            except Exception as error:
                st.error(f"Provider Vault upload failed: {error}")
        if not has_uploadable_local_assets:
            st.caption(
                "No local assets currently need provider upload, or local files "
                "could not be found on disk."
            )

        metadata = _ai_metadata(product)
        st.markdown("### Source Intelligence")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("AI Draft", "Yes" if metadata["is_ai_draft"] else "No")
        c2.metric("Source Asset", metadata["source_asset_id"] or "—")
        c3.metric("Classification", metadata["classification"] or "—")
        c4.metric("Confidence", _format_confidence(metadata["confidence"]))
        if product.legacy_content_item_id:
            source_assets = service.load_assets_by_ids(
                (product.legacy_content_item_id,)
            )
            if source_assets:
                source_asset = source_assets[0]
                st.caption(
                    f"Source: #{source_asset.id} — "
                    f"{source_asset.file_name or source_asset.file_path}"
                )
                if source_asset.summary:
                    st.write(source_asset.summary)
            if (
                product.status == ProductStatus.DRAFT
                and not read_only
                and st.button("Refresh From Asset")
            ):
                try:
                    refreshed = service.refresh_ai_draft_from_asset(
                        product.id,
                        creator_profile_id,
                    )
                    st.success("Refreshed from source asset intelligence.")
                    _set_mode("EDIT", refreshed.product.id)
                    st.rerun()
                except ProductCatalogError as error:
                    _render_validation_error(error)
                except Exception as error:
                    st.error(str(error))

        st.markdown("### Pricing and Activation")
        p1, p2, p3 = st.columns(3)
        p1.metric("Base Price", _format_price(product.base_price_cents, product.currency))
        p2.metric("Min Price", _format_price(product.min_price_cents, product.currency))
        p3.metric("Max Price", _format_price(product.max_price_cents, product.currency))
        st.caption(f"Activation Source: {product.activation_source or '—'}")
        st.caption(f"Activation Reason: {product.activation_reason or '—'}")

    st.markdown("### Product Identity")
    internal_name = st.text_input(
        "Internal Name",
        value=product.internal_name if product else "",
        disabled=read_only or bool(entitlement_count),
        key=f"product_catalog_editor_internal_name_{editor_key}",
    )
    display_name = st.text_input(
        "Display Name",
        value=product.display_name if product else "",
        disabled=read_only,
        key=f"product_catalog_editor_display_name_{editor_key}",
    )
    description = st.text_area(
        "Description",
        value=product.description or "" if product else "",
        disabled=read_only,
        key=f"product_catalog_editor_description_{editor_key}",
    )
    type_options = list(ProductType)
    product_type = st.selectbox(
        "Product Type",
        type_options,
        index=type_options.index(product.product_type) if product else 0,
        format_func=lambda value: value.value,
        disabled=read_only or bool(entitlement_count),
        key=f"product_catalog_editor_type_{editor_key}",
    )
    delivery_options = list(ProductDeliveryType)
    delivery_type = st.selectbox(
        "Delivery Type",
        delivery_options,
        index=delivery_options.index(product.delivery_type) if product else 0,
        format_func=lambda value: value.value,
        disabled=read_only,
        help="Product Type describes what the Product is. Delivery Type describes how it is delivered.",
        key=f"product_catalog_editor_delivery_type_{editor_key}",
    )

    st.markdown("### Price")
    c1, c2 = st.columns(2)
    price_text = c1.text_input(
        "Price",
        value=(
            "" if not product or product.price_cents is None
            else f"{product.price_cents / 100:.2f}"
        ),
        disabled=read_only,
        key=f"product_catalog_editor_price_{editor_key}",
    )
    currency = c2.text_input(
        "Currency",
        value=product.currency if product else "USD",
        max_chars=3,
        disabled=read_only,
        key=f"product_catalog_editor_currency_{editor_key}",
    )

    selected_strategy = (
        product.fulfillment_strategy
        if product
        else default_fulfillment_strategy(product_type)
    )
    fulfillment_media_link = product.media_link if product else ""
    st.markdown("### Fulfillment")
    st.caption(
        "Publish required assets to the provider vault, create the Media Link manually, "
        "then paste it here."
    )
    f1, f2 = st.columns(2)
    f1.text_input(
        "Fulfillment Strategy",
        value=selected_strategy.value,
        disabled=True,
        key=f"product_catalog_editor_fulfillment_strategy_{editor_key}",
    )
    if product:
        with f2:
            st.caption("Fulfillment Status")
            _render_fulfillment_status(product.fulfillment_status)
    else:
        with f2:
            st.caption("Fulfillment Status")
            _render_fulfillment_status(
                fulfillment_status_for_media_link(fulfillment_media_link)
            )
    media_link = st.text_input(
        "Media Link",
        value=fulfillment_media_link or "",
        disabled=read_only,
        help=(
            "HTTP/HTTPS provider link or local:// internal asset reference. "
            "AI auto-activation uses local://content_items/{id}."
        ),
        key=f"product_catalog_editor_media_link_{editor_key}",
    )
    if product and not read_only:
        if st.button(
            "Save Media Link",
            key=f"save_media_link_{product.id}",
        ):
            try:
                updated = service.save_media_link(
                    product.id,
                    creator_profile_id,
                    media_link,
                )
                st.toast("Media Link Saved", icon="✅")
                if updated.fulfillment_status == ProductFulfillmentStatus.READY:
                    st.toast("Product is READY", icon="🎉")
                    st.success("Media Link saved. Product fulfillment is READY.")
                elif updated.fulfillment_status == ProductFulfillmentStatus.FAILED:
                    st.error("Media Link saved, but fulfillment validation failed.")
                else:
                    st.warning("Media Link cleared. Product fulfillment is NOT_READY.")
                st.rerun()
            except ProductCatalogError as error:
                _render_validation_error(error)

    st.markdown("### Metadata")
    tags = st.text_input(
        "Tags (comma-separated)",
        value=", ".join(product.tags) if product else "",
        disabled=read_only,
        key=f"product_catalog_editor_tags_{editor_key}",
    )
    themes = st.text_input(
        "Themes (comma-separated)",
        value=", ".join(product.themes) if product else "",
        disabled=read_only,
        key=f"product_catalog_editor_themes_{editor_key}",
    )

    asset_ids = initial_assets if read_only or entitlement_count else _render_asset_picker(
        service,
        fanvue_account_id,
        editor_key,
        initial_assets,
    )
    if read_only or entitlement_count:
        st.markdown("### Assets")
        for position, asset in enumerate(service.load_assets_by_ids(initial_assets), 1):
            preview_col, detail_col, action_col = st.columns([1, 3, 1])
            with preview_col:
                _render_asset_thumbnail(
                    asset,
                    caption=(
                        f"{position}. Cover"
                        if position == 1
                        else f"{position}. Asset"
                    ),
                )
            with detail_col:
                st.write(f"**{position}. {asset.file_name or asset.file_path}**")
                st.caption(
                    f"Asset #{asset.id} · {asset.media_type} · "
                    f"{asset.classification} · {asset.status}"
                )
            st.write(f"{position}. #{asset.id} — {asset.file_name or asset.file_path}")

            _render_asset_fanvue_upload_button(
                fanvue_account_id=fanvue_account_id,
                asset=asset,
                key=f"asset_upload_to_fanvue_locked_{editor_key}_{asset.id}",
                read_only=read_only,
            )

    command = ProductCatalogCommand(
        creator_profile_id=creator_profile_id,
        internal_name=internal_name,
        display_name=display_name,
        description=description,
        product_type=product_type,
        price_cents=None,
        currency=currency,
        media_link=media_link,
        delivery_type=delivery_type,
        tags=_csv_values(tags),
        themes=_csv_values(themes),
        asset_ids=asset_ids,
    )

    if not read_only:
        save_col, activate_col = st.columns(2)
        if save_col.button("Save Draft" if not product else "Save Changes", type="primary"):
            try:
                command = ProductCatalogCommand(
                    **{**command.__dict__, "price_cents": _parse_price_cents(price_text)}
                )
                result = (
                    service.create_product(command)
                    if not product
                    else service.update_product(product.id, command)
                )
                st.success("Product saved.")
                _set_mode("EDIT", result.product.id)
                st.rerun()
            except (ProductCatalogError, ValueError) as error:
                _render_validation_error(error)

        can_activate = not product or product.status in {
            ProductStatus.DRAFT,
            ProductStatus.DISABLED,
        }
        if can_activate and activate_col.button("Save and Activate"):
            try:
                command = ProductCatalogCommand(
                    **{**command.__dict__, "price_cents": _parse_price_cents(price_text)}
                )
                if not product:
                    result = service.create_product(command, activate=True)
                    product_id = result.product.id
                else:
                    service.update_product(product.id, command, activate=True)
                    product_id = product.id
                st.success("Product activated.")
                _set_mode("EDIT", product_id)
                st.rerun()
            except (ProductCatalogError, ValueError) as error:
                _render_validation_error(error)

    if product and not read_only:
        st.divider()
        lifecycle_col, danger_col = st.columns(2)
        with lifecycle_col:
            st.markdown("### Lifecycle")
            transitions = ProductCatalogService.TRANSITIONS[product.status]
            for target in transitions:
                if target == ProductStatus.ACTIVE:
                    continue
                if st.button(f"Set status to {target.value}", key=f"transition_{target.value}"):
                    try:
                        service.transition_status(
                            product.id,
                            creator_profile_id,
                            target,
                        )
                        st.success(f"Product status changed to {target.value}.")
                        st.rerun()
                    except ProductCatalogError as error:
                        _render_validation_error(error)

        with danger_col:
            st.markdown("### Danger Zone")
            st.warning(
                "Delete Product archives the product locally, removes its "
                "ProductAsset links, and archives the attached local assets. "
                "Files on disk are not deleted."
            )
            fanvue_status, _ = _product_fanvue_status(
                product,
                initial_ordered_assets,
            )
            if fanvue_status != "Not uploaded to Fanvue":
                st.warning(
                    "This removes the product from local catalog only. "
                    "Provider Vault cleanup is not included."
                )
            confirmation_text = (
                "I understand this will remove this product from the catalog."
            )
            confirmed = st.checkbox(
                confirmation_text,
                key=f"delete_confirm_{product.id}",
            )
            if st.button(
                "Delete Product",
                disabled=not confirmed,
                key=f"delete_product_{product.id}",
            ):
                try:
                    result = service.delete_product(
                        product.id,
                        creator_profile_id,
                    )
                    st.success(
                        "Product removed from local catalog. "
                        f"Archived {result.assets_archived} asset(s) and "
                        f"removed {result.product_asset_links_deleted} "
                        "product-asset link(s)."
                    )
                    if result.fanvue_cleanup_required:
                        st.warning(
                            "Provider Vault cleanup was not performed in this phase."
                        )
                    _set_mode("LIST")
                    st.rerun()
                except ProductCatalogError as error:
                    _render_validation_error(error)


def render_product_catalog(
    *,
    fanvue_account_id: int,
    creator_profile: dict,
) -> None:
    st.title("Product Catalog")
    creator_profile_id = creator_profile.get("id") if creator_profile else None
    if not fanvue_account_id or not creator_profile_id:
        st.error(
            "An active publishing account and Creator Profile are required."
        )
        return

    st.caption(
        f"Publishing Account {fanvue_account_id} · Creator: "
        f"{creator_profile.get('display_name') or creator_profile.get('persona_name')}"
    )
    previous_scope = st.session_state.get("product_catalog_creator_profile_id")
    if previous_scope != creator_profile_id:
        st.session_state["product_catalog_creator_profile_id"] = creator_profile_id
        _set_mode("LIST")
    mode = st.session_state.get("product_catalog_mode", "LIST")
    service = ProductCatalogService()
    try:
        if mode == "LIST":
            _render_catalog_list(service, creator_profile_id)
        else:
            _render_editor(service, fanvue_account_id, creator_profile_id, mode)
    except ProductCatalogError as error:
        _render_validation_error(error)
