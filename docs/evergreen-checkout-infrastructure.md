# Provider-neutral evergreen checkout infrastructure

This change supplies a reusable lifecycle service and PostgreSQL lineage
repository. It does not install an HTTP route, a production commerce adapter,
a provider client, or any customer recovery job. The existing media gateway is
unchanged. No historical aliases are swept or backfilled.

## Resolution

`EvergreenCheckoutService.resolve(alias, binding=authenticated_binding)`:

1. Authenticates the alias using a required canonical authority adapter.
2. Serializes the root transaction across processes with a PostgreSQL session
   advisory lock, then takes the adapter's canonical buyer/offer transaction lock.
3. Reauthenticates the grant, loads the original and latest authoritative
   transaction, and validates identity, offer, product, publication, purchase,
   commerce, runtime support, and canonical configured price.
4. For expiry, performs the normal expiry transition if still due, then inserts
   one canonical successor and one lineage generation in the **same transaction**.
   An already EXPIRED predecessor is never updated. Successor IDs are deterministic
   per predecessor and namespace; generation, predecessor, and successor uniqueness
   are enforced by PostgreSQL. Historical lineage fields cannot be updated/deleted.
5. Commits before runtime reconciliation. The runtime operation key is stable per
   transaction. Failure leaves the generation available for safe reconciliation;
   it does not create a second successor. An expired generation with unresolved
   runtime state fails closed instead of starting another potentially ambiguous
   external operation.
6. Revalidates current authority after reconciliation, validates the destination,
   then records the outcome and returns the effective transaction and destination.

The alias is never rewritten. The latest generation is indexed; resolving a
long-lived alias does not recursively traverse its history. Purchase completion
returns `PURCHASE_COMPLETE`; ownership/delivery remains a separate canonical
responsibility. Nothing in this service charges or delivers a product.

## Required integration contracts

`CheckoutAuthority` is mandatory, with no live default. A future adapter must:

- Use the existing canonical transaction store, grant authentication, ownership,
  price, product/publication validity and customer/operator block authorities.
- Use the supplied database connection for transaction inserts/expiry and locked
  eligibility checks. Never commit independently. This is essential for atomicity.
- Share canonical buyer/offer locking with other transaction creators, revocation
  writers and purchase-verification writers; independently authenticated caller
  identity must supply `CheckoutBinding`. An alias alone must not fabricate identity.
- Prevent conflicting active transactions or unresolved purchases under existing
  canonical rules; preserve canonical attribution in successor creation.
- Return all eligibility decisions explicitly. Missing/false checks deny access.
  Set `price_unambiguous` only when canonical accounting rules authorize the
  configured price, including any difference from historical price. Currency
  changes fail closed. No price is inferred from the URL or provider response.
- Validate destination host, scheme and authorization using the existing
  allowlist. This service deliberately does not infer an allowed destination.
- Use a distinct, stable namespace per canonical transaction store. Lineage UUIDs
  refer to that store; there is no duplicate transaction table and no foreign key
  to a provider-specific schema. Adapter persistence verification checks IDs and
  immutable transaction snapshots before commit.

`CheckoutRuntime.reconcile` is also mandatory and may only prepare checkout state.
It must reconcile by the supplied stable operation key, retire conflicting old
runtime state where required, and never blindly retry an ambiguous external
creation. A provider without sufficient idempotency/reconciliation support must
fail closed. No external exactly-once guarantee is claimed without this adapter
contract. This change provides no implementation for a live provider.
Runtime adapters must also bound external timeouts and avoid acquiring from an
exhausted pool of connections held by concurrent alias-lock waiters; certify the
real adapter's connection use and load behavior before activation.

The generic public exception message is always `This checkout link is unavailable.`
Internal `reason_code` and resolution events retain bounded failure diagnostics.
Raw aliases and provider error strings are not stored in events. Unknown aliases
have no authenticated identity to associate with an audit event and are rejected
before lineage access. Applications must not serialize exception causes publicly.

## Support handling

`CommercialObjectionService` recognizes bounded expired/broken/dead/unavailable
checkout-link language and minor typos, using existing `PAYMENT_TECHNICAL` and
`PAYMENT_SUPPORT_REQUIRED` routing. Unrelated expiration and explicit non-commerce
links are excluded. Ambiguous “can't open it” requires commerce evidence.
`GPTService.generate_response` returns `Let me check into it.` for these reports,
without an LLM request, diagnosis questions, marketing, or a claim of successful
repair. Existing commercial-objection flags prohibit continued selling.

## Migration and activation

Migration `20260920_146_evergreen_checkout_lineage.sql` adds lineage and resolution
events only and is registered with `SchemaManagerService`. It never mutates
existing customer records. Rollback is allowed only while lineage is empty;
after use, disable the adapter and retain audit history.

Production has **not** been activated. Activation would require a separately
reviewed canonical authority/runtime adapter and first-party checkout route,
certification against that adapter, the schema migration through the existing
schema manager, and reload of only the checkout API process. Support classification
and acknowledgement changes require reload of the processes that load those
services. No media-provider or delivery worker restart is needed for this generic
library. Do not run the tests against production.

## Tests

`tests/test_evergreen_checkout.py` initializes its own temporary PostgreSQL cluster
on loopback with synthetic ordinary-digital-template transactions and a fake
idempotent runtime. It never reads a production database URL. `PG_TEST_BIN` can
specify PostgreSQL binaries; on Windows 17 is detected at its standard location.
The cluster is stopped and deleted after testing. Windows sandbox restrictions
may require running this fixture outside the sandbox.

```powershell
$env:DATABASE_URL = 'postgresql://checkout_test@127.0.0.1:1/evergreen_checkout_test'
python -m pytest tests/test_evergreen_checkout.py tests/test_checkout_technical_support.py -q
```

The dummy application URL prevents accidental database access from unrelated
imports. The disposable fixture supplies its own verified connection explicitly.

Regression certification on 2026-09-20: 682 tests passed across commercial
objections, sales progression, pre-generation decisions, commercial authority,
conversation quality, phone-texting style, engagement policy, existing alias and
public-gateway security, buyer advisory locking, and schema-constraint equivalence.
No production database or real provider was part of these runs.

Final focused certification: **64 passed**, including a hard process exit after
commit, ten concurrent requests, successor expiry, eligibility rejection,
immutable lineage, precise runtime diagnostics, and forward/rollback migration.
Both final test runs completed successfully; the temporary cluster was stopped
and cleaned up. Earlier Windows launcher/cleanup fixture failures were fixed.

Files added or changed for this implementation:

- `app/models/evergreen_checkout.py`
- `app/repositories/evergreen_checkout_repository.py`
- `app/services/evergreen_checkout_service.py`
- `app/services/commercial_objection_service.py`
- `app/services/gpt_service.py`
- `app/services/schema_manager_service.py`
- `migrations/forward/20260920_146_evergreen_checkout_lineage.sql`
- `migrations/rollback/20260920_146_evergreen_checkout_lineage.sql`
- `tests/test_evergreen_checkout.py`
- `tests/test_checkout_technical_support.py`
- `docs/evergreen-checkout-infrastructure.md`

Customer-specific actions: **NONE**. Production migrations, activation, provider
invocations, customer recovery, and customer messages: **NONE**.
