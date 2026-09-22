"""Opt-in, provider-neutral stable checkout lifecycle. No live adapters."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from app.models.evergreen_checkout import (
    CheckoutAuthority, CheckoutRuntime, CheckoutResolution, CheckoutUnavailable,
)
from app.repositories.evergreen_checkout_repository import EvergreenCheckoutRepository


class EvergreenCheckoutService:
    ACTIVE = frozenset({"CREATED", "PRESENTED", "CLICKED"})

    def __init__(self, *, namespace: str, authority: CheckoutAuthority,
                 runtime: CheckoutRuntime, repository=None,
                 lifetime=timedelta(hours=72), clock=lambda: datetime.now(timezone.utc)):
        if not namespace.strip() or lifetime <= timedelta(0):
            raise ValueError("A namespace and positive canonical transaction lifetime are required.")
        self.namespace = namespace
        self.authority = authority
        self.runtime = runtime
        self.repository = repository or EvergreenCheckoutRepository()
        self.lifetime = lifetime
        self.clock = clock

    def resolve(self, alias, *, binding):
        # Authenticate before using any supplied input as a locking/storage key.
        try:
            with self.repository.connection_factory() as connection:
                grant = self.authority.authenticate(alias, binding, connection=connection)
                self._grant(grant, binding)
            try:
                return self._resolve_authenticated(alias, binding, grant)
            except CheckoutUnavailable as error:
                recover = getattr(self.runtime, "recover_expired", None)
                if error.reason_code != "PRIOR_RUNTIME_UNRESOLVED" or not callable(recover):
                    raise
                # The first resolution has released its SQL/session locks.
                # A canonical durable runtime may reconcile an ambiguous family
                # operation without creating another resource or successor.
                recover(grant, self.repository)
                return self._resolve_authenticated(alias, binding, grant)
        except CheckoutUnavailable:
            raise
        except Exception as error:
            # Never render DB/provider error text or bearer aliases publicly.
            raise CheckoutUnavailable("CHECKOUT_INTERNAL_FAILURE") from error

    def _resolve_authenticated(self, alias, binding, grant):
        effective = None
        generation = 0
        with self.repository.serialize(self.namespace, grant.original_transaction_id) as connection:
            try:
                with connection.transaction():
                    self.authority.lock_scope(grant, connection=connection)
                    current_grant = self.authority.authenticate(alias, binding, connection=connection)
                    if current_grant != grant:
                        raise CheckoutUnavailable("GRANT_CHANGED")
                    self._grant(current_grant, binding)
                    original = self._load(grant.original_transaction_id, connection)
                    self._transaction(original, grant, binding)
                    latest = self.repository.latest(connection, self.namespace, grant.original_transaction_id)
                    generation = int(latest["generation"]) if latest else 0
                    effective = self._load(latest["successor_id"], connection) if latest else original
                    self._transaction(effective, grant, binding)
                    if effective.offer_id != original.offer_id:
                        raise CheckoutUnavailable("OFFER_BINDING_MISMATCH")
                    if latest and original.status != "EXPIRED":
                        raise CheckoutUnavailable("LINEAGE_INVALID")
                    eligibility = self.authority.validate(grant, effective, connection=connection)
                    self._eligible(eligibility, effective)
                    now = self.clock()
                    self._aware(now)
                    self._aware(effective.expires_at)
                    expired = effective.expires_at <= now
                    if effective.status == "EXPIRED" and not expired:
                        raise CheckoutUnavailable("EXPIRY_INCONSISTENT")
                    if expired:
                        if latest and latest["runtime_state"] != "READY":
                            raise CheckoutUnavailable("PRIOR_RUNTIME_UNRESOLVED")
                        predecessor = effective
                        if predecessor.status != "EXPIRED":
                            predecessor = self.authority.expire(predecessor, now=now, connection=connection)
                            if predecessor != replace(effective, status="EXPIRED"):
                                raise CheckoutUnavailable("EXPIRY_NOT_RECORDED")
                        generation += 1
                        key = self._key(f"successor:{predecessor.transaction_id}")
                        effective = self.authority.create_successor(
                            predecessor, transaction_id=key,
                            price=eligibility.configured_price, expires_at=now + self.lifetime,
                            idempotency_key=key, connection=connection,
                        )
                        self._transaction(effective, grant, binding)
                        if (effective.transaction_id != key or effective.status not in self.ACTIVE
                                or effective.price != eligibility.configured_price
                                or effective.offer_id != predecessor.offer_id
                                or effective.expires_at != now + self.lifetime):
                            raise CheckoutUnavailable("SUCCESSOR_INVALID")
                        self.repository.append(
                            connection, namespace=self.namespace, grant=grant,
                            predecessor=predecessor, successor=effective,
                            generation=generation, now=now,
                        )
                        if (self._load(predecessor.transaction_id, connection) != predecessor
                                or self._load(effective.transaction_id, connection) != effective):
                            raise CheckoutUnavailable("CANONICAL_PERSISTENCE_MISMATCH")
                # Successor + lineage commit BEFORE external reconciliation.
                # A crash leaves a reusable PENDING generation, never a second
                # successor. The same provider operation key is used on retry.
                try:
                    destination = self.runtime.reconcile(
                        effective, operation_key=self._key(f"runtime:{effective.transaction_id}"),
                    )
                except CheckoutUnavailable:
                    raise
                except Exception as error:
                    raise CheckoutUnavailable("RUNTIME_RECONCILIATION_FAILED") from error
                with connection.transaction():
                    self.authority.lock_scope(grant, connection=connection)
                    checked = self.authority.authenticate(alias, binding, connection=connection)
                    if checked != grant:
                        raise CheckoutUnavailable("GRANT_CHANGED")
                    self._grant(checked, binding)
                    current = self._load(effective.transaction_id, connection)
                    self._transaction(current, grant, binding)
                    if current != effective or current.expires_at <= self.clock():
                        raise CheckoutUnavailable("TRANSACTION_CHANGED")
                    self._eligible(self.authority.validate(grant, current, connection=connection), current)
                    if not self.authority.validate_destination(destination, current):
                        raise CheckoutUnavailable("DESTINATION_INVALID")
                    confirm = getattr(self.authority, "confirm", None)
                    if callable(confirm):
                        confirm(grant, current, connection=connection, now=self.clock())
                    self.repository.runtime_result(connection, self.namespace, current.transaction_id,
                                                   state="READY", reason="OK")
                    self.repository.record(connection, namespace=self.namespace, grant=grant,
                        effective_id=current.transaction_id, generation=generation,
                        result="RESOLVED", reason="OK", now=self.clock())
                return CheckoutResolution(destination, grant.original_transaction_id,
                                          effective.transaction_id, generation)
            except Exception as error:
                failure = error if isinstance(error, CheckoutUnavailable) else CheckoutUnavailable("CHECKOUT_INTERNAL_FAILURE")
                with connection.transaction():
                    self.repository.runtime_result(connection, self.namespace,
                        effective.transaction_id if effective else None,
                        state="FAILED", reason=failure.reason_code)
                    self.repository.record(connection, namespace=self.namespace, grant=grant,
                        effective_id=effective.transaction_id if effective else None,
                        generation=generation, result="REJECTED", reason=failure.reason_code, now=self.clock())
                if failure is error:
                    raise
                raise failure from error

    def _load(self, transaction_id, connection):
        transaction = self.authority.load(transaction_id, connection=connection)
        if transaction is None:
            raise CheckoutUnavailable("TRANSACTION_MISSING")
        if transaction.transaction_id != transaction_id:
            raise CheckoutUnavailable("TRANSACTION_BINDING_MISMATCH")
        return transaction

    def _key(self, material):
        return uuid5(NAMESPACE_URL, f"evergreen-checkout:{self.namespace}:{material}")

    @staticmethod
    def _aware(value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CheckoutUnavailable("TIMEZONE_REQUIRED")

    @staticmethod
    def _grant(grant, binding):
        if grant is None:
            raise CheckoutUnavailable("ALIAS_INVALID")
        if grant.revoked:
            raise CheckoutUnavailable("GRANT_REVOKED")
        if grant.binding != binding:
            raise CheckoutUnavailable("IDENTITY_MISMATCH")

    def _transaction(self, transaction, grant, binding):
        if transaction is None:
            raise CheckoutUnavailable("TRANSACTION_MISSING")
        if transaction.revoked:
            raise CheckoutUnavailable("TRANSACTION_REVOKED")
        if transaction.binding != binding or transaction.binding != grant.binding:
            raise CheckoutUnavailable("IDENTITY_MISMATCH")
        if transaction.status == "PURCHASED":
            raise CheckoutUnavailable("PURCHASE_COMPLETE")
        if transaction.status not in self.ACTIVE | {"EXPIRED"}:
            raise CheckoutUnavailable("TRANSACTION_INACTIVE")

    @staticmethod
    def _eligible(value, transaction):
        for field, reason in (
            ("identity_valid", "IDENTITY_MISMATCH"),
            ("offer_available", "OFFER_UNAVAILABLE"),
            ("product_available", "PRODUCT_UNAVAILABLE"),
            ("publication_valid", "PUBLICATION_INVALID"),
            ("purchase_allowed", "PURCHASE_NOT_ALLOWED"),
            ("commerce_allowed", "COMMERCE_BLOCKED"),
            ("runtime_supported", "RUNTIME_UNSUPPORTED"),
            ("price_unambiguous", "PRICE_AMBIGUOUS"),
        ):
            if getattr(value, field, False) is not True:
                raise CheckoutUnavailable(reason)
        price = value.configured_price
        if (price is None or type(price.minor) is not int or price.minor < 0
                or len(price.currency) != 3 or not price.currency.isascii()
                or not price.currency.isalpha() or price.currency != price.currency.upper()
                or price.currency != transaction.price.currency
                or price.minor != transaction.price.minor):
            raise CheckoutUnavailable("PRICE_INVALID")
