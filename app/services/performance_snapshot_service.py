"""Account-scoped, read-only business performance snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.performance_snapshot import ReportingPeriodService
from app.repositories.performance_snapshot_repository import PerformanceSnapshotRepository


class PerformanceSnapshotService:
    DRILLDOWNS = frozenset({
        "TOTAL_REVENUE", "CONTENT_REVENUE", "TIPS", "PURCHASES",
        "UNIQUE_BUYERS", "NEW_BUYERS", "REPEAT_BUYERS", "OFFERS_PRESENTED",
        "OFFERS_PURCHASED", "OFFER_CONVERSION",
        "WOULD_HAVE_SOLD", "ACTIVE_PEOPLE", "NEW_PEOPLE", "RETURNING_PEOPLE",
    })

    def __init__(self, *, repository=None, periods=None, clock=None):
        self.repository = repository or PerformanceSnapshotRepository()
        self.periods = periods or ReportingPeriodService()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self, *, creator_profile_id: int, fanvue_account_id: int,
                 period: str = "TODAY") -> dict:
        resolved, data = self._evaluate(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, period=period,
        )
        transactions = data["transactions"]
        qualifying = data["purchases"]
        people = data["active_people"]
        offers = data["offers"]
        purchased_offers = data["purchased_offers"]
        conversion = (round(len(purchased_offers) / len(offers) * 100, 1)
                      if offers else None)
        metrics = {
            "totalVerifiedRevenueMinor": self._metric(
                sum(int(row.get("gross_minor") or 0) for row in transactions),
                [row["record_id"] for row in transactions]),
            "contentMediaRevenueMinor": self._metric(
                sum(int(row.get("gross_minor") or 0) for row in data["content"]),
                [row["record_id"] for row in data["content"]]),
            "tipsRevenueMinor": self._metric(
                sum(int(row.get("gross_minor") or 0) for row in data["tips"]),
                [row["record_id"] for row in data["tips"]]),
            "subscriptionRenewalRevenueMinor": self._metric(
                sum(int(row.get("gross_minor") or 0) for row in data["subscriptions"]),
                [row["record_id"] for row in data["subscriptions"]]),
            "unclassifiedRevenueMinor": self._metric(
                sum(int(row.get("gross_minor") or 0) for row in data["unclassified"]),
                [row["record_id"] for row in data["unclassified"]]),
            "qualifyingPurchases": self._metric(len(qualifying), [r["record_id"] for r in qualifying]),
            "uniqueBuyers": self._metric(len(data["unique_buyers"]), data["unique_buyers"]),
            "newBuyers": self._metric(len(data["new_buyers"]), data["new_buyers"]),
            "repeatBuyers": self._metric(len(data["repeat_buyers"]), data["repeat_buyers"]),
            "averagePurchaseValueMinor": self._metric(
                round(sum(int(r.get("gross_minor") or 0) for r in qualifying) / len(qualifying))
                if qualifying else 0, [r["record_id"] for r in qualifying]),
            "offersPresented": self._metric(len(offers), [r["record_id"] for r in offers]),
            "offersPurchased": self._metric(len(purchased_offers), [r["record_id"] for r in purchased_offers]),
            "offerConversion": (self._metric(conversion, [r["record_id"] for r in offers])
                if offers else self._unavailable("No offers were presented during this period.")),
            "wouldHaveSold": self._metric(len(data["would_have_sold"]), [r["record_id"] for r in data["would_have_sold"]]),
            "activePeople": self._metric(len(people), [r["personKey"] for r in people]),
            "newPeople": self._metric(len(data["new_people"]), [r["personKey"] for r in data["new_people"]]),
            "returningPeople": self._metric(len(data["returning_people"]), [r["personKey"] for r in data["returning_people"]]),
            "customerMessages": self._metric(len(data["period_inbound"]), [r["event_key"] for r in data["period_inbound"]]),
            "avaMessages": self._metric(len(data["period_ava"]), [r["event_key"] for r in data["period_ava"]]),
        }
        return {
            "period": resolved.as_dict(), "commerce": {k: v for k, v in metrics.items()
                if k not in {"activePeople","newPeople","returningPeople","customerMessages","avaMessages"}},
            "peopleActivity": {k: metrics[k] for k in
                ("activePeople","newPeople","returningPeople","customerMessages","avaMessages")},
            "dataQuality": {
                "knownTestRecordsExcluded": data["excluded_test_count"],
                "testExclusionAuthority": "persisted PurchaseIntent/publication provenance",
                "interval": "[start,end)",
            },
        }

    def drill_down(self, *, creator_profile_id: int, fanvue_account_id: int,
                   period: str, metric: str) -> dict:
        selected = str(metric).upper()
        if selected not in self.DRILLDOWNS:
            raise ValueError(f"Unsupported Snapshot drill-down metric: {metric}")
        resolved, data = self._evaluate(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, period=period)
        mapping = {
            "TOTAL_REVENUE": data["transactions"], "CONTENT_REVENUE": data["content"],
            "TIPS": data["tips"], "PURCHASES": data["purchases"],
            "OFFERS_PRESENTED": data["offers"], "OFFERS_PURCHASED": data["purchased_offers"],
            "OFFER_CONVERSION": data["offers"], "WOULD_HAVE_SOLD": data["would_have_sold"],
            "ACTIVE_PEOPLE": data["active_people"], "NEW_PEOPLE": data["new_people"],
            "RETURNING_PEOPLE": data["returning_people"],
        }
        if selected in {"UNIQUE_BUYERS", "NEW_BUYERS", "REPEAT_BUYERS"}:
            key = {"UNIQUE_BUYERS":"unique_buyers","NEW_BUYERS":"new_buyers",
                   "REPEAT_BUYERS":"repeat_buyers"}[selected]
            wanted = set(data[key])
            rows = [data["buyer_rows"][buyer] for buyer in sorted(wanted)]
        else:
            rows = mapping[selected]
        amount = sum(int(r.get("gross_minor") or r.get("realized_amount_minor") or 0)
                     for r in rows)
        return {"period": resolved.as_dict(), "metric": selected,
                "count": len(rows), "amountMinor": amount, "items": rows}

    def people_projection(self, *, creator_profile_id: int, fanvue_account_id: int) -> list[dict]:
        people = self.repository.people(creator_profile_id=creator_profile_id,
                                        fanvue_account_id=fanvue_account_id)
        events = self._dedupe(self.repository.inbound_events(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id))
        by_person: dict[int, list[dict]] = {}
        for event in events:
            by_person.setdefault(int(event["telegram_user_id"]), []).append(event)
        current = self.repository.current_customer_state(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        return [self._project_person(row, by_person.get(int(row["telegram_user_id"]), []),
                    current.get(int(row["telegram_user_id"]), {}), creator_profile_id,
                    fanvue_account_id) for row in people]

    def _evaluate(self, *, creator_profile_id: int, fanvue_account_id: int, period: str):
        resolved = self.periods.resolve(period, now=self.clock())
        people_all = self.people_projection(creator_profile_id=creator_profile_id,
                                             fanvue_account_id=fanvue_account_id)
        inbound_all = self._dedupe(self.repository.inbound_events(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id))
        ava_all = self._dedupe(self.repository.ava_events(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id))
        period_inbound = [r for r in inbound_all if resolved.contains(r["occurred_at"])]
        period_ava = [r for r in ava_all if resolved.contains(r["occurred_at"])]
        active_ids = {int(r["telegram_user_id"]) for r in period_inbound}
        active = [p for p in people_all if p["telegramUserId"] in active_ids]
        new = [p for p in active if p["firstChatAt"] and resolved.contains(p["firstChatAt"])]
        returning = [p for p in active if p not in new]
        raw_transactions = self.repository.transactions(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        excluded = [r for r in raw_transactions if r.get("excluded_test")
                    and self._successful(r) and resolved.contains(r["payment_timestamp"])]
        successful = [r for r in raw_transactions if self._successful(r)
                      and not r.get("excluded_test")]
        transactions = [r for r in successful if resolved.contains(r["payment_timestamp"])]
        classified = {name: [r for r in transactions if self._classify(r)==name]
                      for name in ("content","tip","subscription","unclassified")}
        purchases = classified["content"]
        before_count: dict[str, int] = {}
        period_count: dict[str, int] = {}
        for row in successful:
            if self._classify(row) != "content": continue
            buyer = str(row["customer_commerce_profile_id"])
            if resolved.start is not None and row["payment_timestamp"] < resolved.start:
                before_count[buyer] = before_count.get(buyer, 0) + 1
            if resolved.contains(row["payment_timestamp"]):
                period_count[buyer] = period_count.get(buyer, 0) + 1
        unique_buyers = sorted(period_count)
        new_buyers = sorted(b for b in unique_buyers if before_count.get(b, 0)==0)
        repeat_buyers = sorted(b for b in unique_buyers
            if before_count.get(b, 0)>0 or period_count.get(b, 0)>=2)
        buyer_rows = {}
        for row in purchases:
            buyer = str(row["customer_commerce_profile_id"])
            buyer_rows.setdefault(buyer, {
                "customerCommerceProfileId": buyer,
                "externalFanvueUserUuid": str(row.get("external_fanvue_user_uuid") or ""),
                "qualifyingPurchaseCountInPeriod": period_count.get(buyer, 0),
                "qualifyingRevenueMinorInPeriod": 0,
            })
            buyer_rows[buyer]["qualifyingRevenueMinorInPeriod"] += int(row.get("gross_minor") or 0)
        offers_by_id = {}
        for row in self.repository.offers(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id):
            if not row.get("excluded_test") and resolved.contains(row["presented_at"]):
                offers_by_id.setdefault(str(row["record_id"]), row)
        offers = list(offers_by_id.values())
        offers = [dict(r, offerConversionStatus=("PURCHASED" if r.get("purchased_at")
                  else "NOT_PURCHASED")) for r in offers]
        purchased_offers = [r for r in offers if r.get("purchased_at")]
        would = [r for r in self.repository.would_have_sold(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
            if resolved.contains(r["observed_at"])]
        return resolved, {"people_all": people_all, "active_people": active,
            "new_people": new, "returning_people": returning,
            "period_inbound": period_inbound, "period_ava": period_ava,
            "transactions": transactions, "content": classified["content"],
            "tips": classified["tip"], "subscriptions": classified["subscription"],
            "unclassified": classified["unclassified"], "purchases": purchases,
            "unique_buyers": unique_buyers, "new_buyers": new_buyers,
            "repeat_buyers": repeat_buyers, "buyer_rows": buyer_rows, "offers": offers,
            "purchased_offers": purchased_offers,
            "would_have_sold": would, "excluded_test_count": len(excluded)}

    @staticmethod
    def _project_person(row, events, current, creator_profile_id, fanvue_account_id):
        verified = bool(row.get("mapping_active") and row.get("verification_status") == "VERIFIED")
        ordered = sorted(events, key=lambda event: event["occurred_at"])
        status = "MAPPED_VERIFIED" if verified else (
            "AMBIGUOUS" if row.get("mapping_id") else "UNMAPPED")
        return {"personKey": f"telegram:{creator_profile_id}:{fanvue_account_id}:{row['telegram_user_id']}",
            "telegramUserId": int(row["telegram_user_id"]), "username": row.get("username"),
            "displayName": row.get("display_name") or row.get("username") or str(row["telegram_user_id"]),
            "identityStatus": status, "prospectState": row.get("relationship_state"),
            "fanvueUserId": row.get("local_fanvue_user_id") if verified else None,
            "externalFanvueUserUuid": str(row.get("external_fanvue_user_uuid")) if verified else None,
            "customerCommerceProfileId": str(row.get("customer_commerce_profile_id")) if verified and row.get("customer_commerce_profile_id") else None,
            "buyerStatus": row.get("profile_state") if verified else None,
            "lifetimeVerifiedRevenueMinor": int(row.get("lifetime_gross_minor") or 0) if verified else None,
            "qualifyingPurchaseCount": int(row.get("purchase_count") or 0) if verified else None,
            "firstChatAt": ordered[0]["occurred_at"] if ordered else None,
            "lastChatAt": ordered[-1]["occurred_at"] if ordered else None,
            "activePurchaseIntent": bool(current.get("active_purchase_intent")) if verified else False,
            "activeSalesSession": bool(current.get("active_sales_session")) if verified else False}

    @staticmethod
    def _dedupe(rows):
        result = {}
        for row in rows:
            key = (int(row["telegram_user_id"]), str(row["event_key"]))
            result.setdefault(key, row)
        return sorted(result.values(), key=lambda row: (row["occurred_at"], row["event_key"]))

    @staticmethod
    def _successful(row):
        return str(row.get("payment_status") or "").lower() in {"succeeded","successful","paid","completed"}

    @staticmethod
    def _classify(row):
        source = str(row.get("purchase_source") or "").lower().replace("_", "")
        if source in {"medialink","media","content","ppv"}: return "content"
        if source == "tip": return "tip"
        if source in {"subscription","renewal"}: return "subscription"
        return "unclassified"

    @staticmethod
    def _metric(value, record_ids):
        return {"status": "AVAILABLE", "value": value,
                "recordIds": [str(item) for item in record_ids]}

    @staticmethod
    def _unavailable(reason):
        return {"status": "UNAVAILABLE", "value": None, "recordIds": [],
                "reason": reason}
