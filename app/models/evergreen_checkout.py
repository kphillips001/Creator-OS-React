"""Provider-neutral contracts for stable checkout aliases.

The canonical commerce adapter owns transactions, identity, prices and grants.
This module grants no authority to sell, charge or deliver anything.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class CheckoutUnavailable(RuntimeError):
    PUBLIC_MESSAGE = "This checkout link is unavailable."

    def __init__(self, reason_code: str):
        super().__init__(self.PUBLIC_MESSAGE)
        self.reason_code = reason_code


@dataclass(frozen=True)
class CheckoutBinding:
    tenant: str
    customer: str
    subject: str
    channel: str


@dataclass(frozen=True)
class CheckoutGrant:
    alias_id: UUID
    original_transaction_id: UUID
    binding: CheckoutBinding
    revoked: bool = False


@dataclass(frozen=True)
class CheckoutPrice:
    minor: int
    currency: str


@dataclass(frozen=True)
class CheckoutTransaction:
    transaction_id: UUID
    binding: CheckoutBinding
    offer_id: str
    status: str
    expires_at: datetime
    price: CheckoutPrice
    revoked: bool = False


@dataclass(frozen=True)
class CheckoutEligibility:
    # All checks are mandatory and deny by default, including on reuse.
    identity_valid: bool = False
    offer_available: bool = False
    product_available: bool = False
    publication_valid: bool = False
    purchase_allowed: bool = False
    commerce_allowed: bool = False
    runtime_supported: bool = False
    price_unambiguous: bool = False
    configured_price: CheckoutPrice | None = None


@dataclass(frozen=True)
class CheckoutResolution:
    destination: str
    original_transaction_id: UUID
    effective_transaction_id: UUID
    generation: int


class CheckoutAuthority(Protocol):
    """Required canonical adapter; there is deliberately no live default.

    All connection-taking methods MUST use the supplied transaction and must
    not commit it. lock_scope must share the canonical buyer/offer lock used by
    every other transaction creator and purchase/revocation writer. authenticate
    locks/rechecks the grant; validate locks authoritative eligibility records.
    No method may send a message, charge, or deliver a product.
    """

    def authenticate(self, alias: str, binding: CheckoutBinding, *, connection) -> CheckoutGrant: ...
    def lock_scope(self, grant: CheckoutGrant, *, connection) -> None: ...
    def load(self, transaction_id: UUID, *, connection) -> CheckoutTransaction: ...
    def validate(self, grant: CheckoutGrant, transaction: CheckoutTransaction, *, connection) -> CheckoutEligibility: ...
    def expire(self, transaction: CheckoutTransaction, *, now: datetime, connection) -> CheckoutTransaction: ...
    def create_successor(self, predecessor: CheckoutTransaction, *, transaction_id: UUID,
                         price: CheckoutPrice, expires_at: datetime,
                         idempotency_key: UUID, connection) -> CheckoutTransaction: ...
    def validate_destination(self, destination: str, transaction: CheckoutTransaction) -> bool: ...


class CheckoutRuntime(Protocol):
    """Reconcile checkout state only; never charge or deliver.

    A stable operation key survives crashes. Implementations must use provider
    idempotency or query-and-reconcile ambiguous requests; blind create retries
    are forbidden. If safety cannot be established, raise CheckoutUnavailable.
    """

    def reconcile(self, transaction: CheckoutTransaction, *, operation_key: UUID) -> str: ...
