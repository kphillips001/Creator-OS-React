"""Provider purchase aggregates for one creator and Fanvue buyer."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class CustomerCommerceProfileState(str, Enum):
    UNKNOWN = "UNKNOWN"
    PROSPECT = "PROSPECT"
    LEAD = "LEAD"
    FIRST_PURCHASE = "FIRST_PURCHASE"
    REPEAT_BUYER = "REPEAT_BUYER"
    VIP = "VIP"
    HIGH_VALUE = "HIGH_VALUE"
    INACTIVE = "INACTIVE"
    PRE_LAUNCH_INTEREST = "PRE_LAUNCH_INTEREST"


@dataclass(frozen=True)
class CustomerCommerceProfile:
    customer_commerce_profile_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    external_fanvue_user_uuid: UUID
    telegram_identity_mapping_id: int | None
    telegram_user_id: int | None
    display_name: str | None
    handle: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    first_purchase_at: datetime | None
    last_purchase_at: datetime | None
    lifetime_gross_minor: int
    lifetime_net_minor: int
    purchase_count: int
    average_order_value_minor: int
    largest_purchase_minor: int
    last_transaction_order_id: str | None
    last_payment_status: str | None
    last_purchase_source: str | None
    last_synced_at: datetime | None
    profile_state: CustomerCommerceProfileState
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CustomerCommerceStatistics:
    profile_count: int
    buyer_count: int
    lifetime_gross_minor: int
    lifetime_net_minor: int
    purchase_count: int
    average_order_value_minor: int
    largest_purchase_minor: int
