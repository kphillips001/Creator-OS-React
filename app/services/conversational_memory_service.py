"""Durable Telegram-native relationship memory for pre-purchase prospects."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.services.conversational_memory_domain_classifier import (
    ConversationalMemoryDomainClassifier,
)


class ConversationalMemoryService:
    """Persist versioned facts separately from commerce/behavior memory."""

    # This source is watched by the local development launcher; edits are
    # loaded by both FastAPI and the independently supervised worker runtime.
    SCHEMA_VERSION = 2
    _WEEKDAYS = {name.lower(): i for i, name in enumerate(
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))}
    _STOPWORDS = {"about", "actually", "again", "also", "and", "are", "been", "for",
                  "from", "have", "into", "just", "lately", "like", "mostly", "that",
                  "the", "their", "this", "with", "your"}
    _MEMORY_PRIORITY_LIMITS = {
        "STANDARD": 6,
        "ELEVATED": 8,
        "HIGH": 10,
        "HIGHEST": 12,
    }

    def __init__(self, *, repository=None, clock=lambda: datetime.now(timezone.utc)):
        self.repository = repository or TelegramSalesProspectRepository()
        self._clock = clock

    def learn(self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
              telegram_chat_id, message_text, observed_at=None,
              memory_priority="STANDARD"):
        existing = self.repository.get(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, telegram_user_id=telegram_user_id)
        if existing is None:
            existing = self.repository.observe(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id, telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id)
        state = self._normalize_state(dict(existing.preference_state or {}))
        at = observed_at or self._clock()
        superseded_before = sum(
            record.get("status") == "superseded" for record in state["records"]
        )
        records = self.extract_records(
            message_text, observed_at=at, customer_timezone=state.get("timezone"),
            active_records=[record for record in state["records"]
                            if record.get("status") == "current"],
        )
        disclosure = self.classify_customer_self_disclosure(message_text)
        invalid_capture_rejected = self._invalid_preference_capture_rejected(
            message_text, records
        )
        written = self._merge_records(state, records)
        self._refresh_event_lifecycle(state, at)
        corrections = max(0, sum(
            record.get("status") == "superseded" for record in state["records"]
        ) - superseded_before)
        location_record = next(
            (record for record in records if record.get("key") == "location"), None,
        )
        timezone_record = next(
            (record for record in records if record.get("key") == "timezone"), None,
        )
        state["lastExtraction"] = {
            "observedAt": at.isoformat(), "written": written,
            "extractedCount": len(records), "persistedCount": len(written),
            "correctionsApplied": corrections,
            "invalidMemoryCaptureRejected": invalid_capture_rejected,
            "locationTimezoneInference": ({
                "location": location_record.get("value"),
                "timezone": timezone_record.get("value") if timezone_record else None,
                "resolved": bool(timezone_record and timezone_record.get("value")),
            } if location_record else None),
            "eventsExtracted": [record.get("value") for record in records
                                if record.get("category") == "event"],
            "eventPersistence": self._event_persistence_diagnostic(
                message_text, records,
            ),
            "customerSelfDisclosure": {
                **disclosure,
                "memoryCandidateCreated": bool(records) and disclosure["detected"],
                "memoryCandidateType": sorted({
                    record.get("category") for record in records
                }) if disclosure["detected"] else [],
                "memoryPersisted": bool(written) and disclosure["detected"],
                "memoryRetrievalEligible": bool(
                    disclosure["detected"]
                    and disclosure["persistenceDecision"] == "PERSIST"
                    and written
                ),
            },
        }
        if records or dict(existing.preference_state or {}) != state:
            updated = self.repository.merge_conversational_memory(
                creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id, values=state)
            state = self._normalize_state(dict(updated.preference_state or state))
        return self.retrieve(
            state, message_text, now=at, memory_priority=memory_priority,
        )

    @classmethod
    def extract(cls, text):
        state = cls._normalize_state({})
        cls._merge_records(state, cls.extract_records(text))
        return cls._projection(state)

    @classmethod
    def extract_records(cls, text, *, observed_at=None, customer_timezone=None,
                        active_records=()):
        at = observed_at or datetime.now(timezone.utc)
        message = str(text or "").strip()
        normalized = message.replace("’", "'")
        normalized = cls._normalize_apostrophes(normalized)
        lowered = normalized.lower()
        records = []

        disclosure = cls.classify_customer_self_disclosure(normalized)
        if (disclosure["detected"]
                and disclosure["persistenceDecision"] == "PERSIST"):
            for item in disclosure["memoryCandidates"]:
                records.append(cls._record(
                    item["category"], item["key"], item["value"], message, at,
                    item.get("confidence", .9), {
                        "domain": disclosure["domain"].lower(),
                        "significance": disclosure["significance"],
                        "disclosureEvidence": disclosure["evidence"],
                        "retrievalEligible": True,
                    }, source="customer_self_disclosure",
                ))

        location = re.search(
            r"\b(?:i(?:'m| am)\s+(?:from|in)|i live in|i moved (?:from .+? )?to)\s+"
            r"([a-z][a-z .'-]{1,45}?)(?=,|\s+so\b|\s+and\b|[.!?]|$)", lowered)
        resolved_here = None
        if location is None:
            # "Here in <place>" is current-location evidence only when the
            # existing IANA locality resolver confirms an unambiguous place.
            # This intentionally rejects contextual phrases such as "here in
            # the chat", "here in bed", or "here in my room".
            here = re.search(
                r"\bhere\s+in\s+([a-z][a-z .'-]{1,45}?)"
                r"(?=\s*(?:,|\u2014|\u2013|\s+so\b|\s+and\b|[.!?]|$))",
                lowered,
            )
            if here is not None:
                candidate = re.sub(r"\s+", " ", here.group(1).strip())
                resolved_here = cls.resolve_location(candidate)
                if resolved_here is not None:
                    location = here
        if location:
            raw_place = re.sub(r"\s+", " ", location.group(1).strip())
            resolved = resolved_here or cls.resolve_location(raw_place)
            place = resolved[0] if resolved else raw_place.title()
            records.append(cls._record(
                "fact", "location", place, message, at, .98,
            ))
            records.append(cls._record(
                "fact", "timezone", resolved[1] if resolved else None,
                message, at, .99 if resolved else .0,
                {"inference": "IANA_LOCALITY", "resolved": bool(resolved)},
                source="deterministic_location_inference",
            ))

        color = re.search(r"\bmy favou?rite colou?r is ([a-z][a-z -]{1,24})", lowered)
        if color:
            records.append(cls._record("preference", "favorite_color",
                                       color.group(1).strip(), message, at))

        pet_records = cls._extract_pet_records(normalized, message, at)
        records.extend(pet_records)

        # Generic possessive entity relation: "my <type> <proper name>".
        entity = None if pet_records else re.search(
            r"\b[Mm]y\s+([a-z][a-z-]{1,24})\s+([A-Z][a-zA-Z'-]{1,30})\b",
            normalized,
        )
        if entity is None and not pet_records:
            named = re.search(r"\bi have (?:a|an) ([a-z][a-z -]{1,24}) (?:named|called) ([A-Z][a-zA-Z'-]{1,30})\b", normalized, re.I)
            if named:
                kind, name = named.group(1), named.group(2).title()
                entity = type("EntityMatch", (), {"group": lambda self, n: (kind, name)[n - 1]})()
        if entity:
            kind, name = entity.group(1).strip().lower(), entity.group(2)
            value = {"name": name, "type": kind, "relationship": "customer's " + kind}
            breed = re.search(rf"\b(?:he|she|{re.escape(name)})(?:[' ]s|\s+is)\s+(?:a|an)\s+"
                              r"([a-z][a-z -]{1,40}?)(?=\s+and\b|[.!?]|$)", normalized, re.I)
            if breed: value["breed"] = breed.group(1).strip().lower()
            records.append(cls._record("entity", name.lower(), value, message, at))
            if (re.search(rf"\b(?:walk|walks|walking)\s+(?:my\s+)?{re.escape(name)}\b", normalized, re.I)
                    or re.search(rf"\btake\s+my\s+{re.escape(kind)}\s+{re.escape(name)}\s+for\s+a\s+walk\b", normalized, re.I)):
                records.append(cls._record("routine", f"walk_{name.lower()}",
                                           f"walks {name}", message, at))

        preference_domain = None
        preference = re.search(r"(?<!what )(?<!things )(?<!stuff )\b(?:i(?:'m| am)\s+(?:mostly\s+)?into|i\s+(?:love|like|enjoy|prefer))\s+"
                               r"(.+?)(?=\.|!|\?|\banyway\b|$)", lowered)
        if preference is None:
            preference = re.search(r"\bi(?:'m| am)\s+more of (?:a|an)\s+"
                                   r"(.+?)(?=\s+person\b|[.!?]|$)", lowered)
            if preference is not None:
                preference_domain = "leisure_activity"
        if preference:
            raw_preference = re.sub(
                r"\s+(?:now|then|today|tonight|lately)\s*$", "",
                preference.group(1).strip(" ,"), flags=re.I,
            )
            for value in cls._split_preferences(raw_preference):
                if value.strip().lower() in {"now", "then", "today", "tonight", "lately"}:
                    continue
                metadata = ({"domain": preference_domain}
                            if preference_domain is not None else None)
                records.append(cls._record(
                    "preference", cls._slug(value), value, message, at, .9, metadata,
                ))
        listening = re.search(r"\b(?:i(?:'ve| have)\s+been|been)\s+listening to\s+(?:a lot of\s+)?"
                              r"(.+?)(?=\s+lately\b|[.!?]|$)", normalized, re.I)
        if listening:
            artist = listening.group(1).strip(" ,")
            records.append(cls._record("preference", "music_artist_" + cls._slug(artist),
                artist, message, at, .92, {"domain": "music", "kind": "artist"}))
            # Co-occurring preferences in the same customer statement inherit
            # the subject domain without encoding a particular genre or artist.
            for record in records:
                if record.get("category") == "preference":
                    record.setdefault("metadata", {}).setdefault("domain", "music")

        event = re.search(r"\b(?:i(?:'m| am)\s+)?(?:actually\s+)?(?:taking|going with|bringing)\s+"
                          r"(.+?)\s+(?:to|for)\s+(.+?)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                          normalized, re.I)
        if event:
            subject, purpose, weekday = (v.strip() for v in event.groups())
            detail = re.search(rf"\b{re.escape(weekday)}\s+for\s+(.+?)(?=[.!?]|$)", normalized, re.I)
            if detail: purpose = f"{purpose} for {detail.group(1).strip()}"
            scheduled = cls._next_weekday(at, weekday, customer_timezone)
            value = {"summary": f"{subject} {purpose}", "relatedEntity": subject,
                     "scheduledFor": scheduled.isoformat(), "status": "upcoming",
                     "originalTemporalText": weekday.title()}
            records.append(cls._record("event", cls._slug(subject + "-" + purpose),
                value, message, at, .9, {"temporal": True, "timezone": customer_timezone}))
        records.extend(cls._extract_future_event_records(
            normalized, message, at, customer_timezone, active_records,
            skip_legacy_match=bool(event),
        ))
        # Multiple semantic extractors may recognize the same normalized fact.
        # Preserve the first authoritative record and never emit duplicate keys.
        preference_values = {
            str(record.get("value") or "").strip().lower()
            for record in records if record.get("category") == "preference"
        }
        unique = {}
        for record in records:
            if (record.get("category") == "hobby"
                    and str(record.get("value") or "").strip().lower()
                    in preference_values):
                continue
            unique.setdefault((record.get("category"), record.get("key")), record)
        return list(unique.values())

    @classmethod
    def classify_customer_self_disclosure(cls, text):
        """Classify volunteered facts without treating every I-statement as memory."""
        normalized = cls._normalize_apostrophes(str(text or "").replace("â€™", "'"))
        lowered = normalized.lower()
        evidence, candidates = [], []
        domain, significance = "NONE", "NONE"

        quiet = bool(re.search(r"\bi(?:'m| am)\s+usually\s+(?:pretty\s+)?quiet\s+at first\b", lowered))
        warmup = bool(re.search(r"\b(?:it\s+)?takes me (?:a while|a minute|some time|time)\s+to warm up(?: to (?:people|somebody|someone))?\b", lowered))
        outgoing = bool(re.search(r"\bi(?:'m| am)\s+(?:actually\s+)?really outgoing once i (?:know|get to know) someone\b", lowered))
        if quiet or warmup or outgoing:
            domain, significance = "PERSONALITY_SOCIAL_STYLE", "DURABLE"
            if quiet: evidence.append("QUIET_AT_FIRST")
            if warmup: evidence.append("TAKES_TIME_TO_WARM_UP")
            if outgoing: evidence.append("OUTGOING_AFTER_FAMILIARITY")
            value = (
                "quiet at first and takes time to warm up" if quiet and warmup else
                "quiet at first" if quiet else
                "takes time to warm up to people" if warmup else
                "outgoing once comfortable with someone"
            )
            candidates.append({"category": "trait", "key": "social_style", "value": value,
                               "confidence": .94})
        elif (
            re.search(r"\bi(?:'m| am)\s+(?:kinda |kind of |really )?(?:an? )?outdoors person\b", lowered)
            or re.search(r"\bi(?:'m| am)\s+more of (?:a|an)\s+[^.!?]+\s+person\b", lowered)
            or re.search(r"\bi(?:'m| am)\s+(?:(?:really|big)\s+)?into\s+[^.!?]+", lowered)
            or re.search(r"\bi\s+(?:love|enjoy|play)\s+[^.!?]+", lowered)
            or re.search(r"\b[^.!?]+\s+is probably my favorite thing\b", lowered)
            or re.search(r"\bweekends?\s+are\s+usually\s+[^.!?]+", lowered)
        ):
            domain, significance = "HOBBY_INTEREST", "DURABLE"
            facts = []
            if re.search(r"\boutdoors?\b", lowered): facts.append(("interest", "outdoors", "OUTDOORS"))
            for fact in ("hiking", "camping", "fishing", "guitar"):
                if re.search(rf"\b{fact}\b", lowered):
                    facts.append(("hobby", fact, fact.upper()))
            if re.search(
                r"\b(?:trying|checking out|visiting)\s+(?:a\s+)?new\s+coffee\s+places?\b",
                lowered,
            ):
                facts.append((
                    "interest", "trying new coffee places", "COFFEE_PLACES",
                ))
            if not facts:
                generic = re.search(
                    r"\bi\s+(?:love|enjoy|play)\s+(.+?)(?=[.!?]|$)|"
                    r"\bi(?:'m| am)\s+(?:(?:really|big)\s+)?into\s+(.+?)(?=[.!?]|$)|"
                    r"\b(.+?)\s+is probably my favorite thing\b",
                    lowered,
                )
                raw = next((group for group in generic.groups() if group), "") if generic else ""
                for value in cls._split_preferences(raw.strip(" ,")):
                    facts.append(("interest", cls._slug(value), value.upper()))
            for category, value, marker in facts:
                evidence.append(marker if marker.endswith("_INTEREST") else marker + "_INTEREST")
                candidates.append({"category": category, "key": cls._slug(value),
                                   "value": value, "confidence": .92})
        elif re.search(r"\bi have (?:a|an) .+? (?:named|called) [a-z]", lowered):
            domain, significance, evidence = "PERSONAL_CONTEXT", "DURABLE", ["NAMED_PET_OR_ENTITY"]
        else:
            favorite_band = re.search(r"\b(.+?)\s+(?:are|is) probably my favorite band\b", lowered)
            late_work = re.search(r"\bi work late (?:most nights|usually|a lot)\b", lowered)
            dislike = re.search(r"\bi (?:really\s+)?hate\s+(.+?)(?=[.!?]|$)", lowered)
            if favorite_band:
                artist = favorite_band.group(1).strip(" ,")
                domain, significance, evidence = "MUSIC", "DURABLE", ["FAVORITE_BAND"]
                candidates.append({"category": "preference", "key": "music_artist_" + cls._slug(artist),
                                   "value": artist.title(), "confidence": .94})
            elif late_work:
                domain, significance, evidence = "ROUTINE", "DURABLE", ["RECURRING_LATE_WORK"]
                candidates.append({"category": "routine", "key": "works_late",
                                   "value": "works late most nights", "confidence": .92})
            elif dislike:
                value = dislike.group(1).strip(" ,")
                domain, significance, evidence = "PREFERENCE", "DURABLE", ["STRONG_DISLIKE"]
                candidates.append({"category": "preference", "key": "dislikes_" + cls._slug(value),
                                   "value": "dislikes " + value, "confidence": .92})
            elif re.search(r"\bi(?:'m| am)\s+(?:just\s+)?(?:drinking water|sitting (?:down|on the couch))\b", lowered):
                domain, significance, evidence = "EPHEMERAL_ACTIVITY", "LOW", ["TRIVIAL_CURRENT_STATE"]
            elif re.search(r"\bi clicked (?:it|the button)\b", lowered):
                domain, significance, evidence = "TRANSACTIONAL_ACTION", "LOW", ["BUTTON_ACTION"]

        detected = bool(evidence and domain != "TRANSACTIONAL_ACTION")
        persistence = "PERSIST" if significance == "DURABLE" else "DO_NOT_PERSIST"
        return {
            "detected": detected, "domain": domain, "significance": significance,
            "evidence": evidence, "memoryCandidates": candidates,
            "persistenceDecision": persistence,
            "persistenceReason": (
                "CONTINUITY_RELEVANT_DURABLE_DISCLOSURE" if persistence == "PERSIST"
                else "EPHEMERAL_OR_NON_RELATIONSHIP_DETAIL"
            ),
        }

    @classmethod
    def _extract_future_event_records(cls, normalized, evidence, at,
                                      customer_timezone, active_records,
                                      *, skip_legacy_match=False):
        """Extract explicit customer-continuity plans with bounded subject linkage."""
        lowered = normalized.lower()
        if skip_legacy_match or cls._event_false_positive(lowered):
            return []
        temporal_pattern = (
            r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"weekend|month)|tomorrow|this\s+weekend|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        )
        existing_event = cls._single_relevant_event(active_records)
        cancellation = re.search(
            r"\b(?:the\s+)?(?:vet\s+|doctor\s+)?appointment\s+"
            r"(?:got\s+|was\s+|is\s+)?cancel(?:led|ed)\b",
            lowered,
        )
        if cancellation and existing_event:
            value = dict(existing_event["value"])
            value.update(status="cancelled", cancelledAt=at.isoformat())
            return [cls._record(
                "event", existing_event["key"], value, evidence, at, .99,
                {"temporal": True, "timezone": customer_timezone,
                 "correction": "CANCELLED"},
            )]
        temporal = re.search(rf"\b({temporal_pattern})\b", lowered)
        if temporal is None:
            return []
        temporal_text = re.sub(r"\s+", " ", temporal.group(1).strip())
        correction = re.search(
            rf"\b(?:actually\s+)?(?:his|her|their|the)\s+appointment\s+"
            rf"(?:got\s+)?(?:moved|rescheduled)\s+to\s+({temporal_pattern})\b",
            lowered,
        ) or re.search(
            rf"\bit(?:'s| is)\s+actually\s+({temporal_pattern})\s*,?\s+not\s+"
            rf"(?:{temporal_pattern})\b", lowered,
        )
        if correction and existing_event:
            temporal_text = correction.group(1)
            return [cls._event_record(
                existing_event["value"].get("subject") or "customer",
                existing_event["value"].get("event") or "appointment",
                temporal_text, evidence, at, customer_timezone,
                confidence=.98, metadata={"correction": "RESCHEDULED"},
            )]
        subject = activity = None
        known_pet = cls._known_pet(active_records)
        possessive = re.search(
            rf"\b(he|she|[A-Z][a-zA-Z'-]{{1,30}})(?:'s\s+got|\s+has(?:\s+got)?)\s+"
            rf"(?:a|an)\s+(.+?)\s+({temporal_pattern})\b",
            normalized, re.I,
        )
        if possessive:
            raw_subject, activity = possessive.group(1), possessive.group(2)
            if raw_subject.lower() in {"he", "she"}:
                subject = known_pet
                if subject is None:
                    return []
            else:
                subject = raw_subject.title()
        if subject is None:
            direct_pet = re.search(
                rf"\bmy\s+(dog|cat|puppy|kitten)\s+"
                rf"(?:has|has\s+got|gets|is\s+getting)\s+(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            )
            if direct_pet:
                subject = known_pet or "customer's " + direct_pet.group(1).lower()
                activity = direct_pet.group(2)
        if subject is None:
            relation = re.search(
                rf"\bmy\s+(sister|brother|mom|mother|dad|father|partner|friend)\s+"
                rf"(?:is\s+|will\s+be\s+)(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            )
            if relation:
                subject = "customer's " + relation.group(1).lower()
                activity = relation.group(2)
        if subject is None:
            tentative_entity = re.search(
                rf"\bi\s+think\s+([A-Z][a-zA-Z'-]{{1,30}})(?:'s|\s+has)\s+"
                rf"(.+?)\s+(?:is\s+)?({temporal_pattern})\b",
                normalized, re.I,
            )
            if tentative_entity:
                candidate = tentative_entity.group(1).title()
                if known_pet and candidate == known_pet:
                    subject, activity = known_pet, tentative_entity.group(2)
        if subject is None:
            customer = re.search(
                rf"\b(?:i(?:'ve| have)\s+got|i\s+have|i\s+might\s+have|"
                rf"i\s+may\s+have)\s+(?:an|a|my)?\s*"
                rf"(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            ) or re.search(
                rf"\bi(?:'m| am)\s+(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            ) or re.search(
                rf"\bwe(?:'re| are)\s+(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            ) or re.search(
                rf"\bwe\s+(?:might|may)\s+have\s+(.+?)\s+({temporal_pattern})\b",
                normalized, re.I,
            ) or re.search(
                rf"\bmy\s+birthday\s+is\s+({temporal_pattern})\b",
                normalized, re.I,
            )
            if customer:
                subject = "customer"
                activity = "birthday" if "birthday" in customer.group(0).lower() else customer.group(1)

        if not subject or not activity:
            return []
        activity = cls._canonical_event_activity(activity)
        if not activity or not cls._event_worthy(
            activity, evidence=evidence, subject=subject,
        ):
            return []
        subject_domain = "pet" if known_pet and subject == known_pet else (
            "entity" if subject != "customer" else None
        )
        return [cls._event_record(
            subject, activity, temporal_text, evidence, at, customer_timezone,
            metadata={"subjectDomain": subject_domain} if subject_domain else None,
        )]

    @staticmethod
    def _event_false_positive(lowered):
        if re.search(r"\b(?:favorite\s+song|movie\s+comes\s+out|hate\s+mondays|"
                     r"charlie\s+brown|vet\s+bills|tomorrow\s+never\s+knows|"
                     r"every\s+day\s+is\s+friday)\b", lowered):
            return True
        return bool(re.search(r"\b(?:might\s+maybe|maybe\s+i|someday|one\s+of\s+these\s+days)\b", lowered))

    @classmethod
    def _event_record(cls, subject, activity, temporal_text, evidence, at,
                      customer_timezone, confidence=.94, metadata=None):
        resolved = cls._resolve_future_temporal(at, temporal_text, customer_timezone)
        value = {
            "subject": subject, "event": activity,
            "summary": f"{subject} has {activity}",
            "originalTemporalText": temporal_text,
            "scheduledFor": resolved.get("scheduledFor"),
            "resolutionPrecision": resolved.get("precision"),
            "temporalCertainty": (
                "TENTATIVE" if re.search(
                    r"\b(?:maybe|possibly|sometime|probably|might|may|i think)\b",
                    str(evidence), re.I,
                ) else "STATED"
            ),
            "status": "upcoming", "completionVerified": False,
        }
        event_metadata = {"temporal": True,
                          "timezone": resolved.get("timezone"),
                          "timezoneSource": resolved.get("timezoneSource")}
        event_metadata.update(metadata or {})
        return cls._record(
            "event", cls._slug(str(subject) + "-" + str(activity)), value,
            evidence, at, confidence, event_metadata,
        )

    @staticmethod
    def _canonical_event_activity(value):
        activity = re.sub(r"\s+", " ", str(value).strip(" ,.!?" ).lower())
        activity = re.sub(
            r"^(?:(?:probably|maybe|possibly)\s+)?(?:just\s+)?", "", activity,
        )
        activity = re.sub(r"^(?:going\s+to|will\s+be)\s+", "", activity)
        activity = re.sub(r"^(?:a|an)\s+", "", activity)
        if not activity or len(activity) > 80:
            return None
        return activity

    @staticmethod
    def _event_worthy(activity, *, evidence, subject):
        text = str(activity or "").lower()
        weak = re.search(
            r"\b(?:chill|relax|take it easy|watch tv|do something|grab some food|"
            r"pretty quiet|be quiet|stay in|nothing|no plans)\b", text,
        )
        if weak:
            return False
        significant = re.search(
            r"\b(?:appointment|reservation|reservations|trip|flight|flying|meeting|"
            r"interview|doctor|vet|visit|groomed|grooming|concert|camping|birthday|"
            r"wedding|procedure|surgery|exam|travel|visiting)\b", text,
        )
        explicit_commitment = re.search(
            r"\b(?:going|flying|traveling|travelling|leaving|meeting|visiting|"
            r"attending|starting)\b", text,
        )
        known_entity_commitment = str(subject or "") != "customer" and bool(
            re.search(r"\b(?:appointment|visit|groomed|meeting|interview)\b", text)
        )
        return bool(significant or explicit_commitment or known_entity_commitment)

    @classmethod
    def _event_persistence_diagnostic(cls, message, records):
        if any(record.get("category") == "event" for record in records):
            return {"rejected": False, "reason": None}
        text = cls._normalize_apostrophes(str(message or "")).lower()
        temporal = re.search(
            r"\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|"
            r"friday|saturday|sunday|this weekend|next weekend|next month)\b", text,
        )
        candidate = temporal and re.search(
            r"\b(?:i(?:'m| am|'ll| will)|we(?:'re| are|'ll| will)|maybe|probably|might)\b",
            text,
        )
        return {
            "rejected": bool(candidate),
            "reason": "INSUFFICIENT_CONTINUITY_SIGNIFICANCE" if candidate else None,
        }

    @staticmethod
    def _known_pet(active_records):
        names = [str(record.get("value")) for record in active_records
                 if record.get("category") == "pet"
                 and record.get("key") == "pet_name"
                 and record.get("status") == "current"]
        return names[0] if len(set(names)) == 1 else None

    @staticmethod
    def _single_relevant_event(active_records):
        events = [record for record in active_records
                  if record.get("category") == "event"
                  and record.get("status") == "current"
                  and (record.get("value") or {}).get("status") == "upcoming"]
        return events[0] if len(events) == 1 else None

    @classmethod
    def _resolve_future_temporal(cls, at, phrase, customer_timezone):
        source = "CUSTOMER_TIMEZONE" if customer_timezone else "UTC_FALLBACK"
        zone_name = customer_timezone or "UTC"
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone_name, zone, source = "UTC", ZoneInfo("UTC"), "UTC_FALLBACK"
        current = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        local = current.astimezone(zone)
        phrase = str(phrase).lower().strip()
        if phrase == "tomorrow":
            target = local + timedelta(days=1); precision = "DATE"
        elif phrase in cls._WEEKDAYS or phrase.startswith("next ") and phrase[5:] in cls._WEEKDAYS:
            weekday = phrase.removeprefix("next ")
            days = (cls._WEEKDAYS[weekday] - local.weekday()) % 7 or 7
            if phrase.startswith("next ") and days < 7:
                days += 7
            target = local + timedelta(days=days); precision = "DATE"
        elif phrase in {"this weekend", "next weekend"}:
            days = (5 - local.weekday()) % 7
            if days == 0 and local.hour >= 12:
                days = 7
            if phrase == "next weekend":
                days += 7
            target = local + timedelta(days=days); precision = "WEEKEND"
        elif phrase == "next month":
            year, month = local.year, local.month + 1
            if month == 13: year, month = year + 1, 1
            target = local.replace(year=year, month=month, day=1); precision = "MONTH"
        else:
            return {"scheduledFor": None, "precision": "UNRESOLVED",
                    "timezone": zone_name, "timezoneSource": source}
        target = target.replace(hour=12, minute=0, second=0, microsecond=0)
        return {"scheduledFor": target.isoformat(), "precision": precision,
                "timezone": zone_name, "timezoneSource": source}

    @classmethod
    def _extract_pet_records(cls, normalized, evidence, at):
        """Extract explicit current-pet ownership without inferring aspiration/metaphor."""
        pet_kind = r"dog|cat|puppy|kitten|golden retriever|labrador retriever|labrador|lab"
        breed = name = pet_type = None

        match = re.search(
            rf"\bi(?:'ve| have)\s+got\s+(?:a|an)\s+({pet_kind})\s+"
            r"(?:named|called)\s+([A-Z][a-zA-Z'-]{1,30})\b",
            normalized, re.I,
        ) or re.search(
            rf"\bi\s+have\s+(?:a|an)\s+({pet_kind})\s+"
            r"(?:named|called)\s+([A-Z][a-zA-Z'-]{1,30})\b",
            normalized, re.I,
        )
        if match:
            kind, name = match.group(1).lower(), match.group(2).title()
            pet_type, breed = cls._pet_kind(kind)
        else:
            match = re.search(
                rf"\bmy\s+(dog|cat|puppy|kitten)\s+([A-Z][a-zA-Z'-]{{1,30}})\s+"
                rf"(?:is|is actually|'s actually)\s+(?:a|an)\s+({pet_kind})\b",
                normalized, re.I,
            )
            if match:
                pet_type, name = cls._pet_kind(match.group(1).lower())[0], match.group(2).title()
                _, breed = cls._pet_kind(match.group(3).lower())
            else:
                match = re.search(
                    rf"\b([A-Z][a-zA-Z'-]{{1,30}})\s+(?:is|is actually|'s actually)\s+"
                    rf"my\s+({pet_kind})\b",
                    normalized, re.I,
                )
                if match:
                    name = match.group(1).title()
                    pet_type, breed = cls._pet_kind(match.group(2).lower())

        # Two-sentence ownership: "I have a golden retriever. His name is Charlie."
        if name is None:
            owned = re.search(rf"\bi\s+have\s+(?:a|an)\s+({pet_kind})\s*[.!?]", normalized, re.I)
            named = re.search(r"\b(?:his|her|their)\s+name\s+is\s+([A-Z][a-zA-Z'-]{1,30})\b", normalized, re.I)
            if owned and named:
                pet_type, breed = cls._pet_kind(owned.group(1).lower())
                name = named.group(1).title()

        # Explicit corrections retain history through the normal key supersession path.
        correction_name = re.search(
            r"\bactually\s+(?:his|her|their)\s+name\s+is\s+"
            r"([A-Z][a-zA-Z'-]{1,30})(?:,?\s+not\s+[A-Z][a-zA-Z'-]{1,30})?\b",
            normalized, re.I,
        )
        if correction_name:
            name = correction_name.group(1).title()
        correction_breed = re.search(
            rf"\b[A-Z][a-zA-Z'-]{{1,30}}(?:'s|\s+is)\s+actually\s+(?:a|an)\s+({pet_kind})"
            rf"(?:,?\s+not\s+(?:a|an)\s+({pet_kind}))?\b",
            normalized, re.I,
        )
        if correction_breed:
            pet_type, breed = cls._pet_kind(correction_breed.group(1).lower())

        result = []
        if name:
            result.append(cls._record("pet", "pet_name", name, evidence, at, .98))
        if breed:
            result.append(cls._record("pet", "pet_breed", breed, evidence, at, .97))
        elif pet_type:
            result.append(cls._record("pet", "pet_type", pet_type, evidence, at, .97))
        if name and (pet_type or breed) and not correction_breed:
            value = {"name": name, "type": pet_type or "pet",
                     "relationship": "customer's " + (pet_type or "pet")}
            if breed:
                value["breed"] = breed
            result.append(cls._record("entity", name.lower(), value, evidence, at, .96,
                                      {"domain": "pet", "compatibilityProjection": True}))
        return result

    @staticmethod
    def _pet_kind(kind):
        normalized = str(kind).strip().lower()
        if normalized in {"dog", "puppy"}:
            return "dog", None
        if normalized in {"cat", "kitten"}:
            return "cat", None
        if normalized in {"labrador", "labrador retriever", "lab"}:
            return "dog", "lab" if normalized == "lab" else normalized
        return "dog", normalized

    @classmethod
    def retrieve(cls, state, message_text, *, now=None, limit=None,
                 memory_priority="STANDARD"):
        state = cls._normalize_state(state)
        normalized_priority = str(memory_priority or "STANDARD").upper()
        if normalized_priority not in cls._MEMORY_PRIORITY_LIMITS:
            normalized_priority = "STANDARD"
        policy_limit = cls._MEMORY_PRIORITY_LIMITS[normalized_priority]
        effective_limit = policy_limit if limit is None else max(1, int(limit))
        cls._refresh_event_lifecycle(state, now or datetime.now(timezone.utc))
        tokens = cls._tokens(message_text)
        recall_request = bool(re.search(
            r"\b(?:remember|remind me|did i tell you|what did i (?:say|tell)|"
            r"you know my|what kind of .+ did i tell|no guessing|"
            r"(?:what|which) (?:breed|kind|type|name|color|colour|city|place|"
            r"location|timezone|music|artist|band|genre) (?:is|was|do|did)|"
            r"where (?:do|did) i (?:live|say|tell)|"
            r"what was (?:that|the) (?:thing|event|appointment|plan))\b",
            str(message_text or "").replace("’", "'").lower(),
        ))
        explicit_memory_reference = bool(re.search(
            r"\b(?:told you|see,? i told you|like i said|remember i said|"
            r"you were right about me|guess i(?:'m| am) not that quiet|"
            r"warm(?:ed|ing)? up eventually)\b",
            cls._normalize_apostrophes(message_text).lower(),
        ))
        active = [r for r in state["records"] if r.get("status") == "current"
                  and not (r.get("category") == "event"
                           and (r.get("value") or {}).get("status") == "cancelled")]
        classification = ConversationalMemoryDomainClassifier.classify(
            message_text, active_records=active,
        )
        projection = cls._projection(state)
        # This count comes from canonical persisted records. Callers must not
        # infer durability from retrieval-projection container keys.
        projection["durableRecordCount"] = sum(
            1 for record in active if record.get("value") not in (None, "")
        )
        selected_domains = set(classification.domains)
        semantic_event_requested = "event" in selected_domains
        temporal_windows = cls._temporal_recall_windows(
            message_text, now or datetime.now(timezone.utc),
            projection.get("timezone"),
        )
        temporal_event_matches = {}
        for record in active:
            if record.get("category") != "event":
                continue
            value = record.get("value") or {}
            if value.get("status") != "upcoming":
                continue
            if cls._event_recall_significance(record) < 2:
                continue
            try:
                scheduled = datetime.fromisoformat(value.get("scheduledFor"))
            except (TypeError, ValueError):
                continue
            matching = [window for window in temporal_windows
                        if window["start"] <= scheduled <= window["end"]]
            if matching:
                temporal_event_matches[id(record)] = matching[0]
        if temporal_event_matches:
            selected_domains.add("event")
        scored = []
        for record in active:
            # Legacy events persisted before the significance gate must obey the
            # same retrieval policy as newly extracted events. Keep the durable
            # record/lifecycle intact, but never promote continuity noise merely
            # because tokens overlap its generated key.
            if (record.get("category") == "event"
                    and cls._event_recall_significance(record) < 2):
                continue
            domains = cls._record_domains(record)
            if not selected_domains.intersection(domains):
                continue
            overlap = len(tokens & cls._tokens(str(record.get("value")) + " " + record.get("key", "")))
            metadata = dict(record.get("metadata") or {})
            if (record.get("key") in {"location", "timezone"}
                    and "location" in selected_domains):
                overlap += 2
            if metadata.get("domain") == "music" and "music" in selected_domains:
                overlap += 2
            if "leisure_activity" in domains and "leisure_activity" in selected_domains:
                overlap += 2
            if record.get("category") == "entity" and "entity" in selected_domains:
                overlap += 3
            if record.get("category") == "pet" and "pet" in selected_domains:
                overlap += 2
            if (record.get("category") == "trait"
                    and "personality_social_style" in selected_domains):
                overlap += 2
                if explicit_memory_reference:
                    overlap += 4
            if (record.get("category") in {"interest", "hobby"}
                    and "hobby_interest" in selected_domains):
                overlap += 2
            if record.get("category") == "event" and "event" in selected_domains:
                temporal_match = temporal_event_matches.get(id(record))
                if temporal_match:
                    overlap += 5 + cls._event_recall_significance(record)
                elif semantic_event_requested and (overlap or recall_request):
                    overlap += 1
                else:
                    continue
            if overlap: scored.append((overlap, record))
        ranked = sorted(scored, key=lambda x: x[0], reverse=True)
        selected = [r for _, r in ranked[:effective_limit]]
        continuity_guidance = cls._continuity_guidance(
            selected, temporal_event_matches=temporal_event_matches,
            explicit_recall=recall_request,
            explicit_reference=explicit_memory_reference,
            classification=classification,
        )
        result = {"timezone": projection.get("timezone"),
                  "durableRecordCount": projection["durableRecordCount"],
                  "knownMemoryDomains": sorted({
                      domain for record in active
                      for domain in cls._record_domains(record) if domain
                  }),
                  "knownMemoryKeys": sorted({
                      str(record.get("key")) for record in active if record.get("key")
                  }),
                  "retrievedMemories": selected,
                  "memoryDiagnostics": {"available": bool(active),
                    "identitySource": "TELEGRAM_NUMERIC_PROSPECT", "retrievedCount": len(selected),
                    "retrievalAttempted": True, "retrievedKeys": [r["key"] for r in selected],
                    "retrievedCategories": sorted({r["category"] for r in selected}),
                    "semanticClassificationAttempted": True,
                    "semanticDomains": sorted(selected_domains),
                    "semanticClassificationConfidence": classification.confidence,
                    "semanticClassificationSource": classification.source,
                    "explicitRecallRequest": recall_request,
                    "explicitMemoryReference": explicit_memory_reference,
                    "recallSatisfied": bool(selected) if recall_request else None,
                    "writtenThisTurn": state.get("lastExtraction", {}).get("written", []),
                    "extractedThisTurn": state.get("lastExtraction", {}).get("extractedCount", 0),
                    "persistedThisTurn": state.get("lastExtraction", {}).get("persistedCount", 0),
                    "correctionsApplied": state.get("lastExtraction", {}).get("correctionsApplied", 0),
                    "invalidMemoryCaptureRejected": bool(
                        state.get("lastExtraction", {}).get(
                            "invalidMemoryCaptureRejected"
                        )
                    ),
                    "eventsExtractedThisTurn": list(
                        state.get("lastExtraction", {}).get("eventsExtracted") or []
                    ),
                    "eventPersistence": dict(
                        state.get("lastExtraction", {}).get("eventPersistence") or {}
                    ),
                    "customerSelfDisclosure": dict(
                        state.get("lastExtraction", {}).get("customerSelfDisclosure") or {}
                    ),
                    "temporalEventRecall": {
                        "attempted": bool(temporal_windows),
                        "timezone": projection.get("timezone") or "UTC",
                        "reason": ("RESOLVED_TEMPORAL_OVERLAP"
                                   if temporal_event_matches else None),
                        "windows": [{
                            "expression": window["expression"],
                            "start": window["start"].isoformat(),
                            "end": window["end"].isoformat(),
                        } for window in temporal_windows],
                        "matchedEvents": [{
                            "key": record.get("key"),
                            "subject": (record.get("value") or {}).get("subject"),
                            "event": (record.get("value") or {}).get("event"),
                            "scheduledFor": (record.get("value") or {}).get("scheduledFor"),
                        } for record in active
                            if id(record) in temporal_event_matches],
                    },
                    "continuityGuidance": continuity_guidance,
                    "memoryPriorityOperational": True,
                    "memoryPriority": normalized_priority,
                    "operationalMemoryPolicy": {
                        "authority": "ConversationalMemoryService",
                        "policy": "RELEVANCE_PRESERVING_CANDIDATE_DEPTH",
                        "retrievalCandidateLimit": effective_limit,
                        "defaultCandidateLimit": cls._MEMORY_PRIORITY_LIMITS["STANDARD"],
                        "truthThresholdChanged": False,
                        "persistenceEligibilityChanged": False,
                        "callbackRequirementChanged": False,
                    },
                    "memoryCandidates": [{
                        "key": record.get("key"),
                        "category": record.get("category"),
                        "domains": sorted(cls._record_domains(record)),
                        "relevanceScore": score,
                        "selected": record in selected,
                    } for score, record in ranked],
                    "locationTimezoneInference": state.get("lastExtraction", {}).get("locationTimezoneInference"),
                    "persistenceSource": "telegram_sales_prospects.preference_state",
                    "retrievalSource": "telegram_sales_prospects.preference_state",
                    "totalCurrent": len(active),
                    "supersededCount": sum(r.get("status") == "superseded" for r in state["records"])}}
        if projection.get("location") and tokens.intersection(
                {"where", "live", "location", "city", "moved", "timezone"}):
            result["location"] = projection["location"]
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def _continuity_guidance(cls, selected, *, temporal_event_matches,
                             explicit_recall, explicit_reference=False,
                             classification):
        if not selected:
            return {
                "priority": "NONE", "strongestMemory": None,
                "relevanceReasons": [], "conditionalUse": True,
                "maximumCallbacks": 0,
            }
        strongest = selected[0]
        reasons = []
        if id(strongest) in temporal_event_matches:
            reasons.append("RESOLVED_TEMPORAL_OVERLAP")
        if explicit_recall:
            reasons.append("EXPLICIT_RECALL")
        if explicit_reference:
            reasons.append("EXPLICIT_MEMORY_REFERENCE")
        domains = cls._record_domains(strongest)
        if classification.domains.intersection(domains):
            reasons.append("SEMANTIC_DOMAIN_RELEVANCE")
        priority = "HIGH" if (
            reasons and (
                "RESOLVED_TEMPORAL_OVERLAP" in reasons
                or "EXPLICIT_RECALL" in reasons
                or "EXPLICIT_MEMORY_REFERENCE" in reasons
                or classification.confidence >= .9
            )
        ) else "NORMAL"
        return {
            "priority": priority,
            "strongestMemory": {
                "category": strongest.get("category"),
                "key": strongest.get("key"),
                "value": strongest.get("value"),
            },
            "relevanceReasons": reasons,
            "conditionalUse": True,
            "maximumCallbacks": 1,
        }

    @classmethod
    def _temporal_recall_windows(cls, message, now, customer_timezone):
        text = cls._normalize_apostrophes(str(message or "")).lower()
        if re.search(r"\btomorrow\s+by\s+[a-z]|\btomorrow never knows\b", text):
            return []
        zone_name = customer_timezone or "UTC"
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("UTC")
        current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        local = current.astimezone(zone)
        expressions = []
        pattern = (
            r"later\s+today|today|tonight|tomorrow(?:\s+(?:morning|afternoon|evening))?|"
            r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"weekend|week|month)|this\s+(?:weekend|week)|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        )
        for match in re.finditer(rf"\b({pattern})\b", text):
            expression = re.sub(r"\s+", " ", match.group(1))
            if expression in expressions:
                continue
            expressions.append(expression)
        windows = []
        for expression in expressions:
            if expression in {"today", "later today", "tonight"}:
                start = local.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1) - timedelta(microseconds=1)
            elif expression.startswith("tomorrow"):
                start = (local + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0,
                )
                end = start + timedelta(days=1) - timedelta(microseconds=1)
            elif expression in {"this week", "next week"}:
                offset = -local.weekday() + (7 if expression == "next week" else 0)
                start = (local + timedelta(days=offset)).replace(
                    hour=0, minute=0, second=0, microsecond=0,
                )
                end = start + timedelta(days=7) - timedelta(microseconds=1)
            elif expression in {"this weekend", "next weekend"}:
                days = (5 - local.weekday()) % 7
                if expression == "next weekend":
                    days += 7
                start = (local + timedelta(days=days)).replace(
                    hour=0, minute=0, second=0, microsecond=0,
                )
                end = start + timedelta(days=2) - timedelta(microseconds=1)
            elif expression == "next month":
                year, month = local.year, local.month + 1
                if month == 13: year, month = year + 1, 1
                start = local.replace(year=year, month=month, day=1,
                                      hour=0, minute=0, second=0, microsecond=0)
                following_year, following_month = year, month + 1
                if following_month == 13:
                    following_year, following_month = year + 1, 1
                end = start.replace(year=following_year, month=following_month) - timedelta(microseconds=1)
            else:
                resolved = cls._resolve_future_temporal(local, expression, zone_name)
                try:
                    target = datetime.fromisoformat(resolved.get("scheduledFor"))
                except (TypeError, ValueError):
                    continue
                start = target.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1) - timedelta(microseconds=1)
            windows.append({"expression": expression, "start": start, "end": end})
        return windows

    @classmethod
    def _event_recall_significance(cls, record):
        value = record.get("value") or {}
        # Canonical v2 records use event/subject. Earlier durable records use
        # summary/relatedEntity and must be judged by the same significance
        # policy rather than being mistaken for empty, weak events.
        activity = str(value.get("event") or value.get("summary") or "")
        if not cls._event_worthy(activity, evidence=record.get("evidence"),
                                 subject=(value.get("subject")
                                          or value.get("relatedEntity"))):
            return 0
        score = 2
        if re.search(r"\b(?:appointment|reservation|flight|interview|doctor|vet|"
                     r"meeting|procedure|surgery|wedding)\b", activity, re.I):
            score += 2
        if value.get("temporalCertainty") == "STATED":
            score += 1
        if value.get("resolutionPrecision") == "DATE":
            score += 1
        return score

    @classmethod
    def _record_domains(cls, record):
        category = record.get("category")
        if category == "preference":
            return cls._preference_domains(record)
        if category == "event":
            return {"event", str((record.get("metadata") or {}).get("subjectDomain") or "")} - {""}
        domain = {"fact": "location", "entity": "entity", "pet": "pet",
                  "routine": "routine", "trait": "personality_social_style",
                  "interest": "hobby_interest", "hobby": "hobby_interest"}.get(category)
        return {domain} if domain else set()

    @staticmethod
    def _preference_domains(record):
        """Return semantic domains, including legacy evidence-based categories."""
        if record.get("category") != "preference":
            return set()
        domains = {str((record.get("metadata") or {}).get("domain") or "")}
        evidence = (str(record.get("evidence") or "").lower()
                    .replace("\u2019", "'").replace("�", "'"))
        if re.search(r"\bi(?:'m| am)\s+more of (?:a|an)\s+.+?\s+person\b", evidence):
            domains.add("leisure_activity")
        return domains - {""}

    @staticmethod
    def _normalize_apostrophes(value):
        return (str(value or "").replace("\u2019", "'")
                .replace(chr(0xFFFD), "'"))

    @classmethod
    def resolve_location(cls, value):
        key = re.sub(r"\s+", " ", value.strip().lower())
        # IANA's installed timezone database is the canonical resolver. Match
        # only an unambiguous zone locality; never guess from a generic place.
        candidates = []
        for zone in available_timezones():
            locality = zone.rsplit("/", 1)[-1].replace("_", " ").lower()
            if locality == key and "/" in zone:
                candidates.append(zone)
        if len(candidates) != 1:
            return None
        return (key.title(), candidates[0])

    @classmethod
    def _merge_records(cls, state, records):
        written = []
        for incoming in records:
            # Canonical pet corrections also retire the legacy composite
            # entity projection so stale names/breeds cannot be retrieved.
            if incoming.get("category") == "pet" and incoming.get("key") in {
                "pet_name", "pet_breed", "pet_type",
            }:
                for existing in state["records"]:
                    metadata = dict(existing.get("metadata") or {})
                    if (existing.get("category") == "entity"
                            and metadata.get("compatibilityProjection") is True
                            and existing.get("status") == "current"):
                        value = existing.get("value") or {}
                        field = {"pet_name": "name", "pet_breed": "breed",
                                 "pet_type": "type"}[incoming["key"]]
                        if value.get(field) != incoming.get("value"):
                            existing.update(status="superseded",
                                            supersededAt=incoming["observedAt"])
            duplicate = False
            for existing in state["records"]:
                if ((existing.get("category"), existing.get("key")) ==
                    (incoming["category"], incoming["key"]) and existing.get("status") == "current"):
                    if existing.get("value") == incoming.get("value"):
                        existing.update(lastObservedAt=incoming["observedAt"],
                                        evidence=incoming["evidence"],
                                        confidence=incoming["confidence"],
                                        metadata=incoming.get("metadata") or {})
                        duplicate = True
                        break
                    existing.update(status="superseded", supersededAt=incoming["observedAt"])
            if not duplicate: state["records"].append(incoming)
            written.append({"category": incoming["category"], "key": incoming["key"]})
        state.update(cls._projection(state))
        return written

    @classmethod
    def _refresh_event_lifecycle(cls, state, now):
        for record in state["records"]:
            if record.get("category") != "event" or record.get("status") != "current": continue
            value = record.get("value") or {}
            try: scheduled = datetime.fromisoformat(value.get("scheduledFor"))
            except (TypeError, ValueError): continue
            current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            if scheduled.tzinfo is None: scheduled = scheduled.replace(tzinfo=timezone.utc)
            if current > scheduled + timedelta(days=1): value["status"] = "past"
        return state

    @classmethod
    def _projection(cls, state):
        result = {}
        for record in state.get("records", []):
            if record.get("status") != "current": continue
            category, key, value = record.get("category"), record.get("key"), record.get("value")
            if category == "fact" and key in {"location", "timezone"}: result[key] = value
            elif category == "preference" and key == "favorite_color": result["favoriteColor"] = value
            elif category == "entity":
                result.setdefault("entities", []).append(value)
                if "pet" not in result: result["pet"] = value
            elif category == "pet":
                pet = result.setdefault("pet", {})
                if key == "pet_name": pet["name"] = value
                elif key == "pet_type": pet["type"] = value
                elif key == "pet_breed": pet["breed"] = value
            elif category == "preference": result.setdefault("preferences", []).append(value)
            elif category == "routine": result.setdefault("routines", []).append(value)
            elif category == "trait": result.setdefault("traits", []).append(value)
            elif category in {"interest", "hobby"}:
                result.setdefault("interests", []).append(value)
            elif category == "event": result.setdefault("events", []).append(value)
        return result

    @classmethod
    def _normalize_state(cls, value):
        if value.get("schemaVersion") == cls.SCHEMA_VERSION and isinstance(value.get("records"), list):
            return dict(value)
        state = {"schemaVersion": cls.SCHEMA_VERSION, "records": []}
        at = datetime.now(timezone.utc)
        for key in ("location", "timezone"):
            if value.get(key): state["records"].append(cls._record("fact", key, value[key], "legacy prospect memory", at))
        if value.get("favoriteColor"):
            state["records"].append(cls._record("preference", "favorite_color", value["favoriteColor"], "legacy prospect memory", at))
        if isinstance(value.get("pet"), dict):
            pet = value["pet"]
            state["records"].append(cls._record("entity", cls._slug(pet.get("name") or "pet"), pet, "legacy prospect memory", at))
        return state

    @staticmethod
    def _record(category, key, value, evidence, at, confidence=.95, metadata=None,
                source="customer_volunteered_telegram"):
        return {"category": category, "key": key, "value": value, "status": "current",
                "confidence": confidence, "evidence": evidence, "observedAt": at.isoformat(),
                "source": source, "metadata": dict(metadata or {})}

    @classmethod
    def _next_weekday(cls, at, weekday, customer_timezone):
        days = (cls._WEEKDAYS[weekday.lower()] - at.weekday()) % 7 or 7
        return (at + timedelta(days=days)).replace(hour=12, minute=0, second=0, microsecond=0)

    @staticmethod
    def _split_preferences(value):
        return [v.strip() for v in re.split(r"\s*(?:,|\band\b)\s*", value) if 2 <= len(v.strip()) <= 50]

    @staticmethod
    def _invalid_preference_capture_rejected(text, records):
        lowered = str(text or "").lower().replace("\u2019", "'")
        suspicious = bool(
            re.search(
                r"\b(?:what|things|stuff)\s+i\s+(?:like|love|enjoy|prefer)\b",
                lowered,
            )
            or re.search(
                r"\bi\s+(?:like|love|enjoy|prefer)\s+"
                r"(?:now|then|today|tonight|lately)\b",
                lowered,
            )
        )
        invalid_values = {
            "now", "then", "today", "tonight", "lately", "what", "that",
        }
        persisted_invalid = any(
            record.get("category") == "preference"
            and str(record.get("value") or "").strip().lower() in invalid_values
            for record in records
        )
        return suspicious and not persisted_invalid

    @staticmethod
    def _slug(value): return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

    @classmethod
    def _tokens(cls, value):
        tokens = set()
        for token in re.findall(r"[a-z0-9']+", str(value).replace("’", "'").lower()):
            if token.endswith("'s"): token = token[:-2]
            if len(token) > 2 and token not in cls._STOPWORDS: tokens.add(token)
        return tokens
