"""Streamlit Product Review workspace."""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

import streamlit as st

from app.models.product_review import ProductReview, ProductReviewSection
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_review_service import ProductReviewService


def _creator_profile_id(creator_profile: dict | None) -> int | None:
    if not creator_profile:
        return None
    value = creator_profile.get("id") or creator_profile.get("creator_profile_id")
    if value is None:
        return None
    return int(value)


def _format_money(cents: int | None, currency: str = "USD") -> str:
    if cents is None:
        return "Not set"
    return f"{currency} {cents / 100:.2f}"


def _status_badge(label: str, value: str | None) -> None:
    st.caption(f"{label}: {value or 'Unavailable'}")


def open_product_catalog_editor(product_id: str) -> None:
    """Navigate to the existing Product Catalog editor for a Product."""

    st.session_state["product_catalog_mode"] = "EDIT"
    st.session_state["product_catalog_selected_product_id"] = product_id
    st.session_state.dashboard_page = "Product Catalog"


def reset_commerce_override(
    product_id: str,
    creator_profile_id: int,
    field: str,
    *,
    product_catalog_service: ProductCatalogService | None = None,
) -> None:
    """Delegate commerce reset persistence to ProductCatalogService."""

    service = product_catalog_service or ProductCatalogService()
    service.reset_product_commerce_to_ai(
        UUID(product_id),
        creator_profile_id,
        fields=(field,),
    )


def approve_product_review(
    product_id: str,
    creator_profile_id: int,
    *,
    notes: str | None = None,
    product_catalog_service: ProductCatalogService | None = None,
) -> None:
    """Delegate Product approval persistence to ProductCatalogService."""

    service = product_catalog_service or ProductCatalogService()
    service.approve_product(
        UUID(product_id),
        creator_profile_id,
        notes=notes,
    )


def mark_product_review_needs_review(
    product_id: str,
    creator_profile_id: int,
    *,
    notes: str | None = None,
    product_catalog_service: ProductCatalogService | None = None,
) -> None:
    """Delegate Product review-state persistence to ProductCatalogService."""

    service = product_catalog_service or ProductCatalogService()
    service.mark_product_needs_review(
        UUID(product_id),
        creator_profile_id,
        notes=notes,
    )


def reject_product_review(
    product_id: str,
    creator_profile_id: int,
    *,
    notes: str | None = None,
    product_catalog_service: ProductCatalogService | None = None,
) -> None:
    """Delegate Product rejection persistence to ProductCatalogService."""

    service = product_catalog_service or ProductCatalogService()
    service.reject_product(
        UUID(product_id),
        creator_profile_id,
        notes=notes,
    )


def _section_data_rows(section: ProductReviewSection, keys: Iterable[str]) -> None:
    data = section.data or {}
    for key in keys:
        value = data.get(key)
        if value in (None, "", (), []):
            continue
        label = key.replace("_", " ").title()
        st.caption(f"{label}: {value}")


def _matches_search(review: ProductReview, search: str) -> bool:
    if not search:
        return True
    haystack = " ".join(
        str(value or "")
        for value in (
            review.product_name,
            review.description,
            review.product_type,
            review.delivery_type,
            review.review_status,
            review.priority,
            review.experience.summary,
            review.commerce.summary,
            review.publishing.summary,
        )
    ).lower()
    return search.lower() in haystack


def _filter_reviews(
    reviews: tuple[ProductReview, ...],
    *,
    search: str,
    status: str,
    priority: str,
    approval_status: str,
    delivery_type: str,
    publishing_status: str,
) -> tuple[ProductReview, ...]:
    filtered = []
    for review in reviews:
        if not _matches_search(review, search):
            continue
        if status != "All" and review.review_status != status:
            continue
        if priority != "All" and review.priority != priority:
            continue
        if approval_status != "All" and review.approval_status != approval_status:
            continue
        if delivery_type != "All" and review.delivery_type != delivery_type:
            continue
        if (
            publishing_status != "All"
            and review.publishing.status != publishing_status
        ):
            continue
        filtered.append(review)
    return tuple(filtered)


def _render_summary(reviews: tuple[ProductReview, ...]) -> None:
    total = len(reviews)
    needs_attention = sum(
        1 for review in reviews if review.review_status == "Needs Attention"
    )
    draft_review = sum(
        1 for review in reviews if review.review_status == "Draft Review"
    )
    ready = sum(
        1 for review in reviews if review.review_status == "Ready To Publish"
    )
    approved = sum(
        1
        for review in reviews
        if review.approval_status in {"APPROVED", "READY_TO_PUBLISH"}
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reviews", str(total))
    c2.metric("Needs Attention", str(needs_attention))
    c3.metric("Draft Review", str(draft_review))
    c4.metric("Approved / Ready", f"{approved} / {ready}")


def _render_filters(reviews: tuple[ProductReview, ...]) -> dict[str, str]:
    statuses = sorted({review.review_status for review in reviews if review.review_status})
    priorities = sorted({review.priority for review in reviews if review.priority})
    delivery_types = sorted(
        {review.delivery_type for review in reviews if review.delivery_type}
    )
    approval_statuses = sorted(
        {review.approval_status for review in reviews if review.approval_status}
    )
    publishing_statuses = sorted(
        {review.publishing.status for review in reviews if review.publishing.status}
    )

    search = st.text_input(
        "Search Products",
        key="product_review_search",
        placeholder="Search by product, experience, delivery, or readiness",
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    return {
        "search": search,
        "status": c1.selectbox(
            "Review Status",
            ["All"] + statuses,
            key="product_review_status_filter",
        ),
        "priority": c2.selectbox(
            "Priority",
            ["All"] + priorities,
            key="product_review_priority_filter",
        ),
        "approval_status": c3.selectbox(
            "Approval",
            ["All"] + approval_statuses,
            key="product_review_approval_filter",
        ),
        "delivery_type": c4.selectbox(
            "Delivery Type",
            ["All"] + delivery_types,
            key="product_review_delivery_filter",
        ),
        "publishing_status": c5.selectbox(
            "Publishing Readiness",
            ["All"] + publishing_statuses,
            key="product_review_publishing_filter",
        ),
    }


def _render_review_card(review: ProductReview) -> None:
    with st.container(border=True):
        header, action = st.columns([4, 1])
        with header:
            st.subheader(review.product_name)
            if review.description:
                st.caption(review.description)
        with action:
            if st.button(
                "Edit in Catalog",
                key=f"product_review_edit_{review.product_id}",
                use_container_width=True,
            ):
                open_product_catalog_editor(review.product_id)
                st.rerun()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Type", review.product_type or "Unknown")
        c2.metric("Delivery", review.delivery_type or "Unknown")
        c3.metric("Price", _format_money(review.price_cents, review.currency))
        c4.metric("Priority", review.priority.title())
        c5.metric("Origin", review.product_origin)

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            _status_badge("Review Status", review.review_status)
        with b2:
            _status_badge("Approval", review.approval_status)
        with b3:
            _status_badge("Publishing", review.publishing.status)
        with b4:
            _status_badge("Product Status", review.product_status)
        if review.approved_at or review.last_reviewed_at:
            st.caption(
                " | ".join(
                    value
                    for value in (
                        f"Approved: {review.approved_at}" if review.approved_at else "",
                        (
                            f"Last reviewed: {review.last_reviewed_at}"
                            if review.last_reviewed_at
                            else ""
                        ),
                    )
                    if value
                )
            )
        if review.review_notes:
            st.caption(f"Review notes: {review.review_notes}")

        exp_col, commerce_col, publishing_col = st.columns(3)
        with exp_col:
            st.markdown("**Experience**")
            st.write(review.experience.summary or "No Experience summary available.")
            _section_data_rows(
                review.experience,
                (
                    "experience_type",
                    "name",
                    "themes",
                    "keywords",
                    "mood",
                    "relationship_source",
                ),
            )
        with commerce_col:
            st.markdown("**Commerce**")
            st.write(review.commerce.summary or "No Commerce recommendation available.")
            _section_data_rows(
                review.commerce,
                (
                    "suggested_price_cents",
                    "pricing_rule",
                    "confidence",
                    "suggested_keywords",
                ),
            )
        with publishing_col:
            st.markdown("**Publishing**")
            st.write(review.publishing.summary or "Readiness unavailable.")
            _section_data_rows(
                review.publishing,
                (
                    "status",
                    "detail",
                    "projection_owner",
                ),
            )

        with st.expander("AI rationale", expanded=False):
            st.write(review.ai_rationale.summary or "No AI rationale available.")
            if review.ai_rationale.evidence:
                st.caption("Evidence")
                for item in review.ai_rationale.evidence:
                    st.write(dict(item))
            if review.warnings:
                st.warning(", ".join(review.warnings))

        _render_commerce_overrides(review)
        _render_approval_actions(review)


def _render_approval_actions(review: ProductReview) -> None:
    if not review.creator_profile_id:
        return
    with st.expander("Approval", expanded=review.approval_status == "NEEDS_REVIEW"):
        notes = st.text_area(
            "Review Notes",
            value=review.review_notes or "",
            key=f"product_review_notes_{review.product_id}",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(
                "Approve Product",
                key=f"product_review_approve_{review.product_id}",
                use_container_width=True,
            ):
                try:
                    approve_product_review(
                        review.product_id,
                        review.creator_profile_id,
                        notes=notes,
                    )
                except Exception as error:
                    st.error(f"Approval failed: {error}")
                else:
                    st.success("Product approved.")
                    st.rerun()
        with c2:
            if st.button(
                "Mark Needs Review",
                key=f"product_review_needs_review_{review.product_id}",
                use_container_width=True,
            ):
                try:
                    mark_product_review_needs_review(
                        review.product_id,
                        review.creator_profile_id,
                        notes=notes,
                    )
                except Exception as error:
                    st.error(f"Review update failed: {error}")
                else:
                    st.success("Product marked as needing review.")
                    st.rerun()
        with c3:
            if st.button(
                "Reject Product",
                key=f"product_review_reject_{review.product_id}",
                use_container_width=True,
            ):
                try:
                    reject_product_review(
                        review.product_id,
                        review.creator_profile_id,
                        notes=notes,
                    )
                except Exception as error:
                    st.error(f"Rejection failed: {error}")
                else:
                    st.success("Product rejected.")
                    st.rerun()


def _render_commerce_overrides(review: ProductReview) -> None:
    fields = dict((review.commerce_overrides.data or {}).get("fields") or {})
    if not fields:
        return
    with st.expander("Commerce overrides", expanded=bool(review.commerce_overrides.warnings)):
        st.caption(review.commerce_overrides.summary or "No commerce override data.")
        for field_name, values in fields.items():
            label = values.get("label") or field_name.replace("_", " ").title()
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
            c1.write(label)
            c2.caption(f"AI: {values.get('ai')}")
            c3.caption(f"Current: {values.get('current')}")
            overridden = bool(values.get("overridden"))
            c4.caption("Override: Yes" if overridden else "Override: No")
            if (
                overridden
                and field_name in {"price", "delivery_type", "product_type"}
                and review.creator_profile_id
            ):
                if st.button(
                    f"Reset {label}",
                    key=f"product_review_reset_{review.product_id}_{field_name}",
                    use_container_width=True,
                ):
                    try:
                        reset_commerce_override(
                            review.product_id,
                            review.creator_profile_id,
                            field_name,
                        )
                    except Exception as error:
                        st.error(f"Reset failed: {error}")
                    else:
                        st.success(f"{label} reset to AI recommendation.")
                        st.rerun()


def render_product_review(
    *,
    creator_profile: dict | None = None,
    product_review_service: ProductReviewService | None = None,
) -> None:
    st.title("Product Review")
    st.caption("Review AI-generated Products before continuing to editing.")

    creator_profile_id = _creator_profile_id(creator_profile)
    if not creator_profile_id:
        st.warning("A Creator Profile is required to load Product Review.")
        return

    service = product_review_service or ProductReviewService()
    try:
        summary = service.build_summary(creator_profile_id=creator_profile_id)
    except Exception as error:
        st.error(f"Product Review is unavailable: {error}")
        return

    reviews = tuple(summary.reviews)
    _render_summary(reviews)
    st.divider()

    filters = _render_filters(reviews)
    filtered = _filter_reviews(reviews, **filters)
    st.caption(f"Showing {len(filtered)} of {len(reviews)} Product Reviews")

    if not filtered:
        st.info("No Product Reviews match the current filters.")
        return

    for review in filtered:
        _render_review_card(review)
