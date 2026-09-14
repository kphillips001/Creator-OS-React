"""Unified, source-aware read composition for customer knowledge."""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from app.models.customer_snapshot import CustomerSnapshot, CustomerSnapshotItem
from app.repositories.customer_snapshot_repository import CustomerSnapshotRepository
from app.services.customer_snapshot_policy import CustomerSnapshotPolicy


class CustomerSnapshotService:
    SECTION_ORDER = (
        "PERSONAL", "INTERESTS", "PREFERENCES", "RELATIONSHIP_WITH_AVA",
        "THINGS_TO_REMEMBER", "RECENT_LEARNINGS", "SILENT_CONTEXT",
        "RELEVANT_CREATOR_FACTS",
    )

    def __init__(self, *, repository=None, recent_limit=5,
                 clock=lambda: datetime.now(timezone.utc)):
        self.repository = repository or CustomerSnapshotRepository()
        self.recent_limit = max(1, min(int(recent_limit), 10))
        self.clock = clock

    def for_customer(self, *, creator_profile_id, fanvue_account_id, customer_id):
        mapping, prospect, facts = self.repository.canonical_sources(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            customer_id=customer_id,
        )
        return self._compose(
            creator_profile_id=creator_profile_id,
            subject_id=str(customer_id), prospect=prospect, facts=facts,
            mapping_state="MAPPED_VERIFIED" if mapping else "CANONICAL_UNMAPPED",
            identity={"subjectType": "CUSTOMER", "customerId": str(customer_id),
                      "telegramUserId": None if mapping is None else str(mapping.telegram_user_id)},
        )

    def for_prospect(self, *, creator_profile_id, fanvue_account_id,
                     telegram_user_id):
        prospect, facts = self.repository.prospect_sources(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        if prospect is None:
            raise LookupError("Telegram prospect not found")
        if prospect.graduated_mapping_id is not None:
            raise ValueError("Mapped prospect must be opened through its canonical customer")
        return self._compose(
            creator_profile_id=creator_profile_id,
            subject_id=str(telegram_user_id), prospect=prospect, facts=facts,
            mapping_state="TELEGRAM_PROSPECT_NOT_MAPPED",
            identity={"subjectType": "TELEGRAM_PROSPECT",
                      "telegramUserId": str(telegram_user_id),
                      "status": "TELEGRAM PROSPECT — NOT MAPPED"},
            include_customer_facts=False,
        )

    def _compose(self, *, creator_profile_id, subject_id, prospect, facts,
                 mapping_state, identity, include_customer_facts=True):
        included, excluded = self._telegram_items(prospect, subject_id)
        canonical = []
        creator_facts = []
        for fact in facts or ():
            if fact["subject_type"] == "CUSTOMER" and not include_customer_facts:
                continue
            if fact["subject_type"] == "CREATOR":
                creator_facts.append(fact)
            else:
                canonical.append(self._canonical_item(fact))
        included, duplicate_exclusions = self._deduplicate(included, canonical)
        excluded.extend(duplicate_exclusions)
        included.extend(canonical)
        included.extend(self._canonical_item(fact) for fact in creator_facts
                        if self._creator_fact_relevant(fact, included))
        recent_candidates = [item for item in included
                             if item.source_authority == "TELEGRAM_CONVERSATIONAL_MEMORY"
                             and item.section != "THINGS_TO_REMEMBER"]
        recent = sorted(recent_candidates, key=lambda item: item.last_observed_at or item.observed_at or "",
                        reverse=True)[:self.recent_limit]
        included.extend(replace(item, item_id="recent:" + item.item_id,
                                section="RECENT_LEARNINGS") for item in recent)
        sections = {}
        for section in self.SECTION_ORDER:
            values = tuple(item for item in included if item.section == section)
            if values:
                sections[section] = values
        sources = tuple(sorted({item.source_authority for item in included}))
        return CustomerSnapshot(identity, sections, tuple(excluded), sources,
                                mapping_state)

    def _telegram_items(self, prospect, subject_id):
        if prospect is None:
            return [], []
        state = dict(prospect.preference_state or {})
        records = list(state.get("records") or ())
        prospect_id = str(getattr(prospect, "telegram_sales_prospect_id", ""))
        included, excluded, eligible = [], [], []
        for index, record in enumerate(records):
            reason = CustomerSnapshotPolicy.telegram_eligibility(record)
            if reason:
                excluded.append(self._telegram_item(
                    record, subject_id, index, prospect_id=prospect_id,
                    exclusion_reason=reason))
            else:
                eligible.append((index, record))
        pet_records = [(index, record) for index, record in eligible
                       if record.get("category") in {"pet", "entity"}]
        if pet_records:
            entity = next((pair for pair in pet_records
                           if pair[1].get("category") == "entity"), None)
            if entity:
                included.append(self._telegram_item(
                    entity[1], subject_id, entity[0], prospect_id=prospect_id))
                for index, record in pet_records:
                    if (index, record) != entity:
                        excluded.append(self._telegram_item(
                            record, subject_id, index,
                            prospect_id=prospect_id,
                            exclusion_reason="Duplicate of composed pet entity"))
            else:
                values = {record.get("key"): record.get("value")
                          for _, record in pet_records}
                base_index, base = pet_records[0]
                composed = dict(base)
                composed.update(category="entity", key=str(values.get("pet_name") or "pet").lower(),
                                value={"name": values.get("pet_name") or "Pet",
                                       "type": values.get("pet_type") or "pet",
                                       "breed": values.get("pet_breed"),
                                       "relationship": "customer's " + str(values.get("pet_type") or "pet")})
                included.append(self._telegram_item(
                    composed, subject_id, base_index, prospect_id=prospect_id))
            eligible = [(index, record) for index, record in eligible
                        if record.get("category") not in {"pet", "entity"}]
        included.extend(self._telegram_item(
                            record, subject_id, index, prospect_id=prospect_id)
                        for index, record in eligible)
        return included, excluded

    def _telegram_item(self, record, subject_id, index, *, prospect_id="",
                       exclusion_reason=None):
        category, key, value = record.get("category"), record.get("key"), record.get("value")
        section, label, description, attributes = "PREFERENCES", str(value), key, {}
        inferred = record.get("source") == "deterministic_location_inference"
        lifecycle = "CURRENT"
        if category == "fact":
            section = "PERSONAL"; label = str(value)
            description = "Timezone · Inferred from location" if key == "timezone" else "Customer location"
        elif category == "entity":
            section = "PERSONAL"; attributes = dict(value or {})
            label = str(attributes.get("name") or "Pet")
            breed = str(attributes.get("breed") or attributes.get("type") or "Pet").title()
            description = f"{breed} · Customer's {attributes.get('type') or 'pet'}"
        elif category in {"hobby", "interest"}:
            section = "INTERESTS"; label = str(value).title(); description = category.title()
        elif category == "routine":
            section = "PREFERENCES"; label = str(value); description = "Ordinary routine"
        elif category == "preference":
            section = "PREFERENCES"; label = str(value)
            description = "Music preference" if record.get("metadata", {}).get("domain") == "music" else "Preference"
        elif category == "event":
            section = "THINGS_TO_REMEMBER"; attributes = dict(value or {})
            label = f"{attributes.get('subject')} — {attributes.get('event')}"
            description = str(attributes.get("originalTemporalText") or attributes.get("scheduledFor"))
            lifecycle = str(attributes.get("status") or "upcoming").upper()
        return CustomerSnapshotItem(
            item_id=f"telegram:{prospect_id}:{key}:{index}",
            subject_type="CUSTOMER", subject_id=subject_id, section=section,
            label=label, description=description, value=value, attributes=attributes,
            source_authority="TELEGRAM_CONVERSATIONAL_MEMORY",
            source_platform="TELEGRAM", confidence=float(record.get("confidence") or 0),
            lifecycle_status=lifecycle, observed_at=record.get("observedAt"),
            last_observed_at=record.get("lastObservedAt") or record.get("observedAt"),
            correctable=False,
            native_reference={"store": "telegram_sales_prospects.preference_state",
                              "prospectId": prospect_id,
                              "category": category, "key": key},
            inferred=inferred, exclusion_reason=exclusion_reason,
        )

    @staticmethod
    def _canonical_item(fact):
        creator = fact["subject_type"] == "CREATOR"
        silent = fact["usage_policy"] == "SILENT_CONTEXT"
        customer_sections = {
            "IDENTITY_CONTEXT": "PERSONAL",
            "PREFERENCE": "PREFERENCES",
            "RELATIONSHIP": "RELATIONSHIP_WITH_AVA",
            "RECURRING_BEHAVIOR": "RELATIONSHIP_WITH_AVA",
        }
        section = ("SILENT_CONTEXT" if silent else
                   "RELEVANT_CREATOR_FACTS" if creator else
                   customer_sections.get(fact["category"], "RELATIONSHIP_WITH_AVA"))
        return CustomerSnapshotItem(
            item_id="canonical:" + str(fact["fact_id"]),
            subject_type=fact["subject_type"], subject_id=str(fact["subject_id"]),
            section=section, label=fact["object_value"],
            description=str(fact["relation"]).replace("_", " ").title(),
            value=fact["object_value"], attributes=dict(fact.get("attributes") or {}),
            source_authority=("CREATOR_FACT" if creator else "CANONICAL_RELATIONSHIP_FACT"),
            source_platform=fact["source_platform"], confidence=float(fact["confidence"]),
            usage_policy=fact["usage_policy"], lifecycle_status=fact["state"],
            observed_at=str(fact.get("observed_at") or "") or None,
            last_observed_at=str(fact.get("updated_at") or fact.get("verified_at") or "") or None,
            correctable=True,
            native_reference={"store": "canonical_relationship_facts",
                              "factId": str(fact["fact_id"])},
        )

    @classmethod
    def _deduplicate(cls, telegram, canonical):
        canonical_keys = {cls._semantic_key(item) for item in canonical
                          if item.subject_type == "CUSTOMER"}
        retained, excluded = [], []
        for item in telegram:
            if cls._semantic_key(item) in canonical_keys:
                excluded.append(replace(
                    item, exclusion_reason="Duplicate of higher-authority canonical fact"))
            else:
                retained.append(item)
        return retained, excluded

    @staticmethod
    def _semantic_key(item):
        relation = str(item.description).lower().replace(" ", "_")
        if (relation == "owns_pet"
                or str(item.attributes.get("relationship") or "").startswith("customer's ")):
            return frozenset(("owned_pet", str(item.label).strip().lower()))
        text = " ".join((item.label, item.description,
                         str(item.attributes.get("type") or "")))
        return frozenset(token for token in re.findall(r"[a-z0-9]+", text.lower())
                         if token not in {"customer", "the", "ava", "owns", "relationship"})

    @classmethod
    def _creator_fact_relevant(cls, creator_fact, customer_items):
        """Require an explicit object or alias reference in eligible customer context."""
        references = [creator_fact.get("object_value")]
        references.extend((creator_fact.get("object_data") or {}).get("aliases") or ())
        references.extend((creator_fact.get("attributes") or {}).get("aliases") or ())
        needles = [cls._normalized_phrase(value) for value in references
                   if cls._normalized_phrase(value)]
        if not needles:
            return False
        context = " ".join(cls._flatten_text((item.label, item.description,
                                               item.value, item.attributes))
                           for item in customer_items
                           if item.subject_type == "CUSTOMER")
        normalized_context = " " + cls._normalized_phrase(context) + " "
        return any((" " + needle + " ") in normalized_context for needle in needles)

    @staticmethod
    def _normalized_phrase(value):
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

    @classmethod
    def _flatten_text(cls, value):
        if isinstance(value, Mapping):
            return " ".join(cls._flatten_text(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return " ".join(cls._flatten_text(item) for item in value)
        return str(value or "")
