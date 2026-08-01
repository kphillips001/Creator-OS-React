from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

from app.models.ownership_intelligence import (
    CoverageState,
    OwnershipAnswerState,
    OwnershipEvidence,
    OwnershipIdentity,
    OwnershipLifecycle,
    OwnershipSource,
)
from app.services.ownership_intelligence_service import (
    OwnershipIntelligenceService,
)
from app.services.commercial_intelligence_context_service import (
    CommercialIntelligenceContextService,
)
from app.services.customer_workspace_service import CustomerWorkspaceService
from app.repositories.ownership_intelligence_repository import (
    OwnershipIntelligenceRepository,
)


class Repository:
    def __init__(self, evidence=()):
        self.evidence = tuple(evidence)
        self.offering_id = uuid4()
        self.product_id = uuid4()
        self.session_id = uuid4()
        self.chronology = ()
        self.bundles = ()
        self.sessions = ()

    def evidence_for(self, _identity):
        return self.evidence

    def offering_assets(self, _id, **_scope):
        return (10, 11)

    def product_assets(self, _id, **_scope):
        return (11, 12)

    def session_assets(self, _id, **_scope):
        return {
            "foundation": "photoshoot-1",
            "represented_asset_ids": (10, 11, 12),
            "purchased_asset_ids": (10,),
            "purchase_chronology": self.chronology,
        }

    def bundle_compositions(self, **_scope):
        return self.bundles

    def customer_session_ids(self, _identity):
        return self.sessions


def evidence(source, lifecycle, *, assets=(), offering=None, product=None,
             session=None, proves=False, record=None):
    return OwnershipEvidence(
        source=source, lifecycle=lifecycle,
        identity_path="canonical-test",
        supporting_record_id=record or str(uuid4()),
        asset_ids=tuple(assets), offering_id=offering,
        product_id=product, sales_session_id=session,
        proves_ownership=proves, details=MappingProxyType({}),
    )


def identity():
    return OwnershipIdentity(
        creator_profile_id=7, fanvue_account_id=3,
        external_fanvue_user_uuid=uuid4(),
        telegram_user_id=9, legacy_fanvue_user_id="22",
        core_user_id=uuid4(),
    )


def test_canonical_answer_deduplicates_value_and_preserves_all_provenance():
    repository = Repository()
    repository.evidence = (
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10, 11), offering=repository.offering_id, proves=True,
        ),
        evidence(
            OwnershipSource.CORE_USER_ENTITLEMENT,
            OwnershipLifecycle.ACTIVE,
            assets=(11, 12), product=repository.product_id, proves=True,
        ),
        evidence(
            OwnershipSource.LEGACY_OWNERSHIP,
            OwnershipLifecycle.ACTIVE,
            assets=(12,), proves=True,
        ),
    )
    answer = OwnershipIntelligenceService(repository).answer(identity())

    assert answer.owned_offering_ids == (repository.offering_id,)
    assert answer.owned_product_ids == (repository.product_id,)
    assert answer.owned_asset_ids == (10, 11, 12)
    assert len(answer.evidence) == 3
    assert tuple(item.source for item in answer.evidence) == (
        OwnershipSource.OFFERING_PURCHASE,
        OwnershipSource.CORE_USER_ENTITLEMENT,
        OwnershipSource.LEGACY_OWNERSHIP,
    )


def test_offering_product_asset_bundle_and_remaining_queries():
    repository = Repository()
    repository.evidence = (
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=repository.offering_id, proves=True,
        ),
    )
    service = OwnershipIntelligenceService(repository)
    answer = service.answer(identity())

    assert service.owns_offering(answer, repository.offering_id)
    assert service.owns_asset(answer, 10)
    assert service.offering_coverage(
        answer, repository.offering_id
    ).state is CoverageState.PARTIAL
    assert service.product_coverage(
        answer, repository.product_id
    ).state is CoverageState.NONE
    assert service.bundle_coverage(
        answer, (10, 11, 12)
    ).remaining_asset_ids == (11, 12)
    assert not service.owns_bundle(answer, (10, 11, 12))
    ordered = service.bundle_coverage(answer, (12, 10, 11, 10))
    assert ordered.represented_asset_ids == (12, 10, 11)
    assert ordered.owned_asset_ids == (10,)
    assert ordered.remaining_asset_ids == (12, 11)


def test_session_coverage_distinguishes_session_and_overlapping_ownership():
    repository = Repository()
    repository.evidence = (
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=repository.offering_id,
            session=repository.session_id, proves=True,
        ),
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.FULFILLED,
            assets=(11,), product=repository.product_id, proves=True,
        ),
    )
    coverage = OwnershipIntelligenceService(repository).session_coverage(
        OwnershipIntelligenceService(repository).answer(identity()),
        repository.session_id,
    )

    assert coverage.coverage.state is CoverageState.PARTIAL
    assert coverage.coverage.owned_asset_ids == (10, 11)
    assert coverage.remaining_asset_ids == (12,)
    assert len(coverage.coverage.evidence) == 2
    assert (
        coverage.coverage.evidence[0].sales_session_id
        == repository.session_id
    )
    assert coverage.coverage.evidence[1].sales_session_id is None


def test_lifecycle_preserved_without_incorrect_ownership_inference():
    repository = Repository((
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT, lifecycle,
            assets=(index,), product=uuid4(),
            proves=lifecycle in {
                OwnershipLifecycle.ACTIVE, OwnershipLifecycle.FULFILLED,
            },
        )
        for index, lifecycle in enumerate((
            OwnershipLifecycle.ACTIVE,
            OwnershipLifecycle.FULFILLED,
            OwnershipLifecycle.EXPIRED,
            OwnershipLifecycle.REVOKED,
            OwnershipLifecycle.REFUNDED,
            OwnershipLifecycle.PENDING,
        ), start=1)
    ))
    answer = OwnershipIntelligenceService(repository).answer(identity())

    assert answer.owned_asset_ids == (1, 2)
    assert tuple(item.lifecycle for item in answer.evidence) == (
        OwnershipLifecycle.ACTIVE,
        OwnershipLifecycle.FULFILLED,
        OwnershipLifecycle.EXPIRED,
        OwnershipLifecycle.REVOKED,
        OwnershipLifecycle.REFUNDED,
        OwnershipLifecycle.PENDING,
    )


def test_purchase_intent_terminal_lifecycle_is_not_collapsed_to_pending():
    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchall(self):
            return tuple(
                {
                    "purchase_intent_id": uuid4(),
                    "commercial_offering_id": uuid4(),
                    "status": status, "attribution_result": "PENDING",
                    "asset_ids": [10], "sales_session_id": None,
                }
                for status in ("ABANDONED", "EXPIRED", "CANCELLED")
            )

    projected = OwnershipIntelligenceRepository()._offering_evidence(
        Cursor(), identity()
    )

    assert tuple(item.lifecycle for item in projected) == (
        OwnershipLifecycle.ABANDONED,
        OwnershipLifecycle.EXPIRED,
        OwnershipLifecycle.CANCELLED,
    )


def test_conflict_and_incomplete_evidence_are_explicit():
    product_id = uuid4()
    repository = Repository((
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.ACTIVE, assets=(10,),
            product=product_id, proves=True,
        ),
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.REFUNDED, assets=(10,),
            product=product_id,
        ),
        evidence(
            OwnershipSource.LEGACY_OWNERSHIP,
            OwnershipLifecycle.INCOMPLETE,
        ),
    ))
    service = OwnershipIntelligenceService(repository)
    answer = service.answer(identity())
    coverage = service.bundle_coverage(answer, (10, 11))

    assert answer.conflicts == (
        f"PRODUCT_LIFECYCLE_CONFLICT:{product_id}",
    )
    assert answer.insufficiencies == (
        "LEGACY_CANONICAL_ASSET_MAPPING_MISSING",
    )
    assert coverage.state is CoverageState.CONFLICTING


def test_domain_and_query_boundary_are_read_only():
    service = OwnershipIntelligenceService(Repository())
    forbidden = {
        "grant", "revoke", "repair", "create", "update", "delete",
        "reconcile", "authorize", "select",
    }
    public = {
        name for name in dir(service)
        if not name.startswith("_") and callable(getattr(service, name))
    }
    assert public.isdisjoint(forbidden)


def test_missing_identity_and_scope_are_structured_insufficiency():
    service = OwnershipIntelligenceService(Repository())
    missing = service.answer(OwnershipIdentity(
        creator_profile_id=0, fanvue_account_id=0,
    ))

    assert missing.state is OwnershipAnswerState.INSUFFICIENT
    assert missing.owned_asset_ids == ()
    assert missing.insufficiencies == (
        "CREATOR_SCOPE_UNRESOLVED",
        "ACCOUNT_SCOPE_UNRESOLVED",
        "CUSTOMER_IDENTITY_UNRESOLVED",
        "SUPPORTED_IDENTITY_PATH_MISSING",
    )


def test_source_failure_is_structured_and_preserves_provenance():
    class FailingRepository(Repository):
        def evidence_for(self, _identity):
            raise RuntimeError("database unavailable")

    answer = OwnershipIntelligenceService(
        FailingRepository()
    ).answer(identity())

    assert answer.state is OwnershipAnswerState.INSUFFICIENT
    assert answer.insufficiencies == (
        "OWNERSHIP_SOURCE_UNAVAILABLE:RuntimeError",
    )
    assert answer.evidence[0].source is OwnershipSource.SOURCE_UNAVAILABLE
    assert answer.evidence[0].details["errorType"] == "RuntimeError"


def test_diagnostics_include_state_scope_lifecycle_and_asset_provenance():
    repository = Repository((
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=uuid4(), proves=True,
        ),
    ))
    answer = OwnershipIntelligenceService(repository).answer(identity())

    assert answer.diagnostics["answerState"] == "CONFIRMED_OWNERSHIP"
    assert answer.diagnostics["creatorProfileId"] == 7
    assert answer.diagnostics["fanvueAccountId"] == 3
    assert answer.diagnostics["evaluatedAt"]
    assert answer.diagnostics["lifecycleSummary"] == {"PURCHASED": 1}
    assert answer.diagnostics["assetProvenance"]["10"][0]["source"] == (
        "ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE"
    )


def test_independent_valid_evidence_survives_adverse_product_evidence():
    product_id = uuid4()
    repository = Repository((
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=uuid4(), proves=True,
        ),
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.ACTIVE,
            assets=(10,), product=product_id, proves=True,
        ),
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.REFUNDED,
            assets=(10,), product=product_id,
        ),
    ))
    answer = OwnershipIntelligenceService(repository).answer(identity())

    assert answer.state is OwnershipAnswerState.CONFLICTING
    assert answer.owned_asset_ids == (10,)
    assert len(answer.evidence) == 3


def test_session_coverage_preserves_sequence_chronology_and_overlap():
    repository = Repository((
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=uuid4(), proves=True,
        ),
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.ACTIVE,
            assets=(11,), product=uuid4(), proves=True,
        ),
    ))
    first, second = uuid4(), uuid4()
    repository.chronology = (
        {
            "purchase_intent_id": first, "sequence_index": 1,
            "associated_at": "2026-01-01T00:00:00Z", "asset_ids": (10,),
        },
        {
            "purchase_intent_id": second, "sequence_index": 2,
            "associated_at": "2026-01-02T00:00:00Z", "asset_ids": (10,),
        },
    )
    coverage = OwnershipIntelligenceService(repository).session_coverage(
        OwnershipIntelligenceService(repository).answer(identity()),
        repository.session_id,
    )

    assert coverage.session_purchased_asset_ids == (10,)
    assert coverage.overlapping_external_asset_ids == (11,)
    assert coverage.remaining_asset_ids == (12,)
    assert tuple(item.sequence for item in coverage.chronology) == (1, 2)
    assert tuple(item.purchase_intent_id for item in coverage.chronology) == (
        first, second,
    )


def test_workspace_view_exposes_bundle_session_and_remaining_value():
    repository = Repository((
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=uuid4(), proves=True,
        ),
    ))
    bundle_id = uuid4()
    repository.bundles = ({
        "offering_id": bundle_id, "title": "Set",
        "asset_ids": (10, 11, 12),
    },)
    repository.sessions = (repository.session_id,)
    service = OwnershipIntelligenceService(repository)
    view = service.workspace_view(service.answer(identity()))

    assert view.bundle_coverage[str(bundle_id)].state is CoverageState.PARTIAL
    assert str(repository.session_id) in view.session_coverage
    assert view.remaining_asset_ids == (11, 12)


def test_commercial_intelligence_context_consumes_canonical_answer():
    repository = Repository((
        evidence(
            OwnershipSource.OFFERING_PURCHASE,
            OwnershipLifecycle.PURCHASED,
            assets=(10,), offering=uuid4(), proves=True,
        ),
    ))
    context_service = CommercialIntelligenceContextService()
    context_service.ownership_intelligence = OwnershipIntelligenceService(
        repository
    )

    context = context_service.assemble(
        creator_profile_id=7, fanvue_account_id=3,
        external_fanvue_user_uuid=uuid4(), telegram_user_id=9,
        intended_photoshoot_reference="photoshoot-1",
        bundle_compositions=({
            "photoshoot_reference": "photoshoot-1",
            "asset_ids": (10, 11), "complete_set": True,
        },),
        conversation_context={"latest_message": "show a photo"},
    )

    assert context.ownership.owned_asset_ids == (10,)
    assert context.ownership.evidence_sources == (
        "ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE",
    )
    assert context.canonical_bundle_coverage.state is CoverageState.PARTIAL
    assert context.canonical_bundle_coverage.remaining_asset_ids == (11,)


def test_customer_workspace_consumes_canonical_read_only_projection():
    repository = Repository((
        evidence(
            OwnershipSource.PRODUCT_ENTITLEMENT,
            OwnershipLifecycle.ACTIVE,
            assets=(12,), product=uuid4(), proves=True,
        ),
    ))
    workspace = CustomerWorkspaceService.__new__(CustomerWorkspaceService)
    workspace.creator_profile_resolver = lambda _account: {"id": 7}
    workspace.ownership_intelligence = OwnershipIntelligenceService(repository)

    projection = workspace._ownership_projection(3, "22")

    assert projection.answer.owned_asset_ids == (12,)
    assert projection.answer.identity.creator_profile_id == 7
    assert projection.answer.identity.fanvue_account_id == 3
    assert projection.answer.identity.legacy_fanvue_user_id == "22"
    plain = workspace._plain(projection)
    assert plain["answer"]["owned_asset_ids"] == [12]
    assert plain["answer"]["evidence"][0]["lifecycle"] == "ACTIVE"
