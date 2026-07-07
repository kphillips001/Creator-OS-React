"""Customer Workspace dashboard page.

C.3.5 establishes the presentation shell only. CustomerService is the sole
customer data source for this page; timeline and intelligence widgets arrive in
later C.3 phases.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.models.customer import Customer
from app.services.customer_service import CustomerService


PROVIDER_OPTIONS = ("internal", "fanvue", "telegram")
CUSTOMER_WORKSPACE_REGIONS = (
    "Timeline",
    "DecisionEngine Inspector",
    "Commerce",
    "Experience Progression",
)


def build_customer_lookup(
    *,
    search_text: str | None,
    provider: str,
    provider_customer_id: str | None,
    provider_account_id: str | None,
) -> dict[str, Any]:
    """Convert UI search controls into a CustomerService lookup."""

    normalized_provider = (provider or "internal").strip().lower()
    search = (search_text or "").strip()
    provider_id = (provider_customer_id or "").strip()
    account_id = (provider_account_id or "").strip()

    if normalized_provider == "internal":
        return {"customer_id": search or None}

    return {
        "provider": normalized_provider,
        "provider_customer_id": provider_id or search or None,
        "provider_account_id": account_id or None,
    }


def _get_customer(
    service: CustomerService,
    lookup: dict[str, Any],
) -> Customer | None:
    customer_id = lookup.pop("customer_id", None)
    provider_customer_id = lookup.get("provider_customer_id")
    if customer_id is None and provider_customer_id is None:
        return None
    return service.get_customer(customer_id, **lookup)


def _render_search() -> dict[str, Any]:
    st.subheader("Customer Search")
    columns = st.columns((2, 1, 1))
    with columns[0]:
        search_text = st.text_input(
            "Customer ID or provider customer ID",
            key="customer_workspace_search_text",
            placeholder="Example: 7:42",
        )
    with columns[1]:
        provider = st.selectbox(
            "Identity",
            PROVIDER_OPTIONS,
            key="customer_workspace_provider",
        )
    with columns[2]:
        provider_account_id = st.text_input(
            "Provider Account",
            key="customer_workspace_provider_account_id",
            placeholder="Optional",
        )

    provider_customer_id = None
    if provider != "internal":
        provider_customer_id = st.text_input(
            "Provider Customer ID",
            key="customer_workspace_provider_customer_id",
            placeholder="Defaults to search text",
        )

    return build_customer_lookup(
        search_text=search_text,
        provider=provider,
        provider_customer_id=provider_customer_id,
        provider_account_id=provider_account_id,
    )


def _render_customer_list(customer: Customer | None) -> None:
    st.subheader("Customer List")
    if customer is None:
        st.caption("Search for a customer to populate this workspace.")
        return

    st.write(customer.display_name or customer.customer_id)
    st.caption(customer.customer_id)


def _render_profile(customer: Customer | None) -> None:
    st.subheader("Customer Profile")
    if customer is None:
        st.info("No customer selected.")
        return

    st.markdown(f"### {customer.display_name or customer.customer_id}")
    st.caption(f"Customer ID: {customer.customer_id}")

    identities = customer.provider_identities
    if identities:
        st.markdown("#### Provider Identities")
        for identity in identities:
            st.write(
                f"{identity.provider}: {identity.provider_customer_id}"
            )
            if identity.username:
                st.caption(identity.username)


def _render_summary(summary: dict[str, Any] | None) -> None:
    st.subheader("Summary")
    if summary is None:
        st.caption("Customer summary unavailable.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Relationship", summary["relationship_status"])
    c2.metric("Messages", summary["message_count"])
    c3.metric("Owned Products", summary["owned_product_count"])
    c4.metric("Offers", summary["offer_count"])

    st.caption(
        " | ".join(
            (
                f"Spend: {summary['total_spend_cents']} cents",
                f"Entitlements: {summary['entitlement_count']}",
                f"Providers: {summary['provider_count']}",
            )
        )
    )


def _format_timeline_timestamp(value: Any) -> str:
    if value is None:
        return "Future-ready"
    return str(value)


def _render_timeline(events: list[dict[str, Any]]) -> None:
    st.markdown("### Timeline")
    if not events:
        st.caption("Search for a customer to populate the timeline.")
        return

    for event in events:
        with st.container():
            st.caption(_format_timeline_timestamp(event.get("timestamp")))
            st.write(event["title"])
            st.caption(event["detail"])
            if event.get("future_ready"):
                st.info("Placeholder: data source not yet exposed.")


def _render_tuple_values(label: str, values: tuple[str, ...]) -> None:
    st.write(f"{label}: {', '.join(values) if values else '-'}")


def _render_decision_inspector(inspector: dict[str, Any] | None) -> None:
    st.markdown("### DecisionEngine Inspector")
    if inspector is None:
        st.caption("Search for a customer to populate the inspector.")
        return

    current = inspector["current_recommendation"]
    recent = inspector["recent_recommendations"]
    progression = inspector["customer_progression"]
    conversation = inspector["conversation_summary"]
    memory = inspector["memory_summary"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last Offer", current["last_offer_id"] or "-")
    c2.metric("Offers", recent["offer_count"])
    c3.metric("Messages", conversation["message_count"])
    c4.metric("Entitlements", memory["entitlement_count"])

    with st.expander("Recommendation Context", expanded=True):
        st.write(f"Last kind: {current['last_offer_kind'] or '-'}")
        st.write(f"Last activity: {inspector['last_decision_activity'] or '-'}")
        _render_tuple_values("Recent products", current["recent_product_ids"])
        _render_tuple_values("Seen offers", recent["seen_offer_ids"])
        _render_tuple_values("Preferred tags", recent["preferred_tags"])
        _render_tuple_values("Preferred themes", recent["preferred_themes"])

    with st.expander("Progression and Conversation"):
        st.write(
            "Current experience: "
            f"{progression['current_experience_id'] or '-'}"
        )
        st.write(f"Active session: {'Yes' if progression['active_session'] else 'No'}")
        st.write(f"Session step: {progression['session_step']}")
        st.write(f"Conversation mode: {conversation['current_mode'] or '-'}")
        st.write(f"Inbound messages: {conversation['inbound_message_count']}")
        st.write(f"Outbound messages: {conversation['outbound_message_count']}")

    with st.expander("Memory Summary"):
        st.write(f"Relationship: {memory['relationship_status']}")
        st.write(f"Value tier: {memory['value_tier'] or '-'}")
        st.write(f"Buyer tier: {memory['buyer_tier'] or '-'}")
        st.write(f"Spend: {memory['total_spend_cents']} cents")
        st.write(f"Purchases: {memory['purchase_count']}")
        st.write(f"Owned products: {memory['owned_product_count']}")

    with st.expander("Future Decision Data"):
        for label in ("offer_candidates", "delivery_permissions"):
            section = inspector[label]
            st.write(label.replace("_", " ").title())
            st.info(section["message"])


def _render_customer_commerce(commerce: dict[str, Any] | None) -> None:
    st.markdown("### Commerce")
    if commerce is None:
        st.caption("Search for a customer to populate commerce details.")
        return

    entitlements = commerce["entitlements"]
    purchase = commerce["purchase_summary"]
    value = commerce["customer_value"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Owned Products", entitlements["owned_product_count"])
    c2.metric("Entitlements", entitlements["count"])
    c3.metric("Purchases", purchase["purchase_count"])
    c4.metric("Spend", f"{purchase['total_spend_cents']} cents")

    with st.expander("Owned Commerce", expanded=True):
        _render_tuple_values("Products owned", commerce["products_owned"])
        _render_tuple_values("Products purchased", commerce["products_purchased"])
        _render_tuple_values(
            "Purchased experiences",
            commerce["purchased_experiences"],
        )
        st.write(f"Last purchase: {purchase['last_purchase_at'] or '-'}")

    with st.expander("Offer Outcomes"):
        acceptance = commerce["offer_acceptance"]
        rejection = commerce["offer_rejection"]
        st.write(f"Offers accepted: {acceptance['accepted_offer_count']}")
        st.write(f"Offers rejected: {rejection['rejected_offer_count']}")
        st.write(f"Total offers: {acceptance['offer_count']}")

    with st.expander("Telegram Conversation State"):
        state = commerce["telegram_conversation_state"]
        st.write(f"Current experience: {state['current_experience'] or '-'}")
        st.write(f"Current product: {state['current_product'] or '-'}")
        st.write(f"Current offer: {state['current_offer'] or '-'}")
        st.write(f"Delivery type: {state['delivery_type'] or '-'}")
        st.write(f"Conversation status: {state['conversation_status'] or '-'}")
        st.write(f"Commerce progress: {state['commerce_progress']}")
        st.write(f"Next action: {state['next_recommended_action']}")

    with st.expander("Delivery Decision"):
        decision = commerce["delivery_decision"]
        permission = decision["delivery_permission"]
        last_delivery = decision["last_delivery"]
        st.write(
            "Current delivery decision: "
            f"{decision['current_delivery_decision'] or '-'}"
        )
        st.write(f"Delivery type: {decision['delivery_type'] or '-'}")
        st.write(f"Recommended product: {decision['recommended_product'] or '-'}")
        st.write(f"Delivery permission: {permission.get('allowed')}")
        st.write(f"FREE vs PAID: {decision['free_vs_paid']}")
        st.write(f"Delivery reason: {decision['delivery_reason'] or '-'}")
        st.write(f"Last delivery: {last_delivery.get('delivery_method') or '-'}")
        st.write(f"Last FREE asset: {last_delivery.get('last_free_asset') or '-'}")
        st.write(
            "Last PAID media link: "
            f"{last_delivery.get('last_paid_media_link') or '-'}"
        )
        st.write(f"Blocking reason: {last_delivery.get('blocking_reason') or '-'}")
        st.write(f"Next suggested action: {decision['next_suggested_action']}")

    with st.expander("Commerce Memory"):
        memory = commerce["commerce_memory"]
        spending = memory["customer_spending_summary"]
        engagement = memory["customer_engagement_summary"]
        _render_tuple_values("Purchased products", memory["purchased_products"])
        _render_tuple_values("FREE assets delivered", memory["free_assets_delivered"])
        _render_tuple_values(
            "PAID media links delivered",
            memory["paid_media_links_delivered"],
        )
        st.write(f"Current commerce journey: {memory['current_commerce_journey']}")
        st.write(f"Purchase count: {spending['purchase_count']}")
        st.write(f"Total spend: {spending['total_spend_cents']} cents")
        st.write(f"Messages: {engagement['message_count']}")
        st.write(f"Offers: {engagement['offer_count']}")
        st.write(
            "Recommended next commerce action: "
            f"{memory['recommended_next_commerce_action']}"
        )

    with st.expander("Customer Value"):
        st.write(f"Relationship: {value['relationship_status']}")
        st.write(f"Value tier: {value['value_tier'] or '-'}")
        st.write(f"Buyer tier: {value['buyer_tier'] or '-'}")
        st.write(f"Subscriber: {'Yes' if value['is_subscriber'] else 'No'}")
        st.write(f"Follower: {'Yes' if value['is_follower'] else 'No'}")

    with st.expander("Future Commerce Data"):
        for label in ("products_offered", "media_links"):
            section = commerce[label]
            st.write(label.replace("_", " ").title())
            st.info(section["message"])


def _render_experience_progression(
    progression: dict[str, Any] | None,
) -> None:
    st.markdown("### Experience Progression")
    if progression is None:
        st.caption("Search for a customer to populate Experience progression.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Progress", f"{progression['progress_percentage']}%")
    c2.metric("State", progression["current_experience_state"])
    c3.metric("Next Action", progression["next_recommended_experience_action"])

    with st.expander("Current Experience", expanded=True):
        st.write(f"Current experience: {progression['current_experience'] or '-'}")
        st.write(f"Current product: {progression['current_product'] or '-'}")
        st.write(
            "Current story position: "
            f"{progression['current_story_position'] or '-'}"
        )
        st.write(
            "Current asset position: "
            f"{progression['current_asset_position'] or '-'}"
        )

    with st.expander("Last Progression Event"):
        event = progression["last_progression_event"]
        st.write(f"Source: {event.get('source') or '-'}")
        st.write(f"Experience: {event.get('experience_id') or '-'}")
        st.write(f"Session step: {event.get('session_step') or '-'}")


def _render_navigation_regions() -> None:
    st.subheader("Navigation")
    columns = st.columns(4)
    for index, region in enumerate(CUSTOMER_WORKSPACE_REGIONS):
        with columns[index % len(columns)]:
            st.button(
                region,
                key=f"customer_workspace_region_{region}",
                disabled=True,
                use_container_width=True,
            )


def _render_placeholders() -> None:
    st.markdown("### Workspace Regions")
    for region in CUSTOMER_WORKSPACE_REGIONS:
        if region in (
            "Timeline",
            "DecisionEngine Inspector",
            "Commerce",
            "Experience Progression",
        ):
            continue
        with st.expander(region, expanded=False):
            st.caption(f"{region} will be implemented in a later C.3 phase.")


def render_customer_workspace(
    *,
    customer_service: CustomerService | None = None,
) -> None:
    service = customer_service or CustomerService()

    st.title("Customer Workspace")
    st.caption("Primary customer information surface for Creator OS.")

    lookup = _render_search()
    customer = _get_customer(service, dict(lookup))
    summary = None
    timeline_events: list[dict[str, Any]] = []
    decision_inspector = None
    commerce_summary = None
    experience_progression = None
    if customer is not None:
        summary = service.get_customer_summary(customer.customer_id)
        timeline_events = service.get_customer_timeline(customer.customer_id)
        decision_inspector = service.get_customer_decision_inspector(
            customer.customer_id
        )
        commerce_summary = service.get_customer_commerce_summary(
            customer.customer_id
        )
        experience_progression = (
            service.get_customer_experience_progression_summary(
                customer.customer_id
            )
        )

    list_col, profile_col = st.columns((1, 2))
    with list_col:
        _render_customer_list(customer)
        _render_navigation_regions()
    with profile_col:
        _render_profile(customer)
        _render_summary(summary)

    _render_timeline(timeline_events)
    _render_decision_inspector(decision_inspector)
    _render_customer_commerce(commerce_summary)
    _render_experience_progression(experience_progression)
    _render_placeholders()
