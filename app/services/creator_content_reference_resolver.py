"""Resolve current customer references against permanent creator publications."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping

from app.models.creator_content_reference import (
    CreatorContentReferenceCandidate,
    CreatorContentReferenceResolution,
)
from app.repositories.creator_content_publication_repository import CreatorContentPublicationRepository


class CreatorContentReferenceResolver:
    """Deterministic bounded resolver; CTA entry is evidence, never commercial authority."""

    MAX_CANDIDATES = 20
    MAX_ENTRY_HISTORY = 5
    MAX_CONTEXT_TEXT = 700
    CONTENT_NOUN = re.compile(r"\b(photo|picture|pic|image|selfie|outfit|clothes|clothing|dress|pose|set|shoot|caption|kayak|hiking)\b", re.I)
    DEICTIC = re.compile(r"\b(that|this|the one|one you posted|from that set|you posted|your)\b", re.I)
    CALLBACK = re.compile(r"\b(where did you take|more from|doing overtime|posted|wore|wearing|still think|can't stop thinking)\b", re.I)
    VAGUE_REACTION = re.compile(r"(?:\b(damn|wow|gorgeous|beautiful|hot|sexy|love|lovely|stunning)\b|[😍🥵🔥🤤])", re.I)
    GREETING_ONLY = re.compile(r"^(?:hi|hey|hello|good (?:morning|afternoon|evening))(?:\s+ava)?[!. ]*$", re.I)
    MONTHS = {name.lower(): index for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
    STOP = frozenset("a an and are at be did do for from how i in is it love loved me my of on one that the this to was were what where you your ago posted".split())

    def __init__(self, *, repository=None, entry_repository=None) -> None:
        self.repository = repository or CreatorContentPublicationRepository()
        if entry_repository is None:
            from app.repositories.creator_content_entry_attribution_repository import CreatorContentEntryAttributionRepository
            entry_repository = CreatorContentEntryAttributionRepository()
        self.entry_repository = entry_repository

    def resolve(self, *, creator_profile_id: int | None, inbound: str,
                current_timestamp: datetime | None = None, recent_conversation=(),
                telegram_provenance: Mapping[str, Any] | None = None,
                telegram_user_id: int | None = None, telegram_chat_id: int | None = None,
                entry_history=None):
        text = " ".join(str(inbound or "").split()).strip()
        intent = self._intent(text)
        vague = self._vague_reaction(text)
        provenance = dict(telegram_provenance or {})
        message_id = self._first_int(provenance, "creator_publication_telegram_message_id",
            "reply_to_telegram_message_id", "forwarded_from_message_id")
        entries = self._entries(creator_profile_id=creator_profile_id,
            telegram_user_id=telegram_user_id, telegram_chat_id=telegram_chat_id,
            supplied=entry_history)
        entry = dict(entries[0]) if entries else {}
        base = {"entry_provenance": entry}
        if creator_profile_id is None:
            return CreatorContentReferenceResolution("NONE", intent, **base)
        if not intent and not vague and message_id is None:
            return CreatorContentReferenceResolution("NONE", False, **base)

        recent = self.repository.search(creator_profile_id=int(creator_profile_id),
            platform="telegram", destination="main", limit=min(8, self.MAX_CANDIDATES))
        terms = self._meaningful_terms(text)
        semantic_search = getattr(self.repository, "search_reference_candidates", None)
        semantic = semantic_search(creator_profile_id=int(creator_profile_id), terms=terms,
            limit=self.MAX_CANDIDATES) if callable(semantic_search) else ()
        entry_publication = self._publication_by_id(int(creator_profile_id), entry.get("publicationId"))
        combined = (*semantic, *recent, *((entry_publication,) if entry_publication else ()))
        candidates = tuple({item.publication_id: item for item in combined}.values())[:self.MAX_CANDIDATES]
        if not candidates:
            return CreatorContentReferenceResolution("NONE", intent,
                evidence=("NO_PUBLICATION_CANDIDATES",), **base)

        if message_id is not None:
            exact = [item for item in candidates if item.telegram_message_id == message_id]
            if len(exact) == 1:
                overrides = bool(entry and entry.get("publicationId") != exact[0].publication_id)
                return self._resolved(exact[0], "TELEGRAM_PROVENANCE", 1.0,
                    ("AUTHORITATIVE_TELEGRAM_MESSAGE_ID",), entry=entry,
                    reply_overrode=overrides)

        if intent:
            now = current_timestamp or datetime.now(UTC)
            scored = sorted((self._score(item, text, now) for item in candidates),
                            key=lambda value: (-value[0], -value[1].published_at.timestamp()))
            viable = [value for value in scored if value[0] >= 2.0]
            if not viable:
                return CreatorContentReferenceResolution("NONE", True,
                    evidence=("INSUFFICIENT_SEMANTIC_OR_DATE_EVIDENCE",), **base)
            best_score, best, best_reasons = viable[0]
            peers = [value for value in viable if best_score - value[0] < 1.25]
            if len(peers) > 1:
                return CreatorContentReferenceResolution(
                    "AMBIGUOUS", True, method="SEMANTIC_DATE_RANKING",
                    confidence=min(0.79, best_score / 10.0),
                    candidates=tuple(CreatorContentReferenceCandidate(
                        item.publication_id, round(score, 3), tuple(reasons))
                        for score, item, reasons in peers[:5]),
                    evidence=("MULTIPLE_MATERIALLY_EQUIVALENT_PUBLICATIONS",), **base)
            selected_entry = bool(entry and entry.get("publicationId") == best.publication_id)
            overrode = bool(entry and not selected_entry)
            reasons = tuple(best_reasons) + (("CTA_ENTRY_CORROBORATES_EXPLICIT_REFERENCE",) if selected_entry else ())
            confidence = min(0.99, 0.48 + best_score / 12.0 + (0.02 if selected_entry else 0.0))
            return self._resolved(best, "SEMANTIC_DATE_RANKING", confidence, reasons,
                entry=entry, cta_participated=selected_entry, explicit_overrode=overrode)

        if vague and entry_publication is not None:
            return self._resolved(entry_publication, "CTA_ENTRY_PROVENANCE", 0.9,
                ("LATEST_AUTHORITATIVE_ENTRY_EVENT", "VAGUE_CURRENT_REACTION"),
                entry=entry, cta_participated=True)
        return CreatorContentReferenceResolution("NONE", False,
            evidence=("NO_CURRENT_REFERENCE_EVIDENCE",), **base)

    def _entries(self, *, creator_profile_id, telegram_user_id, telegram_chat_id, supplied):
        if supplied is not None:
            return tuple(dict(item) for item in supplied)[:self.MAX_ENTRY_HISTORY]
        if creator_profile_id is None or telegram_user_id is None:
            return ()
        try:
            return self.entry_repository.list_entry_history(
                creator_profile_id=int(creator_profile_id), telegram_user_id=int(telegram_user_id),
                telegram_chat_id=(int(telegram_chat_id) if telegram_chat_id is not None else None),
                limit=self.MAX_ENTRY_HISTORY)
        except RuntimeError:
            # Attribution is optional; a missing/unavailable 1C table cannot remove Part 1B resolution.
            return ()

    def _publication_by_id(self, creator_profile_id, publication_id):
        if not publication_id:
            return None
        reader = getattr(self.repository, "get_by_id", None)
        if callable(reader):
            return reader(creator_profile_id=creator_profile_id, publication_id=str(publication_id))
        values = getattr(self.repository, "values", ())
        return next((item for item in values if item.publication_id == str(publication_id)), None)

    def _score(self, publication, text, now):
        lower = text.lower()
        document = " ".join((publication.published_caption,
            publication.factual_visual_summary or "", publication.setting or "",
            publication.clothing or "", publication.pose or "", publication.activity or "",
            " ".join(publication.useful_objects), " ".join(publication.themes),
            publication.photoshoot_id or "")).lower()
        meaningful = list(self._meaningful_terms(lower))
        matches = [token for token in meaningful if token in document]
        score = min(7.0, len(matches) * 2.0)
        reasons = [f"SEMANTIC_TERM:{token}" for token in matches[:6]]
        date_score, date_reason = self._date_score(lower, publication.published_at, now)
        score += date_score
        if date_reason: reasons.append(date_reason)
        age_days = max(0.0, (now - publication.published_at).total_seconds() / 86400)
        score += max(0.0, 0.45 - min(age_days, 30.0) * 0.015)
        return score, publication, reasons

    def _date_score(self, text, published_at, now):
        published = published_at.astimezone(UTC) if published_at.tzinfo else published_at.replace(tzinfo=UTC)
        age = now.astimezone(UTC) - published
        if "yesterday" in text:
            return (4.0, "RELATIVE_DATE:YESTERDAY") if age.days in {0, 1} else (-2.0, None)
        week = re.search(r"\b(\d+|two|three)\s+weeks?\s+ago\b", text)
        if week:
            count = {"two": 2, "three": 3}.get(week.group(1), int(week.group(1)) if week.group(1).isdigit() else 0)
            return (5.0, f"RELATIVE_DATE:{count}_WEEKS") if abs(age.days - count * 7) <= 3 else (-2.0, None)
        if "months ago" in text:
            return (2.0, "RELATIVE_DATE:MONTHS_AGO") if age.days >= 60 else (-2.0, None)
        for name, month in self.MONTHS.items():
            if re.search(rf"\b{name}\b", text):
                return (4.0, f"MONTH:{name.upper()}") if published.month == month else (-2.0, None)
        return 0.0, None

    def _resolved(self, item, method, confidence, evidence, *, entry=None,
                  cta_participated=False, explicit_overrode=False, reply_overrode=False):
        context = {"publicationId": item.publication_id,
            "telegramMessageId": item.telegram_message_id,
            "publishedAt": item.published_at.isoformat(),
            "generatedImageId": item.generated_image_id,
            "actualAssetId": item.published_asset_id,
            "photoshootId": item.photoshoot_id,
            "caption": self._bound(item.published_caption),
            "visualSummary": self._bound(item.factual_visual_summary),
            "setting": self._bound(item.setting), "clothing": self._bound(item.clothing),
            "pose": self._bound(item.pose), "activity": self._bound(item.activity),
            "expression": self._bound(item.expression),
            "objects": tuple(item.useful_objects[:12]), "mood": self._bound(item.mood),
            "themes": tuple(item.themes[:12]),
            "safetySummary": self._bounded_safety(item.safety_snapshot),
            "resolutionMethod": method, "confidence": round(confidence, 3)}
        return CreatorContentReferenceResolution("RESOLVED", True, method=method,
            confidence=round(confidence, 3), context=context,
            candidates=(CreatorContentReferenceCandidate(item.publication_id,
                round(confidence * 10, 3), tuple(evidence)),), evidence=tuple(evidence),
            entry_provenance=dict(entry or {}),
            cta_provenance_participated=cta_participated,
            explicit_reference_overrode_cta=explicit_overrode,
            reply_provenance_overrode_cta=reply_overrode)

    @classmethod
    def _meaningful_terms(cls, text):
        return tuple(dict.fromkeys(token for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2 and token not in cls.STOP))[:12]

    @classmethod
    def _intent(cls, text):
        return bool(text and cls.CONTENT_NOUN.search(text)
                    and (cls.DEICTIC.search(text) or cls.CALLBACK.search(text)))

    @classmethod
    def _vague_reaction(cls, text):
        return bool(text and not cls.GREETING_ONLY.fullmatch(text)
                    and cls.VAGUE_REACTION.search(text))

    @classmethod
    def _bound(cls, value):
        return " ".join(str(value or "").split())[:cls.MAX_CONTEXT_TEXT] or None

    @staticmethod
    def _bounded_safety(value):
        allowed = ("nudityLevel", "explicitContent", "sexualIntensity", "safetyClassification", "riskFlags")
        return {key: value[key] for key in allowed if key in dict(value or {})}

    @staticmethod
    def _first_int(values, *keys):
        for key in keys:
            try:
                if values.get(key) is not None: return int(values[key])
            except (TypeError, ValueError):
                pass
        return None