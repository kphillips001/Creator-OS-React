"""Reusable Asset Library browsing and selection components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from app.models.asset_library import (
    AssetLibraryFilter,
    AssetLibraryItem,
    AssetLibraryResult,
)
from app.services.asset_library_service import AssetLibraryService


@dataclass(frozen=True)
class AssetSelectionModel:
    selected_asset_ids: tuple[int, ...]
    ordered_asset_ids: tuple[int, ...]
    items_by_id: dict[int, AssetLibraryItem]


def build_asset_picker_filter(
    *,
    search: str | None,
    media_type: str,
    classification: str | None,
    eligible_only: bool = True,
    limit: int = 500,
) -> AssetLibraryFilter:
    return AssetLibraryFilter(
        search=(search or "").strip() or None,
        media_type=None if media_type == "all" else media_type,
        classification=(classification or "").strip() or None,
        eligible_only=eligible_only,
        limit=limit,
    )


def merge_asset_items(
    result: AssetLibraryResult,
    selected_items: tuple[AssetLibraryItem, ...],
) -> dict[int, AssetLibraryItem]:
    items_by_id = {item.asset_id: item for item in result.items}
    items_by_id.update({item.asset_id: item for item in selected_items})
    return items_by_id


def ordered_selection(
    *,
    current_order: tuple[int, ...] | list[int],
    selected_asset_ids: tuple[int, ...] | list[int],
) -> tuple[int, ...]:
    selected = tuple(int(asset_id) for asset_id in selected_asset_ids)
    ordered = [asset_id for asset_id in current_order if asset_id in selected]
    ordered.extend(asset_id for asset_id in selected if asset_id not in ordered)
    return tuple(ordered)


def render_asset_thumbnail(
    item: AssetLibraryItem | None,
    *,
    caption: str | None = None,
) -> None:
    if item and item.preview_path:
        st.image(item.preview_path, caption=caption, use_container_width=True)
        return
    if item:
        st.caption(caption or "Preview unavailable")
        st.caption(f"#{item.asset_id} | {item.media_type}")
    else:
        st.caption("No asset")


def render_asset_card(item: AssetLibraryItem) -> None:
    with st.container():
        render_asset_thumbnail(item, caption=f"Asset #{item.asset_id}")
        st.write(f"**{item.file_name or f'Asset {item.asset_id}'}**")
        st.caption(
            f"{item.media_type} | {item.classification or '-'} | "
            f"{item.status or '-'}"
        )
        c1, c2 = st.columns(2)
        c1.metric("Products", item.relationship.product_count)
        c2.metric("Experiences", item.relationship.experience_count)
        st.caption(f"Publishing: {item.publishing.status}")


def render_asset_grid(
    items: tuple[AssetLibraryItem, ...],
    *,
    columns: int = 3,
) -> None:
    for index in range(0, len(items), columns):
        grid_columns = st.columns(columns)
        for column, item in zip(grid_columns, items[index:index + columns]):
            with column:
                render_asset_card(item)


def render_asset_picker(
    *,
    asset_library_service: AssetLibraryService,
    picker_key: str,
    initial_asset_ids: tuple[int, ...],
    render_action: Callable[[int, AssetLibraryItem], None] | None = None,
) -> AssetSelectionModel:
    order_key = f"{picker_key}_asset_order"
    if order_key not in st.session_state:
        st.session_state[order_key] = list(initial_asset_ids)

    f1, f2, f3 = st.columns(3)
    search = f1.text_input("Asset search", key=f"{picker_key}_search")
    media_type = f2.selectbox(
        "Media type",
        ["all", "image", "video"],
        key=f"{picker_key}_media_type",
    )
    classification = f3.text_input(
        "Classification",
        key=f"{picker_key}_classification",
    )

    filters = build_asset_picker_filter(
        search=search,
        media_type=media_type,
        classification=classification,
        eligible_only=True,
    )
    result = asset_library_service.search_assets(filters)
    current_order = tuple(st.session_state[order_key])
    current_items = asset_library_service.get_asset_items(current_order)
    items_by_id = merge_asset_items(result, current_items)
    options = list(items_by_id)
    selected = st.multiselect(
        "Assigned assets",
        options=options,
        default=list(current_order),
        format_func=lambda asset_id: _asset_option_label(items_by_id[asset_id]),
        key=f"{picker_key}_asset_picker",
    )
    ordered = ordered_selection(
        current_order=current_order,
        selected_asset_ids=tuple(selected),
    )
    st.session_state[order_key] = list(ordered)

    st.caption("Use the controls below to define delivery order.")
    for position, asset_id in enumerate(ordered):
        item = items_by_id[asset_id]
        preview_col, detail_col, action_col = st.columns([1, 3, 1])
        with preview_col:
            render_asset_thumbnail(item, caption=f"{position + 1}. Asset")
        with detail_col:
            st.write(
                f"**{position + 1}. {item.file_name or f'Asset {item.asset_id}'}**"
            )
            st.caption(
                f"Publishing: {item.publishing.status} | "
                f"{item.publishing.detail or '-'}"
            )
            st.caption(
                f"Asset #{item.asset_id} | {item.media_type} | "
                f"{item.classification or '-'} | {item.status or '-'}"
            )
        with action_col:
            up, down = st.columns(2)
            if up.button(
                "↑",
                key=f"{picker_key}_asset_up_{asset_id}",
                disabled=position == 0,
            ):
                mutable = list(ordered)
                mutable[position - 1], mutable[position] = (
                    mutable[position],
                    mutable[position - 1],
                )
                st.session_state[order_key] = mutable
                st.rerun()
            if down.button(
                "↓",
                key=f"{picker_key}_asset_down_{asset_id}",
                disabled=position == len(ordered) - 1,
            ):
                mutable = list(ordered)
                mutable[position + 1], mutable[position] = (
                    mutable[position],
                    mutable[position + 1],
                )
                st.session_state[order_key] = mutable
                st.rerun()
            if render_action:
                render_action(asset_id, item)

    return AssetSelectionModel(
        selected_asset_ids=tuple(selected),
        ordered_asset_ids=ordered,
        items_by_id=items_by_id,
    )


def _asset_option_label(item: AssetLibraryItem) -> str:
    return (
        f"#{item.asset_id} - {item.file_name or f'Asset {item.asset_id}'} "
        f"({item.media_type})"
    )
