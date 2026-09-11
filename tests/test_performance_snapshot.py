from datetime import datetime, timezone

import pytest

from app.models.performance_snapshot import ReportingPeriodService
from app.services.performance_snapshot_service import PerformanceSnapshotService


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize("key,start,end", [
    ("TODAY", "2026-03-08T05:00:00+00:00", "2026-03-09T04:00:00+00:00"),
    ("YESTERDAY", "2026-03-07T05:00:00+00:00", "2026-03-08T05:00:00+00:00"),
    ("LAST_7_DAYS", "2026-03-01T16:00:00+00:00", "2026-03-08T16:00:00+00:00"),
    ("LAST_30_DAYS", "2026-02-06T16:00:00+00:00", "2026-03-08T16:00:00+00:00"),
    ("THIS_MONTH", "2026-03-01T05:00:00+00:00", "2026-04-01T04:00:00+00:00"),
])
def test_reporting_periods_use_new_york_and_half_open_boundaries(key, start, end):
    period = ReportingPeriodService().resolve(key, now=utc("2026-03-08T16:00:00Z"))
    assert period.start == utc(start)
    assert period.end == utc(end)
    assert period.contains(period.start)
    assert not period.contains(period.end)


def test_all_time_and_year_boundary():
    periods = ReportingPeriodService()
    all_time = periods.resolve("ALL_TIME", now=utc("2026-01-01T06:00:00Z"))
    month = periods.resolve("THIS_MONTH", now=utc("2026-12-15T12:00:00Z"))
    assert all_time.start is None
    assert month.start == utc("2026-12-01T05:00:00Z")
    assert month.end == utc("2027-01-01T05:00:00Z")


class FakeRepository:
    def people(self, **_):
        return [
            {"telegram_user_id": 1, "username": "new_name", "display_name": "One",
             "mapping_id": None, "verification_status": None, "mapping_active": None,
             "relationship_state": {"stage": "prospect"}, "lifetime_gross_minor": None,
             "purchase_count": None},
            {"telegram_user_id": 2, "username": None, "display_name": None,
             "mapping_id": 9, "verification_status": "VERIFIED", "mapping_active": True,
             "local_fanvue_user_id": 22, "external_fanvue_user_uuid": "buyer-2",
             "customer_commerce_profile_id": "profile-2", "profile_state": "FIRST_PURCHASE",
             "lifetime_gross_minor": 2500, "purchase_count": 2},
            {"telegram_user_id": 3, "username": "ambiguous", "display_name": None,
             "mapping_id": 10, "verification_status": "PENDING", "mapping_active": True,
             "local_fanvue_user_id": 33, "external_fanvue_user_uuid": "buyer-3",
             "customer_commerce_profile_id": "profile-3", "profile_state": "HIGH_VALUE",
             "lifetime_gross_minor": 99999, "purchase_count": 20},
            {"telegram_user_id": 4, "username": "outbound_only", "display_name": None,
             "mapping_id": None, "verification_status": None, "mapping_active": None},
        ]

    def inbound_events(self, **_):
        return [
            {"telegram_user_id": 1, "event_key": "telegram:1:101",
             "occurred_at": utc("2026-09-06T14:00:00Z"), "source": "operation"},
            {"telegram_user_id": 1, "event_key": "telegram:1:101",
             "occurred_at": utc("2026-09-06T14:00:00Z"), "source": "chat"},
            {"telegram_user_id": 2, "event_key": "telegram:2:201",
             "occurred_at": utc("2026-09-01T14:00:00Z"), "source": "chat"},
            {"telegram_user_id": 2, "event_key": "telegram:2:202",
             "occurred_at": utc("2026-09-06T15:00:00Z"), "source": "operation"},
        ]

    def ava_events(self, **_):
        return [
            {"telegram_user_id": 1, "event_key": "telegram:1:501",
             "occurred_at": utc("2026-09-06T14:01:00Z"), "source": "ordinary"},
            {"telegram_user_id": 1, "event_key": "telegram:1:501",
             "occurred_at": utc("2026-09-06T14:01:00Z"), "source": "chat"},
            {"telegram_user_id": 2, "event_key": "telegram:2:502",
             "occurred_at": utc("2026-09-06T15:01:00Z"), "source": "commercial"},
        ]

    def current_customer_state(self, **_):
        return {2: {"active_purchase_intent": True, "active_sales_session": True}}

    def transactions(self, **_):
        base = {"payment_status": "succeeded", "net_minor": 0,
                "external_fanvue_user_uuid": "buyer"}
        return [
            dict(base, record_id="old", transaction_order_id="old", gross_minor=1000,
                 purchase_source="mediaLink", payment_timestamp=utc("2026-09-01T12:00:00Z"),
                 customer_commerce_profile_id="profile-2", excluded_test=False),
            dict(base, record_id="content", transaction_order_id="content", gross_minor=2000,
                 purchase_source="mediaLink", payment_timestamp=utc("2026-09-06T16:00:00Z"),
                 customer_commerce_profile_id="profile-2", excluded_test=False),
            dict(base, record_id="tip", transaction_order_id="tip", gross_minor=500,
                 purchase_source="tip", payment_timestamp=utc("2026-09-06T17:00:00Z"),
                 customer_commerce_profile_id="profile-2", excluded_test=False),
            dict(base, record_id="sub", transaction_order_id="sub", gross_minor=700,
                 purchase_source="renewal", payment_timestamp=utc("2026-09-06T18:00:00Z"),
                 customer_commerce_profile_id="profile-3", excluded_test=False),
            dict(base, record_id="unknown", transaction_order_id="unknown", gross_minor=300,
                 purchase_source="other", payment_timestamp=utc("2026-09-06T19:00:00Z"),
                 customer_commerce_profile_id="profile-3", excluded_test=False),
            dict(base, record_id="test", transaction_order_id="test", gross_minor=999,
                 purchase_source="mediaLink", payment_timestamp=utc("2026-09-06T20:00:00Z"),
                 customer_commerce_profile_id="profile-2", excluded_test=True),
            dict(base, record_id="failed", transaction_order_id="failed", gross_minor=999,
                 purchase_source="mediaLink", payment_status="failed",
                 payment_timestamp=utc("2026-09-06T20:00:00Z"),
                 customer_commerce_profile_id="profile-2", excluded_test=False),
        ]

    def offers(self, **_):
        return [{"record_id": "offer", "presented_at": utc("2026-09-06T16:00:00Z"),
                 "excluded_test": False, "purchased_at": None},
                {"record_id": "test-offer", "presented_at": utc("2026-09-06T16:00:00Z"),
                 "excluded_test": True}]

    def would_have_sold(self, **_):
        return [{"record_id": "would", "observed_at": utc("2026-09-06T16:00:00Z")}]


def service():
    return PerformanceSnapshotService(repository=FakeRepository(),
        clock=lambda: utc("2026-09-06T21:00:00Z"))


def test_people_projection_identity_precedence_and_commerce_guard():
    people = service().people_projection(creator_profile_id=2, fanvue_account_id=2)
    by_id = {p["telegramUserId"]: p for p in people}
    assert by_id[1]["personKey"] == "telegram:2:2:1"
    assert by_id[1]["identityStatus"] == "UNMAPPED"
    assert by_id[2]["identityStatus"] == "MAPPED_VERIFIED"
    assert by_id[2]["username"] is None
    assert by_id[2]["activePurchaseIntent"] is True
    assert by_id[3]["identityStatus"] == "AMBIGUOUS"
    assert by_id[3]["lifetimeVerifiedRevenueMinor"] is None


def test_snapshot_deduplicates_activity_and_classifies_commerce():
    result = service().snapshot(creator_profile_id=2, fanvue_account_id=2, period="TODAY")
    commerce, activity = result["commerce"], result["peopleActivity"]
    assert activity["activePeople"]["value"] == 2
    assert activity["newPeople"]["value"] == 1
    assert activity["returningPeople"]["value"] == 1
    assert activity["customerMessages"]["value"] == 2
    assert activity["avaMessages"]["value"] == 2
    assert commerce["totalVerifiedRevenueMinor"]["value"] == 3500
    assert commerce["contentMediaRevenueMinor"]["value"] == 2000
    assert commerce["tipsRevenueMinor"]["value"] == 500
    assert commerce["subscriptionRenewalRevenueMinor"]["value"] == 700
    assert commerce["unclassifiedRevenueMinor"]["value"] == 300
    assert commerce["qualifyingPurchases"]["value"] == 1
    assert commerce["uniqueBuyers"]["value"] == 1
    assert commerce["newBuyers"]["value"] == 0
    assert commerce["repeatBuyers"]["value"] == 1
    assert commerce["averagePurchaseValueMinor"]["value"] == 2000
    assert commerce["offersPurchased"]["value"] == 0
    assert commerce["offerConversion"]["value"] == 0.0
    assert result["dataQuality"]["knownTestRecordsExcluded"] == 1


@pytest.mark.parametrize("metric,key", [
    ("TOTAL_REVENUE", "totalVerifiedRevenueMinor"),
    ("CONTENT_REVENUE", "contentMediaRevenueMinor"),
    ("TIPS", "tipsRevenueMinor"),
    ("PURCHASES", "qualifyingPurchases"),
    ("OFFERS_PRESENTED", "offersPresented"),
    ("WOULD_HAVE_SOLD", "wouldHaveSold"),
])
def test_record_drill_down_reconciles(metric, key):
    snapshot = service().snapshot(creator_profile_id=2, fanvue_account_id=2, period="TODAY")
    detail = service().drill_down(creator_profile_id=2, fanvue_account_id=2,
                                  period="TODAY", metric=metric)
    assert detail["count"] == len(snapshot["commerce"][key]["recordIds"])
    if "Revenue" in key:
        assert detail["amountMinor"] == snapshot["commerce"][key]["value"]


@pytest.mark.parametrize("metric,key", [
    ("ACTIVE_PEOPLE", "activePeople"), ("NEW_PEOPLE", "newPeople"),
    ("RETURNING_PEOPLE", "returningPeople"),
])
def test_person_drill_down_reconciles(metric, key):
    snapshot = service().snapshot(creator_profile_id=2, fanvue_account_id=2, period="TODAY")
    detail = service().drill_down(creator_profile_id=2, fanvue_account_id=2,
                                  period="TODAY", metric=metric)
    assert detail["count"] == snapshot["peopleActivity"][key]["value"]


@pytest.mark.parametrize("metric,key", [
    ("UNIQUE_BUYERS", "uniqueBuyers"), ("NEW_BUYERS", "newBuyers"),
    ("REPEAT_BUYERS", "repeatBuyers"),
])
def test_buyer_drill_down_reconciles(metric, key):
    snapshot = service().snapshot(creator_profile_id=2, fanvue_account_id=2, period="TODAY")
    detail = service().drill_down(creator_profile_id=2, fanvue_account_id=2,
                                  period="TODAY", metric=metric)
    assert detail["count"] == snapshot["commerce"][key]["value"]


class OfferCohortRepository(FakeRepository):
    def offers(self, **_):
        return [
            {"record_id": "same-period", "presented_at": utc("2026-09-06T10:00:00Z"),
             "purchased_at": utc("2026-09-06T11:00:00Z"), "realized_amount_minor": 1000,
             "status": "PURCHASED", "excluded_test": False},
            {"record_id": "purchased-later", "presented_at": utc("2026-09-06T12:00:00Z"),
             "purchased_at": utc("2026-09-08T11:00:00Z"), "realized_amount_minor": 2000,
             "status": "PURCHASED", "excluded_test": False},
            {"record_id": "never", "presented_at": utc("2026-09-06T13:00:00Z"),
             "purchased_at": None, "status": "PRESENTED", "excluded_test": False},
            {"record_id": "clicked", "presented_at": utc("2026-09-06T14:00:00Z"),
             "purchased_at": None, "status": "CLICKED", "excluded_test": False},
            {"record_id": "abandoned", "presented_at": utc("2026-09-06T15:00:00Z"),
             "purchased_at": None, "status": "ABANDONED", "excluded_test": False},
            {"record_id": "synthetic", "presented_at": utc("2026-09-06T16:00:00Z"),
             "purchased_at": utc("2026-09-06T17:00:00Z"), "status": "PURCHASED", "excluded_test": True},
            {"record_id": "same-period", "presented_at": utc("2026-09-06T10:00:00Z"),
             "purchased_at": utc("2026-09-06T11:00:00Z"), "status": "PURCHASED", "excluded_test": False},
            {"record_id": "before-period", "presented_at": utc("2026-09-05T10:00:00Z"),
             "purchased_at": utc("2026-09-06T11:00:00Z"), "status": "PURCHASED", "excluded_test": False},
        ]


def cohort_service(repository=None):
    return PerformanceSnapshotService(repository=repository or OfferCohortRepository(),
        clock=lambda: utc("2026-09-06T21:00:00Z"))


def test_offer_conversion_uses_presented_cohort_and_eventual_verified_purchase():
    result = cohort_service().snapshot(creator_profile_id=2, fanvue_account_id=2, period="TODAY")
    assert result["commerce"]["offersPresented"]["value"] == 5
    assert result["commerce"]["offersPurchased"]["value"] == 2
    assert result["commerce"]["offerConversion"]["value"] == 40.0
    assert result["commerce"]["qualifyingPurchases"]["value"] == 1


@pytest.mark.parametrize("metric,count", [
    ("OFFERS_PRESENTED", 5), ("OFFERS_PURCHASED", 2), ("OFFER_CONVERSION", 5),
])
def test_offer_cohort_drill_down_reconciles_and_shows_conversion_state(metric, count):
    detail = cohort_service().drill_down(creator_profile_id=2, fanvue_account_id=2,
        period="TODAY", metric=metric)
    assert detail["count"] == count
    assert all(row["offerConversionStatus"] in {"PURCHASED", "NOT_PURCHASED"}
               for row in detail["items"])


def test_offer_conversion_without_denominator_is_unavailable():
    repository = OfferCohortRepository()
    repository.offers = lambda **_: []
    result = cohort_service(repository).snapshot(creator_profile_id=2,
        fanvue_account_id=2, period="TODAY")
    conversion = result["commerce"]["offerConversion"]
    assert conversion["status"] == "UNAVAILABLE"
    assert conversion["value"] is None


def test_api_functions_delegate_to_read_only_snapshot_service(monkeypatch):
    import app.api.creator_intelligence as api

    class Stub:
        def snapshot(self, **values): return {"kind": "snapshot", **values}
        def drill_down(self, **values): return {"kind": "detail", **values}

    monkeypatch.setattr(api, "_snapshot_scope", lambda: (2, 7))
    monkeypatch.setattr(api, "PerformanceSnapshotService", Stub)
    summary = api.performance_snapshot()
    detail = api.performance_snapshot_drill_down(metric="TIPS")
    assert summary == {"kind": "snapshot", "creator_profile_id": 2,
                       "fanvue_account_id": 7, "period": "TODAY"}
    assert detail["kind"] == "detail"
    assert detail["metric"] == "TIPS"


def test_current_sales_status_uses_canonical_state_and_operations_failures(monkeypatch):
    import app.api.creator_intelligence as api

    class SalesState:
        def current_sales_status(self, **values):
            assert values == {"creator_profile_id": 2, "fanvue_account_id": 7}
            return {"active_sales_sessions": 3, "active_purchase_intents": 4}

    class Operations:
        def failures(self, **values):
            assert values == {"account_id": 7}
            return {"total": 2, "items": [{}, {}]}

    monkeypatch.setattr(api, "_snapshot_scope", lambda: (2, 7))
    monkeypatch.setattr(api, "PerformanceSnapshotRepository", SalesState)
    monkeypatch.setattr(api, "OperationsWorkspaceService", Operations)
    assert api.current_sales_status() == {
        "activeSalesSessions": 3, "activePurchaseIntents": 4,
        "commercialFailures": 2, "asOf": "CURRENT",
    }
