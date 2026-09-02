"""Fail-closed semantic domain classification for conversational memory."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class MemoryDomainClassification:
    domains: frozenset[str]
    confidence: float
    source: str = "DETERMINISTIC_SEMANTIC_FEATURES"


class ConversationalMemoryDomainClassifier:
    """Open candidate domains without exposing any memory records itself."""

    _MUSIC = {"music", "song", "songs", "listen", "listening", "artist",
              "artists", "band", "bands", "genre", "playlist", "album"}
    _LEISURE = {"activity", "activities", "outside", "outdoors", "outdoor",
                "weekend", "saturday", "sunday", "afternoon", "leisure"}
    _SEEKING = {"what", "which", "recommend", "recommendation", "suggest",
                "suggestion", "ideas", "idea", "suit", "fits", "fit",
                "sounds", "enjoy", "doing", "do", "listen", "like"}
    _ENTITY = {"pet", "dog", "cat", "animal", "breed", "name"}
    _PET = {"pet", "pets", "dog", "dogs", "cat", "cats", "puppy", "puppies",
            "kitten", "kittens", "breed", "breeds", "vet"}
    _PET_BEHAVIOR = {"stole", "steals", "spot", "couch", "ridiculous", "house"}
    _TEMPORAL = {"monday", "tuesday", "wednesday", "thursday", "friday",
                 "saturday", "sunday", "tomorrow", "tonight", "appointment"}
    _EVENT = {"doing", "going", "taking", "bringing", "event", "plan",
              "appointment", "scheduled"}
    _EVENT_DIRECT = {"appointment", "appointments", "plan", "plans", "schedule",
                     "visit", "trip", "flight", "interview", "concert"}
    _LOCATION = {"where", "live", "location", "city", "moved", "timezone"}
    _GEOGRAPHIC = {"weather", "nearby", "local"}
    _OUTDOOR = {"outside", "outdoors", "outdoor", "hike", "hiking", "beach"}
    _GEOGRAPHIC_ANCHOR = {"weekend", "saturday", "sunday", "tomorrow",
                          "around", "here", "nearby", "local", "weather"}
    _ROUTINE = {"usually", "normally", "routine", "every", "daily", "weekly"}
    _SOCIAL_STYLE = {"quiet", "shy", "outgoing", "warm", "warming", "comfortable",
                     "open", "opening", "reserved", "social"}
    _HOBBY_INTEREST = {"outside", "outdoors", "outdoor", "hiking", "hike", "camping", "camp",
                       "fishing", "fish", "guitar", "hobby", "hobbies", "trail"}

    @classmethod
    def classify(cls, message: str, *, active_records: Iterable[Mapping] = ()):
        normalized = str(message or "").lower().replace("\u2019", "'")
        tokens = {
            token[:-2] if token.endswith("'s") else token
            for token in re.findall(r"[a-z0-9']+", normalized)
        }
        domains, scores = set(), []

        if tokens & cls._MUSIC:
            domains.add("music"); scores.append(.96)
        seeking = bool(tokens & cls._SEEKING)
        leisure_context = bool(tokens & cls._LEISURE)
        available_time = "free" in tokens and bool(tokens & {"time", "hours", "afternoon"})
        if seeking and (leisure_context or available_time):
            domains.add("leisure_activity"); scores.append(.9)
        if tokens & cls._ENTITY:
            domains.add("entity"); scores.append(.94)
        if tokens & cls._PET:
            domains.add("pet"); scores.append(.96)
        if (tokens & cls._TEMPORAL) and (tokens & cls._EVENT):
            domains.add("event"); scores.append(.93)
        if tokens & cls._EVENT_DIRECT:
            domains.add("event"); scores.append(.92)
        if tokens & cls._LOCATION:
            domains.add("location"); scores.append(.96)
        if (tokens & cls._GEOGRAPHIC) or (
            (tokens & cls._OUTDOOR) and (tokens & cls._GEOGRAPHIC_ANCHOR)
        ):
            domains.add("location"); scores.append(.91)
        if tokens & cls._ROUTINE:
            domains.add("routine"); scores.append(.86)
        if tokens & cls._SOCIAL_STYLE or "warm up" in normalized:
            domains.add("personality_social_style"); scores.append(.91)
        if tokens & cls._HOBBY_INTEREST:
            domains.add("hobby_interest"); scores.append(.93)

        # A persisted entity name is a stable semantic anchor, not a guessed fact.
        known_entity_mentioned = False
        has_known_pet = False
        for record in active_records:
            if record.get("category") == "pet":
                has_known_pet = True
            if record.get("category") not in {"entity", "pet"}:
                continue
            value = record.get("value") or {}
            name = str(
                value.get("name") if isinstance(value, Mapping)
                else value if record.get("key") == "pet_name" else ""
            ).lower()
            if name and name in tokens:
                known_entity_mentioned = True
                domains.add("pet" if record.get("category") == "pet" else "entity")
                scores.append(.95)
        if has_known_pet and (
            (tokens & {"he", "him", "his", "she", "her"})
            and (tokens & cls._PET_BEHAVIOR or "vet" in tokens
                 or tokens & cls._TEMPORAL or tokens & cls._EVENT_DIRECT)
        ):
            domains.add("pet"); scores.append(.9)
            if tokens & (cls._TEMPORAL | cls._EVENT_DIRECT):
                domains.add("event"); scores.append(.9)
        if known_entity_mentioned and tokens & cls._TEMPORAL:
            domains.add("event"); scores.append(.93)

        confidence = max(scores, default=0.0)
        if confidence < .8:
            domains.clear()
        return MemoryDomainClassification(frozenset(domains), confidence)
