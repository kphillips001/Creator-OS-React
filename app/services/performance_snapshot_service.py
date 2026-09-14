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
        "SUBSCRIPTIONS_RENEWALS", "CUSTOMER_MESSAGES", "AVA_MESSAGES",
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
                   period: str, metric: str, page: int = 1, page_size: int = 50) -> dict:
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
            "SUBSCRIPTIONS_RENEWALS": data["subscriptions"],
            "CUSTOMER_MESSAGES": data["message_people"],
            "AVA_MESSAGES": data["ava_message_people"],
        }
        if selected in {"UNIQUE_BUYERS", "NEW_BUYERS", "REPEAT_BUYERS"}:
            key = {"UNIQUE_BUYERS":"unique_buyers","NEW_BUYERS":"new_buyers",
                   "REPEAT_BUYERS":"repeat_buyers"}[selected]
            wanted = set(data[key])
            rows = [data["buyer_rows"][buyer] for buyer in sorted(wanted)]
        elif selected == "OFFER_CONVERSION":
            rows = [{"presented":len(data["offers"]),"purchased":len(data["purchased_offers"]),
                     "conversionRate":round(len(data["purchased_offers"])/len(data["offers"])*100,1) if data["offers"] else None}]
        else:
            rows = mapping[selected]
        amount = (None if selected in {"OFFER_CONVERSION","UNIQUE_BUYERS","NEW_BUYERS",
                  "REPEAT_BUYERS","ACTIVE_PEOPLE","NEW_PEOPLE","RETURNING_PEOPLE",
                  "CUSTOMER_MESSAGES","AVA_MESSAGES"} else
                  sum(int(r.get("gross_minor") or r.get("realized_amount_minor") or 0) for r in rows))
        page=max(1,int(page));page_size=max(1,min(int(page_size),100));total_rows=len(rows)
        paged_rows=rows[(page-1)*page_size:page*page_size]
        contexts=self._contexts(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        items=[self._business_row(selected,row,contexts,creator_profile_id,fanvue_account_id) for row in paged_rows]
        return {"period": resolved.as_dict(), "metric": selected,
                "count": (len(data["period_inbound"]) if selected=="CUSTOMER_MESSAGES" else
                          len(data["period_ava"]) if selected=="AVA_MESSAGES" else
                          len(data["offers"]) if selected=="OFFER_CONVERSION" else len(rows)),
                "amountMinor": amount, "items": items,
                "pagination":{"page":page,"pageSize":page_size,"totalRows":total_rows,
                              "hasMore":page*page_size<total_rows},
                "presentation":"BUSINESS_FACING","developerDetailsCollapsed":True}

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
        buyer_history: dict[str, list[dict]] = {}
        for row in successful:
            if self._classify(row) == "content":
                buyer_history.setdefault(str(row["customer_commerce_profile_id"]), []).append(row)
        for row in purchases:
            buyer = str(row["customer_commerce_profile_id"])
            buyer_rows.setdefault(buyer, {
                "customerCommerceProfileId": buyer,
                "externalFanvueUserUuid": str(row.get("external_fanvue_user_uuid") or ""),
                "qualifyingPurchaseCountInPeriod": period_count.get(buyer, 0),
                "qualifyingRevenueMinorInPeriod": 0,
            })
            buyer_rows[buyer]["qualifyingRevenueMinorInPeriod"] += int(row.get("gross_minor") or 0)
        for buyer, summary in buyer_rows.items():
            history = sorted(buyer_history[buyer], key=lambda item: item["payment_timestamp"])
            summary.update({"firstPurchaseAt": history[0]["payment_timestamp"],
                "firstPurchaseAmountMinor": int(history[0].get("gross_minor") or 0),
                "latestPurchaseAt": history[-1]["payment_timestamp"],
                "latestPurchaseAmountMinor": int(history[-1].get("gross_minor") or 0),
                "latestPurchaseType": history[-1].get("purchase_source")})
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
        people_by_id={int(person['telegramUserId']):person for person in people_all}
        def aggregate(events):
            result={}
            for event in events:
                key=int(event['telegram_user_id']); person=people_by_id.get(key,{})
                current=result.setdefault(key,{"telegramUserId":key,"messageCount":0,"latestActivityAt":event['occurred_at'],
                    "lastChatAt":event['occurred_at'],"displayName":person.get('displayName'),"username":person.get('username'),
                    "fanvueUserId":person.get('fanvueUserId'),"buyerStatus":person.get('buyerStatus')})
                current['messageCount']+=1;current['latestActivityAt']=max(current['latestActivityAt'],event['occurred_at'])
            return list(result.values())
        return resolved, {"people_all": people_all, "active_people": active,
            "new_people": new, "returning_people": returning,
            "period_inbound": period_inbound, "period_ava": period_ava,
            "message_people":aggregate(period_inbound),"ava_message_people":aggregate(period_ava),
            "transactions": transactions, "content": classified["content"],
            "tips": classified["tip"], "subscriptions": classified["subscription"],
            "unclassified": classified["unclassified"], "purchases": purchases,
            "unique_buyers": unique_buyers, "new_buyers": new_buyers,
            "repeat_buyers": repeat_buyers, "buyer_rows": buyer_rows, "offers": offers,
            "purchased_offers": purchased_offers,
            "would_have_sold": would, "excluded_test_count": len(excluded)}

    def _contexts(self,*,creator_profile_id,fanvue_account_id):
        reader=getattr(self.repository,'business_customer_contexts',None)
        rows=reader(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id) if callable(reader) else []
        result={}
        for row in rows:
            for key in (str(row.get('customer_commerce_profile_id') or ''),str(row.get('external_fanvue_user_uuid') or ''),f"telegram:{row.get('telegram_user_id')}"):
                if key and key!='telegram:None':result[key]=row
        return result

    @staticmethod
    def _business_row(metric,row,contexts,creator_profile_id,fanvue_account_id):
        profile=str(row.get('customer_commerce_profile_id') or row.get('customerCommerceProfileId') or '')
        external=str(row.get('external_fanvue_user_uuid') or row.get('externalFanvueUserUuid') or '')
        telegram=row.get('telegram_user_id') or row.get('telegramUserId')
        context=contexts.get(profile) or contexts.get(external) or contexts.get(f'telegram:{telegram}') or {}
        customer_id=context.get('local_fanvue_user_id') or row.get('fanvueUserId')
        display=context.get('canonical_display_name') or context.get('canonical_username') or context.get('provider_display_name') or context.get('provider_handle') or row.get('displayName') or row.get('username') or 'Unresolved Customer'
        handle=context.get('canonical_username') or context.get('provider_handle') or row.get('username')
        has_conversation=bool(context.get('has_conversation')) or bool(row.get('lastChatAt'))
        customer_key=f'customer:{creator_profile_id}:{fanvue_account_id}:{customer_id}' if customer_id else None
        conversation_key=f'telegram:{creator_profile_id}:{fanvue_account_id}:{telegram}' if telegram and has_conversation else None
        event_types={'TIPS':'Tip','PURCHASES':'Content Purchase','CONTENT_REVENUE':'Content Purchase','TOTAL_REVENUE':'Payment','SUBSCRIPTIONS_RENEWALS':'Subscription / Renewal','OFFERS_PRESENTED':'Offer Presented','OFFERS_PURCHASED':'Offer Purchased','NEW_BUYERS':'New Buyer','REPEAT_BUYERS':'Repeat Buyer','UNIQUE_BUYERS':'Unique Buyer','ACTIVE_PEOPLE':'Customer Activity','NEW_PEOPLE':'New Conversation','RETURNING_PEOPLE':'Returning Customer','CUSTOMER_MESSAGES':'Customer Messages','AVA_MESSAGES':'Ava Messages','OFFER_CONVERSION':'Offer Conversion'}
        gross=row.get('gross_minor') if row.get('gross_minor') is not None else row.get('realized_amount_minor')
        occurred=(row.get('latestPurchaseAt') if metric=='REPEAT_BUYERS' else
                  row.get('firstPurchaseAt') if metric=='NEW_BUYERS' else
                  row.get('payment_timestamp') or row.get('presented_at') or row.get('latestActivityAt') or row.get('lastChatAt'))
        status=row.get('offerConversionStatus') or row.get('payment_status') or row.get('status') or ('Resolved' if customer_id else 'Needs Identity Review')
        source=str(row.get('purchase_source') or '')
        attribution=('ATTRIBUTED' if int(row.get('attributed_asset_count') or 0)>0 else
                     'UNATTRIBUTED') if metric in {'PURCHASES','CONTENT_REVENUE'} else None
        event_label=row.get('offering_title') or event_types.get(metric,metric.replace('_',' ').title())
        return {'rowKey':str(row.get('record_id') or row.get('personKey') or profile or f'{metric}:{telegram}'),
          'customer':{'resolved':bool(customer_id),'rowKey':customer_key,'displayName':display,'handle':handle,'platform':'FANVUE' if profile or external else 'TELEGRAM','buyerStatus':context.get('profile_state') or row.get('buyerStatus') or 'PROSPECT'},
          'event':{'type':event_types.get(metric,metric.replace('_',' ').title()),'label':event_label,'grossMinor':int(gross) if gross is not None else row.get('firstPurchaseAmountMinor') if metric=='NEW_BUYERS' else row.get('latestPurchaseAmountMinor') if metric=='REPEAT_BUYERS' else None,'netMinor':int(row['net_minor']) if row.get('net_minor') is not None else None,'occurredAt':occurred or row.get('firstPurchaseAt') or row.get('latestPurchaseAt'),'status':str(status).replace('_',' ').title(),'purchaseType':(source or str(row.get('latestPurchaseType') or '')).replace('_',' ').replace('mediaLink','Media Link').title(),'attributionState':attribution,'messageCount':row.get('messageCount'),'presented':row.get('presented'),'purchased':row.get('purchased'),'conversionRate':row.get('conversionRate')},
          'context':{'lifetimeGrossMinor':int(context.get('lifetime_gross_minor') or row.get('qualifyingRevenueMinorInPeriod') or 0),'transactionCount':int(context.get('purchase_count') or row.get('qualifyingPurchaseCountInPeriod') or 0),'firstPurchaseAt':context.get('first_purchase_at') or row.get('firstPurchaseAt'),'latestPurchaseAt':context.get('last_purchase_at') or row.get('latestPurchaseAt'),'repeatBuyer':int(context.get('purchase_count') or row.get('qualifyingPurchaseCountInPeriod') or 0)>1},
          'navigation':{'customerKey':customer_key,'conversationKey':conversation_key},
          'developerDetails':{k:str(v) for k,v in row.items() if k in {'record_id','transaction_order_id','customer_commerce_profile_id','external_fanvue_user_uuid','purchase_intent_id','commercial_offering_id'} and v is not None}}

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
