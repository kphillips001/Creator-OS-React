"""Durable lease returned by atomic proactive contact authorization."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CustomerContactReservation:
    reservation_id: UUID
    fanvue_account_id: int
    customer_scope: str
    contact_purpose: str
    state: str
    owner_id: str
    reserved_at: datetime
    lease_expires_at: datetime
    correlation_id: str | None = None
    delivery_reference: str | None = None
