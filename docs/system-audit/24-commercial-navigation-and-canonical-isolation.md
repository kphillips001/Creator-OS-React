# Commercial Navigation and Canonical Asset Isolation

## Decision

Available Inventory is a Business workspace. The Business navigation order is:
Commerce, Commerce Library, Available Inventory, Customers, Sales, Operations,
and Intelligence Center. Existing routes remain available; this change only
removes redundant top-level navigation entries.

Commerce Library is a commercial catalog, not an identity/reference catalog.
Canonical reference assets belong exclusively in Reference Library and are
therefore excluded from Commerce Library.

## Authoritative eligibility rule

`app.services.reference_asset_protection` is the single source of truth for
commercial asset eligibility. An asset is ineligible when durable metadata
marks it as a reference, protected/canonical reference, permanent identity
asset, or its classification is `REFERENCE`/`IDENTITY`. The same module owns
the set-based SQL predicate used by repositories.

`CommercialAssetEligibilityService` applies that policy at application
boundaries and verifies creator ownership. It is used before publication,
provider execution, and Purchase Intent presentation. Offering creation uses
the same classifier before any destination change.

## Enforced boundaries

- Available Inventory requires `READY`, `AVAILABLE_INVENTORY`, active,
  non-archived, non-test, commercially eligible assets before pagination.
- Commerce Library excludes identity/reference assets because it is a
  commercial projection.
- Commercial Offering creation rejects reference membership before persistence.
- Commercial Publication creation and LIVE finalization revalidate every member.
- Fanvue execution revalidates before any provider client or upload operation.
- Fulfillment and selector SQL exclude ineligible members; selector evaluation
  also has a defensive `CANONICAL_REFERENCE_ASSET` exclusion.
- Recommendation ranking rejects an ineligible projection rather than ranking it.
- Purchase Intent creation/replacement revalidates the offering before an offer
  can be presented.

## Identity asset #93

The current canonical identity asset is marked by durable reference metadata,
permanent identity metadata, `REFERENCE` classification, and identity tags.
Those markers make it ineligible without relying on its database ID. It remains
usable by Reference Library and generation identity workflows, but cannot appear
in Available Inventory or Commerce Library, join an offering, reach a provider,
be recommended, or receive a Purchase Intent.

## Repository and service audit

The audited commercial paths were Available Inventory, Commerce Library,
Commercial Offering creation, Commercial Publication lifecycle, Fanvue Media
Link execution, Commercial Fulfillment, Commercial Offering Selector,
Recommendation Engine, Customer Sales Brain selection inputs, and Purchase
Intent creation. Content Destination alone was insufficient because historical
reference assets may have `AVAILABLE_INVENTORY`; eligibility is now an
independent mandatory condition.

No asset records, destinations, offerings, publications, or provider state were
mutated by this implementation.
