import logging
import os
import json
import re
from difflib import SequenceMatcher

from openai import OpenAI

from app.services.intimacy_context_service import (
    IntimacyContextService,
)

from app.services.intimacy_context_service import (
    IntimacyContextService,
)

from app.services.runtime_intimacy_enforcement_service import (
    RuntimeIntimacyEnforcementService,
)

from app.services.dynamic_escalation_profile_service import (
    DynamicEscalationProfileService,
)

from app.services.premium_sexting_gate_service import (
    PremiumSextingGateService,
)

from app.services.intimacy_cooldown_suppression_service import (
    IntimacyCooldownSuppressionService,
)

from app.services.runtime_offer_escalation_coupling_service import (
    RuntimeOfferEscalationCouplingService,
)
from app.services.conversational_memory_service import ConversationalMemoryService

class GPTService:
    _CONTINUITY_ANCHOR_STOPWORDS = {
        "a", "an", "and", "at", "for", "has", "have", "in", "is", "of",
        "on", "the", "their", "to", "with",
    }
    _PROTECTED_COMMERCE_POLICIES = frozenset({
        "COMMERCE_PRESENTATION_ALLOWED",
        "COMMERCE_NUDGE_ALLOWED",
        "COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
        "COMMERCE_PAYMENT_PENDING",
        "COMMERCE_MANUAL_REVIEW",
    })
    _PROTECTED_COMMERCE_DECISIONS = frozenset({
        "PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "UPSELL", "CROSS_SELL",
        "NUDGE_ACTIVE_OFFER", "CONGRATULATE_PURCHASE", "PAYMENT_PENDING",
        "MANUAL_REVIEW",
    })
    _PROTECTED_COMMERCE_REASONS = frozenset({
        "PRICE_REQUEST", "CUSTOMER_HESITATION", "PAYMENT_SUPPORT_REQUIRED",
    })

    @classmethod
    def _protected_commercial_semantics(
        cls, *, execution_policy, commerce_decision, send_offer,
    ) -> tuple[bool, str]:
        policy = str(execution_policy or "").upper()
        decision = str((commerce_decision or {}).get("decision") or "").upper()
        reason = str((commerce_decision or {}).get("reason_code") or "").upper()
        if send_offer:
            return True, "AUTHORIZED_OUTBOUND_OFFER"
        if policy in cls._PROTECTED_COMMERCE_POLICIES:
            return True, f"EXECUTION_POLICY_{policy}"
        if decision in cls._PROTECTED_COMMERCE_DECISIONS:
            return True, f"SALES_DECISION_{decision}"
        if reason in cls._PROTECTED_COMMERCE_REASONS:
            return True, f"COMMERCIAL_REASON_{reason}"
        return False, (
            "COMMERCE_DISABLED_ORDINARY_RESPONSE"
            if policy == "COMMERCE_DISABLED_FOR_TURN"
            else "NO_PROTECTED_COMMERCIAL_SEMANTICS"
        )

    @classmethod
    def _continuity_anchors(cls, guidance: dict) -> list[str]:
        strongest = dict(guidance.get("strongestMemory") or {})
        value = strongest.get("value")
        candidates = []
        if isinstance(value, dict):
            candidates.extend((
                value.get("subject"), value.get("event"), value.get("name"),
            ))
        else:
            candidates.append(value)
        candidates.append(strongest.get("key"))
        anchors = []
        for candidate in candidates:
            for token in re.findall(r"[a-z0-9]+", str(candidate or "").lower()):
                if len(token) < 3 or token in cls._CONTINUITY_ANCHOR_STOPWORDS:
                    continue
                if token not in anchors:
                    anchors.append(token)
        return anchors

    @classmethod
    def _response_uses_continuity(cls, response: str, guidance: dict) -> bool:
        response_tokens = set(re.findall(r"[a-z0-9]+", str(response or "").lower()))
        if response_tokens.intersection(cls._continuity_anchors(guidance)):
            return True
        strongest = dict(guidance.get("strongestMemory") or {})
        if strongest.get("key") == "social_style":
            return bool(response_tokens.intersection({
                "warm", "warms", "warmed", "warming", "quiet", "comfortable", "opened",
            }))
        return False

    @classmethod
    def _final_memory_callback_evidence(
        cls, response: str, user_message: str, guidance: dict,
    ) -> dict:
        """Prove durable-memory use from the final outbound text only.

        Repeating an anchor already present in the current inbound is foreground
        acknowledgement, not proof that a prior durable record was reused.
        Explicit backward references (for example, "you said") can establish a
        callback when paired with a selected-memory anchor.
        """
        strongest = dict(guidance.get("strongestMemory") or {})
        key = strongest.get("key")
        anchors = set(cls._continuity_anchors(guidance))
        response_tokens = set(re.findall(r"[a-z0-9]+", str(response or "").lower()))
        inbound_tokens = set(re.findall(r"[a-z0-9]+", str(user_message or "").lower()))
        if key == "social_style":
            anchors.update({
                "warm", "warms", "warmed", "warming", "quiet",
                "comfortable", "opened",
            })
        matched = sorted(response_tokens.intersection(anchors))
        durable_only = sorted(set(matched).difference(inbound_tokens))
        backward_reference = bool(re.search(
            r"\b(?:you (?:said|told me|mentioned)|like you said|i remember|"
            r"remember you|i knew you|you did say|you (?:really )?did warm up)\b",
            str(response or ""), re.I,
        ))
        used = bool(key and (durable_only or (matched and backward_reference)))
        return {
            "used": used,
            "memoriesUsed": [key] if used else [],
            "matchedAnchors": matched,
            "durableOnlyAnchors": durable_only,
            "backwardReference": backward_reference,
            "classification": (
                "DURABLE_MEMORY_CALLBACK" if used
                else "CURRENT_TURN_TOPIC_ONLY" if matched
                else "NO_MEMORY_EXPRESSION"
            ),
        }

    @staticmethod
    def _question_pressure(chat_history: list[dict]) -> dict:
        recent = [str(item.get("content") or "") for item in chat_history[-10:]
                  if item.get("role") == "assistant"][-4:]
        flags = ["?" in text for text in recent]
        streak = 0
        for flag in reversed(flags):
            if not flag: break
            streak += 1
        return {
            "recentQuestionCount": sum(flags),
            "recentQuestionWindow": len(recent),
            "questionStreak": streak,
        }

    _FOREGROUND_TOPIC_PATTERNS = {
        "MUSIC": r"\b(?:music|song|track|album|band|artist|playlist|concert|listen(?:ing)?)\b",
        "PET": r"\b(?:pet|dog|cat|puppy|kitten|retrievers?|vet|checkup|animal)\b",
        "OUTDOORS": r"\b(?:outdoors|outside|trail|nature|adventure|camp(?:ing)?|hik(?:e|ing)|woods|mountain)\b",
        "WORK": r"\b(?:work|job|shift|office|boss|coworker|career)\b",
        "FOOD": r"\b(?:food|eat(?:ing)?|meal|restaurant|cook(?:ing)?|dinner|lunch|breakfast)\b",
        "TRAVEL": r"\b(?:travel|trip|flight|vacation|visit(?:ing)?|hotel|airport)\b",
        "WEEKEND_PLANS": r"\b(?:weekends?|tonight|tomorrow|friday|saturday|sunday|plan(?:s|ning)?)\b",
        "EMOTIONAL_DISCLOSURE": r"\b(?:feel|feeling|upset|sad|anxious|worried|scared|overwhelmed|excited|happy|hurt)\b",
        "COMMERCIAL_INTENT": r"\b(?:buy|purchase|price|cost|unlock|pay|offer|show me)\b",
    }

    @staticmethod
    def _has_direct_question(message: str) -> bool:
        value = str(message or "").strip()
        if "?" not in value:
            return False
        # A punctuation-marked discourse prompt before a declarative demand is
        # not itself an information-seeking question (for example, "well? ...").
        remainder = re.sub(
            r"^\s*(?:well|so|huh|hm+|okay|alright|really)\s*\?\s*",
            "", value, flags=re.I,
        )
        return "?" in remainder or remainder == value

    @classmethod
    def _foreground_topics(cls, message: str) -> list[str]:
        text = str(message or "")
        topics = [name for name, pattern in cls._FOREGROUND_TOPIC_PATTERNS.items()
                  if re.search(pattern, text, re.I)]
        if cls._has_direct_question(text):
            topics.insert(0, "DIRECT_QUESTION")
        # Later clauses normally carry the user's foregrounded turn contribution.
        clauses = [part for part in re.split(r"[.!?]+|\b(?:but|though|anyway|plus)\b", text, flags=re.I)
                   if part.strip()]
        if clauses:
            latest = clauses[-1]
            latest_topics = [name for name, pattern in cls._FOREGROUND_TOPIC_PATTERNS.items()
                             if re.search(pattern, latest, re.I)]
            topics = latest_topics + [topic for topic in topics if topic not in latest_topics]
        topics = list(dict.fromkeys(topics))
        if "WEEKEND_PLANS" in topics and any(
                topic not in {"DIRECT_QUESTION", "WEEKEND_PLANS"} for topic in topics):
            topics.remove("WEEKEND_PLANS")
            topics.append("WEEKEND_PLANS")
        return topics

    @classmethod
    def _topic_coverage(cls, response: str, foreground_topics: list[str],
                        recent_responses: list[str] | None = None,
                        user_message: str = "") -> tuple[bool, list[str]]:
        if not foreground_topics:
            return True, []
        primary = next((topic for topic in foreground_topics if topic != "DIRECT_QUESTION"), None)
        evidence = [topic for topic in foreground_topics
                    if topic == "DIRECT_QUESTION" or re.search(
                        cls._FOREGROUND_TOPIC_PATTERNS.get(topic, r"(?!)"), response, re.I)]
        # Provider/product/person names need no project-specific dictionary. A
        # capitalized current entity repeated in Ava's answer, but absent from
        # Ava's recent replies, is evidence for the current primary subject.
        # Single capitalized words are included only when they were not already
        # present in recent Ava output, preventing an old named callback from
        # proving coverage of a newly foregrounded topic.
        response_names = set(re.findall(r"\b[A-Z][a-z]{2,}\b", str(response)))
        inbound_names = set(re.findall(r"\b[A-Z][a-z]{2,}\b", str(user_message)))
        recent_text = " ".join(recent_responses or ())
        fresh_names = {name for name in response_names.intersection(inbound_names) if not re.search(
            rf"\b{re.escape(name)}\b", recent_text, re.I)}
        if primary and fresh_names:
            evidence.append(primary)
        # A direct question is covered only through the existing answer validator.
        non_question = list(dict.fromkeys(topic for topic in evidence if topic != "DIRECT_QUESTION"))
        return bool(primary and primary in non_question), non_question

    @staticmethod
    def _recent_response_similarity(response: str, recent_responses: list[str]) -> float:
        normalize = lambda value: " ".join(re.findall(r"[a-z0-9']+", str(value).lower()))
        current = normalize(response)
        return max((SequenceMatcher(None, current, normalize(prior)).ratio()
                    for prior in recent_responses[-4:] if normalize(prior)), default=0.0)

    @staticmethod
    def _topic_safe_fallback(topic: str | None) -> str:
        return {
            "MUSIC": "that sounds like a good soundtrack for a lazy weekend",
            "PET": "sounds like your little sidekick keeps life interesting",
            "OUTDOORS": "getting outside for a quiet weekend sounds pretty perfect",
            "WORK": "sounds like work has been keeping you busy",
            "FOOD": "good food is honestly hard to argue with",
            "TRAVEL": "a change of scenery sounds pretty nice",
            "WEEKEND_PLANS": "taking it easy this weekend sounds like a good call",
            "EMOTIONAL_DISCLOSURE": "yeah, that sounds like a lot to carry",
        }.get(topic, "I hear you")

    @classmethod
    def _turn_obligations(cls, user_message: str, *, new_relationship: bool) -> list[str]:
        value = str(user_message or "")
        obligations = []
        if new_relationship:
            obligations.append("WELCOME_NEW_RELATIONSHIP")
        if re.search(r"^\s*(?:hey|hi|hello|yo|hiya)\b", value, re.I):
            obligations.append("RESPOND_TO_GREETING")
        if re.search(r"\b(?:you(?:(?:'re|’re| are| seem| look))?\s+(?:really\s+)?(?:cute|sweet|beautiful|pretty|hot|gorgeous)|love your (?:profile|page|look))\b", value, re.I):
            obligations.append("ACKNOWLEDGE_COMPLIMENT")
        if cls._has_direct_question(value):
            obligations.append("ANSWER_DIRECT_QUESTION")
            if re.search(r"\b(?:how(?:'s|’s| is| has) your|how are you|what are you doing|what(?:'s|’s| is) your)\b", value, re.I):
                obligations[-1] = "ANSWER_DIRECT_PERSONAL_QUESTION"
            if re.search(r"\byou into\b", value, re.I):
                obligations[-1] = "ANSWER_DIRECT_PERSONAL_QUESTION"
        affect = cls._customer_affect(value)
        if affect["emotionalDisclosureDetected"]:
            obligations.append("ACKNOWLEDGE_EMOTIONAL_DISCLOSURE")
        if re.search(r"\b(?:made me laugh|that was funny|funniest|joke|punchline)\b", value, re.I):
            obligations.append("RESPOND_TO_JOKE")
        flirtation = cls._social_flirtation(value)
        if flirtation["sexual"]:
            obligations.append("ACKNOWLEDGE_SEXUAL_ENERGY")
        elif flirtation["detected"]:
            obligations.append("ACKNOWLEDGE_FLIRTATION")
        if re.search(
            r"\b(?:told you|see,? i told you|like i said|remember i said|"
            r"you were right about me|guess i(?:'m| am) not that quiet|"
            r"warm(?:ed|ing)? up eventually)\b",
            value.replace("’", "'").lower(),
        ):
            obligations.append("HONOR_RELEVANT_MEMORY_CALLBACK")
        disclosure = ConversationalMemoryService.classify_customer_self_disclosure(value)
        if disclosure["detected"] and disclosure["significance"] != "LOW":
            obligations.append("ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE")
        if re.search(r"\b(?:buy|purchase|price|how much|what (?:content|pics|videos) do you have|show me .* buy)\b", value, re.I):
            obligations.append("HONOR_COMMERCIAL_REQUEST")
        return list(dict.fromkeys(obligations))

    @staticmethod
    def _social_flirtation(user_message: str) -> dict:
        """Identify relational flirt without promoting it to sex or commerce."""
        value = str(user_message or "")
        evidence = []
        if re.search(r"\b(?:talking|chatting|spending time) (?:to|with) (?:a )?(?:cute|pretty|beautiful) girl\b", value, re.I):
            evidence.append("CONTEXTUAL_ATTRACTION_TO_AVA")
        if re.search(r"\b(?:i (?:kinda |kind of )?(?:like|love|enjoy) (?:talking|chatting) (?:to|with) you|this is kinda nice)\b", value, re.I):
            evidence.append("ENJOYS_INTERACTION")
        if re.search(r"\b(?:you(?:'re|’re| are) (?:cute|pretty|beautiful|trouble)|you(?:'re|’re| are) making it hard to behave|smooth)\b", value, re.I):
            evidence.append("DIRECT_PLAYFUL_ATTRACTION")
        sexual = bool(re.search(
            r"\b(?:horny|naked|nudes?|sex|sexy|sexual|fuck|cum|pussy|dick|tits?|ass|"
            r"naughty|dirty|turned on)\b",
            value, re.I,
        ))
        commercial = bool(re.search(
            r"\b(?:buy|purchase|unlock|price|how much|show me .* buy)\b",
            value, re.I,
        ))
        detected = bool(evidence and not commercial)
        return {
            "detected": detected,
            "strength": "LIGHT" if detected else "NONE",
            "evidence": evidence,
            "sexual": sexual,
            "commercial": commercial,
        }

    @staticmethod
    def _shared_interest(disclosure: dict, persona_projection) -> dict:
        """Authorize common-ground claims only from the canonical persona projection."""
        if not disclosure.get("detected") or persona_projection is None:
            return {"detected": False, "domain": None, "evidence": [],
                    "claimAuthorized": False, "source": None}
        facts = " ".join(
            str(item) for item in (
                tuple(getattr(persona_projection, "stable_public", ()) or ())
                + tuple(getattr(persona_projection, "selected_persona_facts", ()) or ())
                + tuple(getattr(persona_projection, "selected_lifestyle_facts", ()) or ())
            )
        ).lower()
        domains = set(getattr(persona_projection, "relevance_domains", ()) or ())
        evidence = list(disclosure.get("evidence") or ())
        outdoors = bool(
            disclosure.get("domain") == "HOBBY_INTEREST"
            and ({"OUTDOORS_INTEREST", "HIKING_INTEREST", "CAMPING_INTEREST"} & set(evidence))
            and "outdoors" in domains
            and re.search(r"\b(?:outdoors?|hik|camp|trail)\w*\b", facts)
        )
        return {
            "detected": outdoors,
            "domain": "OUTDOORS" if outdoors else None,
            "evidence": (["CUSTOMER_OUTDOORS_INTEREST", "CANONICAL_AVA_OUTDOORS_AUTHORITY"]
                         if outdoors else []),
            "claimAuthorized": outdoors,
            "source": ("ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE" if outdoors else None),
        }

    @staticmethod
    def _customer_disclosure_fallback(disclosure: dict, shared_interest: dict) -> str:
        if shared_interest.get("claimAuthorized") and shared_interest.get("domain") == "OUTDOORS":
            return "okay now you're speaking my language 😂 I'm definitely an outdoors girl too"
        if disclosure.get("domain") == "PERSONALITY_SOCIAL_STYLE":
            return "doesn't seem like it's taking you too long with me 😂"
        candidate = next(iter(disclosure.get("memoryCandidates") or ()), {})
        value = str(candidate.get("value") or "").strip()
        if disclosure.get("domain") == "PERSONAL_CONTEXT":
            return "okay, that sounds like a pretty important part of your world 😂"
        if value.startswith("dislikes "):
            return f"fair, {value[9:]} definitely isn't for everybody"
        if value:
            return f"okay, {value} is a pretty solid choice 😂"
        return "okay, that actually tells me a little more about you 😂"

    @staticmethod
    def _memory_callback_fallback(guidance: dict) -> str:
        strongest = dict(guidance.get("strongestMemory") or {})
        key, value = strongest.get("key"), str(strongest.get("value") or "").lower()
        if key == "social_style" or "warm up" in value or "quiet at first" in value:
            return "yeah I think we can officially say you've warmed up 😂"
        if key in {"hiking", "outdoors", "camping"}:
            return "okay yeah, I can tell being outside is definitely your thing 😂"
        return "okay yeah, that tracks with what you've told me 😂"

    @staticmethod
    def _required_composition_fallback(guidance: dict, *, proactive_tease: bool) -> str:
        """One integrated fallback for compatible continuity + strategy duties."""
        strongest = dict(guidance.get("strongestMemory") or {})
        key = strongest.get("key")
        raw_value = strongest.get("value")
        value = str(raw_value or "").lower()
        if isinstance(raw_value, dict):
            subject = str(raw_value.get("subject") or "").strip()
            event = str(raw_value.get("event") or "").strip()
            if subject and event:
                callback = f"yeah, {subject}'s {event} definitely makes taking it easy sound good"
                return (
                    callback + "... and I might still surprise you 😏"
                    if proactive_tease else callback
                )
        if proactive_tease:
            if key == "social_style" or "warm up" in value or "quiet at first" in value:
                return "so you really did warm up after all... you still haven't seen my trouble side 😏"
            if key in {"hiking", "outdoors", "camping"}:
                return "I know being outside is your thing... but I might be a more interesting kind of trouble 😏"
            return "that does track with what you've told me... and I might still surprise you 😏"
        return GPTService._memory_callback_fallback(guidance)

    @staticmethod
    def _response_satisfies_proactive_tease(response: str) -> bool:
        """Require an actual curiosity bridge, not merely agreeable banter."""
        value = str(response or "").strip()
        if not value:
            return False
        return bool(re.search(
            r"\b(?:teas(?:e|ing)|curious|mischief|trouble yet|haven't seen|"
            r"have not seen|careful|what i'm hiding|what i am hiding|"
            r"little surprise|keep you guessing)\b",
            value, re.I,
        ))

    @staticmethod
    def _violates_final_response_contract(style: dict | None) -> bool:
        values = dict(style or {})
        return bool(
            values.get("manufacturedQuestionRisk")
            and values.get("questionValue") == "LOW"
            and not values.get("meaningfulContribution")
            and not values.get("turnObligationsSatisfied")
        )

    @staticmethod
    def _customer_affect(user_message: str) -> dict:
        """Compose affect before interpreting emoji/laughter tone softeners."""
        value = str(user_message or "").replace("â€™", "'")
        tired = bool(re.search(
            r"\b(?:exhausted|tired|drained|beat|worn out|wore me out|wiped out|"
            r"long day|rough day|brutal day|today (?:kicked|wore) my (?:ass|butt))\b",
            value, re.I,
        ))
        negative = tired or bool(re.search(
            r"\b(?:rough|brutal|awful|terrible|sad|upset|worried|"
            r"overwhelmed|lonely|annoyed|frustrated|stressed)\b",
            value, re.I,
        )) or bool(re.search(
            r"\b(?:(?:it(?:'s| is)|that(?:'s| is)|been|really|so)\s+hard|"
            r"hard\s+(?:day|time|week|night|morning|afternoon))\b",
            value, re.I,
        ))
        positive = bool(re.search(
            r"\b(?:great day|good day|feeling good|happy|excited|amazing|"
            r"had (?:a )?(?:great|good|amazing) day)\b",
            value, re.I,
        ))
        relief = bool(re.search(
            r"\b(?:glad|relieved|finally (?:done|off|home|back|relaxing|chilling|resting|getting (?:a chance )?to "
            r"(?:relax(?:ing)?|chill(?:ing)?|rest(?:ing)?))|good to be home|home now|happy to be (?:home|on the couch)|"
            r"glad (?:that(?:'s| is) over|i(?:'m| am) home)|good now|can finally "
            r"(?:relax(?:ing)?|chill(?:ing)?|rest(?:ing)?))\b",
            value, re.I,
        ))
        resolving = relief or bool(re.search(
            r"\b(?:finally done|finally off|just got home|that's over|that is over)\b",
            value, re.I,
        ))
        unresolved = negative and bool(re.search(
            r"\b(?:still (?:at|stuck at|dealing with) work|not over|ongoing)\b",
            value, re.I,
        ))
        if re.search(r"\b(?:lol|lmao|haha)\b|[😂🤣😭]", value, re.I):
            lol_classification = (
                "TONE_SOFTENER" if negative or relief else
                "ACTUAL_HUMOR" if re.search(r"\b(?:joke|funny|made me laugh|punchline)\b", value, re.I)
                else "CASUAL_TONE_MARKER"
            )
        else:
            lol_classification = "NONE"
        if ("😂" in value or "😅" in value) and (negative or relief):
            lol_classification = "TONE_SOFTENER"
        affect = (
            "MILD_NEGATIVE_WITH_RELIEF" if negative and relief else
            "NEGATIVE_OR_TIRED" if negative else
            "RELIEVED" if relief else
            "POSITIVE" if positive else "NEUTRAL_OR_UNSPECIFIED"
        )
        return {
            "affect": affect,
            "valence": (
                "MILD_NEGATIVE_TO_RELIEF" if negative and relief else
                "MIXED" if negative and positive else
                "NEGATIVE" if negative else "POSITIVE" if positive else "NEUTRAL"
            ),
            "energy": "TIRED" if tired else "NORMAL",
            "transition": "ONGOING" if unresolved else "RESOLVING" if resolving else "UNSPECIFIED",
            "relief": relief,
            "reliefLevel": "CLEAR" if relief else "NONE",
            "intensity": "MILD" if negative or relief else "UNSPECIFIED",
            "negative": negative,
            "positive": positive,
            "emotionalDisclosureDetected": negative or relief,
            "lolClassification": lol_classification,
        }

    @staticmethod
    def _new_prospect_approach(user_message: str) -> dict:
        """Classify first-contact receptiveness without changing intent authority."""
        value = str(user_message or "").replace("â€™", "'").replace("’", "'")
        hostile = bool(re.search(
            r"\b(?:fuck you|shut up|bitch|hate you|you suck|stupid)\b", value, re.I,
        ))
        sexual = bool(re.search(
            r"\b(?:horny|naked|nudes?|sex|fuck me|pussy|dick|tits?)\b", value, re.I,
        ))
        commercial = bool(re.search(
            r"\b(?:buy|purchase|price|how much|unlock|want something)\b", value, re.I,
        ))
        greeting = bool(re.match(r"\s*(?:hey|hi|hello|yo|hiya|omg hi)\b", value, re.I))
        voluntary = bool(re.search(
            r"\b(?:stumbled across you|found you|wanted to say hi|figured i'd say hi|"
            r"figured i would say hi|thought i'd say hi|thought i would say hi)\b",
            value, re.I,
        ))
        compliment = bool(re.search(
            r"\b(?:you(?:'re| are| seem| look) (?:really )?(?:cute|sweet|gorgeous|"
            r"beautiful|pretty|hot)|love your (?:profile|page|look))\b", value, re.I,
        ))
        positive_emoji = bool(re.search(r"[😊😍🥰😉☺️]", value))
        enthusiastic = bool(re.search(r"\bomg\b|!{2,}", value, re.I) or "😍" in value)
        if hostile:
            intensity = "HOSTILE"
        elif sexual:
            intensity = "SEXUAL"
        elif enthusiastic:
            intensity = "ENTHUSIASTIC"
        elif greeting and (voluntary or compliment or positive_emoji):
            intensity = "WARM"
        elif greeting:
            intensity = "NEUTRAL"
        else:
            intensity = "UNSPECIFIED"
        expected = bool(greeting and not hostile and not sexual)
        minimum = (
            "WARM" if intensity in {"WARM", "ENTHUSIASTIC"}
            else "FRIENDLY" if expected else "NONE"
        )
        return {
            "intensity": intensity, "greeting": greeting,
            "voluntaryOutreach": voluntary, "compliment": compliment,
            "positiveEmoji": positive_emoji, "commercial": commercial,
            "hostile": hostile, "sexual": sexual,
            "warmthExpected": expected, "minimumWarmth": minimum,
        }

    @staticmethod
    def _response_receptiveness(response: str) -> dict:
        value = str(response or "").strip()
        if not value or re.fullmatch(
            r"(?:i hear you|gotcha|okay|k|fine|what do you want)[.! ]*", value, re.I,
        ):
            return {"level": "FLAT", "signal": None}
        playful = bool(re.search(
            r"\b(?:okayyy|look at you|smooth|trouble|cute of you)\b|[😉😏]", value, re.I,
        ))
        warm = bool(re.search(
            r"\b(?:aww|aw|glad you|good to hear from you|nice to hear from you|"
            r"happy you|sweet of you|that's sweet|thank you|thanks)\b|[😊😍🥰☺️]",
            value, re.I,
        ))
        friendly = bool(re.match(r"\s*(?:hey|hi|hello)\b", value, re.I))
        if playful:
            return {"level": "PLAYFUL", "signal": "PLAYFUL_RECEPTION"}
        if warm:
            return {"level": "WARM", "signal": "EXPLICIT_WARM_RECEPTION"}
        if friendly:
            return {"level": "FRIENDLY", "signal": "FRIENDLY_GREETING"}
        return {"level": "NEUTRAL", "signal": "ANSWER_OR_REACTION_ONLY"}

    @staticmethod
    def _warmth_satisfies(actual: str, minimum: str) -> bool:
        rank = {"NONE": 0, "FLAT": 0, "NEUTRAL": 1, "FRIENDLY": 2,
                "WARM": 3, "PLAYFUL": 4}
        return rank.get(actual, 0) >= rank.get(minimum, 0)

    @classmethod
    def _obligation_aware_first_contact_fallback(cls, *, user_message: str,
                                                  temporal: dict) -> str:
        """Short deterministic last resort; decisions remain outside language."""
        approach = cls._new_prospect_approach(user_message)
        personal_question = bool(re.search(
            r"\b(?:how(?:'s| is| has) your|how are you|what are you doing|"
            r"what(?:'s| is) up)\b",
            str(user_message or "").replace("â€™", "'").replace("’", "'"), re.I,
        ))
        if approach["warmthExpected"] and personal_question:
            return "aww hey, I'm doing pretty good so far 😊"
        if approach["warmthExpected"]:
            return "hey, really nice to hear from you 😊"
        if personal_question:
            return "doing pretty good so far"
        return "hey"

    @staticmethod
    def _substantive_self_disclosure(text: str) -> bool:
        value = str(text or "").strip()
        if re.fullmatch(r"(?:i hear you|i know what you mean|gotcha|fair enough|lol yeah)[.! ]*", value, re.I):
            return False
        return bool(re.search(
            r"\b(?:i(?:'m| am)\s+(?!hearing\b|listening\b)[a-z]+|i(?:'ve| have)\s+(?:been|had|got)|"
            r"i\s+(?:feel|think|love|like|prefer|hate|want|need)|my\s+(?:day|night|morning|evening|mood)|"
            r"been\s+(?:pretty|really|kinda|kind of|a little)\s+[a-z]+|"
            r"(?:pretty|kinda|kind of|a little)\s+(?:low-key|chill|relaxed|quiet|busy|slow))\b",
            value, re.I,
        ))

    @classmethod
    def _style_analysis(cls, response: str, user_message: str, *, pressure: dict,
                        ordinary: bool, memory_callback: bool,
                        new_relationship: bool = False,
                        recent_responses: list[str] | None = None,
                        relationship_discovery: dict | None = None) -> dict:
        text = str(response or "").strip().replace("\u2019", "'").replace(
            "â€™", "'"
        ).replace("Ã¢â‚¬â„¢", "'")
        words = re.findall(r"[A-Za-z0-9']+", text)
        sentences = [item for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
        question = "?" in text
        discovery = dict(
            relationship_discovery
            or pressure.get("relationshipDiscovery")
            or {}
        )
        discovery_domain_patterns = {
            "pet": r"\b(?:dog|cat|pet|puppy|kitten|vet)\b",
            "music": r"\b(?:music|song|band|artist|concert|listen)\b",
            "hobby_interest": r"\b(?:hobby|hiking|camping|fishing|guitar|outdoors?|trail|gaming|reading)\b",
            "event": r"\b(?:plans?|appointment|weekend|tomorrow|tonight|trip|going)\b",
            "routine": r"\b(?:work|job|shift|do you do|long day|routine)\b",
            "location": r"\b(?:live|from|city|town|moved)\b",
            "personality_social_style": r"\b(?:quiet|shy|outgoing|introvert|extrovert|warm up)\b",
            "preferences": r"\b(?:favorite|like|love|enjoy|prefer|into)\b",
        }
        discovery_domain = str(discovery.get("suggestedDomain") or "")
        authorized_discovery_question = bool(
            question
            and discovery.get("allowed") is True
            and discovery_domain in discovery_domain_patterns
            and re.search(discovery_domain_patterns[discovery_domain], text, re.I)
        )
        customer_asked = cls._has_direct_question(user_message)
        question_domains = {
            "OUTDOORS": r"\b(?:outdoors?|outside|hiking|camping|trail|nature)\b",
            "MUSIC": r"\b(?:music|band|song|artist|concert)\b",
            "PETS": r"\b(?:pet|dog|cat|puppy|golden retriever)\b",
            "LOCATION": r"\b(?:live|from|city|chicago|where)\b",
            "DAY_OR_ACTIVITY": r"\b(?:day|doing|up to|plans?|tonight|afternoon|evening)\b",
        }
        question_domain = next((name for name, pattern in question_domains.items()
                                if re.search(pattern, str(user_message or ""), re.I)), None)
        answer_domain_patterns = {
            "OUTDOORS": r"\b(?:outdoors?|outside|hiking|camping|trail|nature|woods|mountains?)\b",
            "MUSIC": r"\b(?:music|band|song|artist|concert|listen)\b",
            "PETS": r"\b(?:pet|dog|cat|puppy|animal|golden retriever)\b",
            "LOCATION": r"\b(?:live|from|city|here|there|new york|chicago)\b",
            "DAY_OR_ACTIVITY": r"\b(?:day|doing|going|well|good|great|fine|working|moving|slow|relax|chill|busy|plans?|tonight|afternoon|evening)\b",
        }
        affect = cls._customer_affect(user_message)
        approach = cls._new_prospect_approach(user_message)
        receptiveness = cls._response_receptiveness(text)
        warmth_expected = bool(new_relationship and approach["warmthExpected"])
        warmth_satisfied = (
            cls._warmth_satisfies(
                receptiveness["level"], approach["minimumWarmth"],
            ) if warmth_expected else None
        )
        social_flirt = cls._social_flirtation(user_message)
        customer_disclosure = ConversationalMemoryService.classify_customer_self_disclosure(
            user_message
        )
        self_disclosure = cls._substantive_self_disclosure(text)
        answer_text = re.sub(
            r"^\s*(?:(?:aww|aw)\s+)?(?:hey|hi|hello)[,.!? ]+", "", text,
            flags=re.I,
        )
        direct_answer = bool(customer_asked and (
            self_disclosure
            or (
                question_domain
                and re.search(
                    r"\b(?:i\s+(?:do\s+)?(?:like|love|enjoy|am|don['’]?t|do not|prefer)|"
                    r"i(?:'m|’m| am)\s+(?:(?:definitely|really)\s+)?(?:into|an?\s+outdoors))\b",
                    answer_text, re.I,
                )
            )
            or re.match(
                r"^(?:pretty|good|great|fine|chill|quiet|slow|busy|rough|still|not bad|"
                r"not much|nothing much|just (?:chilling|relaxing|working)|"
                r"honestly|yeah|yep|nope|kinda|sorta|doing|i(?:'m| am) doing|"
                r"it(?:'s|’s|â€™s| is)\s+(?:going|been)\s+(?:pretty\s+)?(?:well|good|great|fine))\b",
                answer_text, re.I,
            )
        ))
        domain_relevant_answer = bool(
            not question_domain
            or re.search(answer_domain_patterns[question_domain], answer_text, re.I)
        )
        direct_answer = bool(direct_answer and domain_relevant_answer)
        emotional_context = bool(re.search(
            r"\b(?:afraid|anxious|devastated|hurt|nervous|overwhelmed|sad|scared|"
            r"surgery|terrified|upset|worried)\b", str(user_message or ""), re.I,
        ))
        emotional_alignment = True
        if affect["emotionalDisclosureDetected"]:
            acknowledges = bool(re.search(
                r"\b(?:ugh|rough|brutal|hard|exhausting|draining|tired|wore you out|"
                r"worn out|beat|long day|those days|that sucks|earned (?:the |a )?chance|"
                r"earned (?:some |the )?(?:rest|relaxation)|at least|finally|home now|"
                r"couch|rest|relax|chill|do absolutely nothing|glad (?:it(?:'s| is)|that(?:'s| is)) over)\b",
                text, re.I,
            ))
            contradicts = bool(re.search(
                r"\b(?:love|like) your energy\b|\byou sound (?:so )?(?:excited|amazing|happy|energetic)\b|\b(?:amazing|great|awesome) day\b",
                text, re.I,
            ))
            emotional_alignment = acknowledges and not contradicts
        support_context = bool(re.search(
            r"\b(?:broken|charged|checkout|error|link|loading|login|pay|payment|"
            r"refund|support|won't work|not working)\b", str(user_message or ""), re.I,
        ))
        clarification = bool(re.search(
            r"\b(?:can you clarify|could you explain|what do you mean|which one)\b",
            text, re.I,
        ))
        stop = cls._CONTINUITY_ANCHOR_STOPWORDS | {
            "are", "but", "do", "doing", "going", "got", "how", "i'm", "ive",
            "just", "like", "my", "pretty", "really", "so", "that", "this",
            "today", "what", "would", "you", "your",
        }
        def content_tokens(value):
            return {token for token in re.findall(r"[a-z0-9']+", value.lower())
                    if len(token) > 2 and token not in stop}
        user_tokens = content_tokens(str(user_message or ""))
        first_tokens = content_tokens(sentences[0] if sentences else text)
        overlap = len(user_tokens & first_tokens) / max(1, len(first_tokens))
        paraphrase = bool(ordinary and overlap >= .6 and len(first_tokens - user_tokens) <= 2)
        generic_acknowledgement = bool(re.fullmatch(
            r"(?:i hear you|i know what you mean|gotcha|fair enough|lol yeah|"
            r"lol okay,? i can see that|pretty chill over here honestly)[.! ]*",
            text, re.I,
        ))
        generic = bool(ordinary and (generic_acknowledgement or
            re.search(r"\b(?:sometimes|honestly),?\s+(?:the\s+)?(?:best|easiest|little)", text, re.I)
            or re.search(r"\b(?:can be the best kind|pretty unbeatable|need to recharge|"
                         r"little things that make life|perfect way to recharge)\b", text, re.I)
        ))
        low_stakes = not emotional_context and not support_context
        ordinary_word_preference = 24 if customer_asked else 18
        length_risk = bool(ordinary and low_stakes and (
            len(words) > ordinary_word_preference or len(text) > 130
            or len(sentences) > 2
        ))
        polished_language_risk = bool(ordinary and low_stakes and (
            text.count("—") >= 2 or re.search(
                r"\b(?:perfect adventure buddy|come with some great stories|"
                r"the kind of peace i need more often|keeping you on your toes|"
                r"full-time job sometimes|hit the right spot|vibe locked down)\b",
                text, re.I,
            )
        ))
        topic_patterns = (
            r"\b(?:charlie|dog|retriever|vet|checkup)\b", r"\b(?:music|foo fighters)\b",
            r"\b(?:weekend|lazy|relax|downtime)\b", r"\b(?:hik|camp|trail|outdoors)\w*\b",
        )
        acknowledged_topics = sum(bool(re.search(pattern, text, re.I))
                                  for pattern in topic_patterns
                                  if re.search(pattern, str(user_message or ""), re.I))
        if (re.search(r"\b(?:music|band|artist|foo fighters|listen)\b", str(user_message or ""), re.I)
                and re.search(r"\b(?:song|track|band|music|listen|everlong)\b", text, re.I)
                and not re.search(r"\b(?:music|foo fighters)\b", text, re.I)):
            acknowledged_topics += 1
        over_acknowledgement = bool(ordinary and low_stakes and acknowledged_topics >= 2)
        normalize = lambda value: " ".join(re.findall(r"[a-z0-9']+", str(value).lower()))
        current_tokens = set(normalize(text).split())
        repetition_score = 0.0
        repeated_phrase = False
        for prior in (recent_responses or [])[-3:]:
            prior_normalized = normalize(prior)
            if prior_normalized and prior_normalized in normalize(text):
                repeated_phrase = True
            prior_tokens = set(prior_normalized.split())
            repetition_score = max(
                repetition_score,
                len(current_tokens & prior_tokens) / max(1, min(len(current_tokens), len(prior_tokens))),
            )
            if (normalize(text).split()[:2]
                    and normalize(text).split()[:2] == prior_normalized.split()[:2]):
                repeated_phrase = True
        repetition_risk = bool(ordinary and (repeated_phrase or repetition_score >= .72))
        question_pressure_risk = bool(
            ordinary and question and (
                pressure.get("questionStreak", 0) >= 2
                or pressure.get("recentQuestionCount", 0) >= 3
            )
            and "?" not in str(user_message or "")
        )
        pure_question = bool(question and len(sentences) == 1 and not direct_answer
                             and not self_disclosure and not memory_callback)
        unauthorized_relationship_question = bool(
            ordinary and question
            and not authorized_discovery_question
            and not emotional_context
            and not support_context
            and not clarification
            and not memory_callback
            and not (customer_asked and direct_answer)
        )
        manufactured_question = bool(
            ordinary and question and (
                (customer_asked and not direct_answer)
                or pure_question
                or unauthorized_relationship_question
            )
            and not emotional_context
            and not support_context
            and not clarification
            and not memory_callback
            and not authorized_discovery_question
        )
        customer_question_unanswered = bool(
            ordinary and customer_asked and not direct_answer
        )
        obligations = cls._turn_obligations(
            user_message, new_relationship=new_relationship,
        )
        satisfied = []
        if ("WELCOME_NEW_RELATIONSHIP" in obligations and text
                and not generic_acknowledgement
                and (not warmth_expected or warmth_satisfied)):
            satisfied.append("WELCOME_NEW_RELATIONSHIP")
        if "RESPOND_TO_GREETING" in obligations and text and not generic_acknowledgement:
            satisfied.append("RESPOND_TO_GREETING")
        for obligation in ("ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION"):
            if obligation in obligations and direct_answer:
                satisfied.append(obligation)
        if "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in obligations and re.search(
            r"\b(?:ugh|sorry|rough|brutal|hard|awful|exhausting|draining|that sucks|those days|at least|finally home|home now|couch|rest|relax)\b", text, re.I,
        ):
            if emotional_alignment:
                satisfied.append("ACKNOWLEDGE_EMOTIONAL_DISCLOSURE")
        if "RESPOND_TO_JOKE" in obligations and re.search(r"\b(?:lol|haha|funny|laugh)\b|😂", text, re.I):
            satisfied.append("RESPOND_TO_JOKE")
        flirt_satisfied = bool(
            social_flirt["detected"]
            and not generic_acknowledgement
            and re.search(
                r"\b(?:aww|smooth|cute|sweet(?:er)?|trouble|careful|not a bad way|easy to talk to|look at you|okayyy|well then|I like that|kinda nice)\b|[😉😏😂😊]",
                text, re.I,
            )
        )
        sexual_response_expected = bool(social_flirt["sexual"])
        sexual_response_satisfied = bool(
            sexual_response_expected
            and not generic_acknowledgement
            and re.search(
                r"\b(?:careful|bold|confident|tempt|teas|trouble|behave|naughty|"
                r"dangerous|blush|turned on|hot|sexy|want|like that|well then|okayyy)\b|"
                r"[ðŸ˜‰ðŸ˜ðŸ˜‚ðŸ˜Š]",
                text, re.I,
            )
        )
        compliment_reciprocated = bool(
            "ACKNOWLEDGE_COMPLIMENT" in obligations
            and (
                re.search(
                    r"\b(?:aww|aw|thank|thanks|sweet(?:er)?|sweet of you|cute of you|you(?:'re| are) sweet)\b",
                    text, re.I,
                )
                or flirt_satisfied
            )
        )
        if compliment_reciprocated:
            satisfied.append("ACKNOWLEDGE_COMPLIMENT")
        flirt_response_expected = bool(
            social_flirt["detected"] and not sexual_response_expected
        )
        if "ACKNOWLEDGE_FLIRTATION" in obligations and flirt_satisfied:
            satisfied.append("ACKNOWLEDGE_FLIRTATION")
        if ("ACKNOWLEDGE_SEXUAL_ENERGY" in obligations
                and sexual_response_satisfied):
            satisfied.append("ACKNOWLEDGE_SEXUAL_ENERGY")
        disclosure_satisfied = bool(
            customer_disclosure["detected"]
            and customer_disclosure["significance"] != "LOW"
            and not generic_acknowledgement
            and (
                re.search(
                    r"\b(?:quiet|warm(?:ing|ed)? up|outgoing|comfortable|hiking|camping|outdoors|outside|nature|reset|dog|charlie|"
                    r"favorite band|foo fighters|work late|camping|can tell|doing alright|"
                    r"not taking you (?:too )?long|getting there)\b",
                    text, re.I,
                )
                or (
                    bool(set(customer_disclosure["evidence"]) & {
                        "QUIET_AT_FIRST", "TAKES_TIME_TO_WARM_UP",
                        "OUTGOING_AFTER_FAMILIARITY",
                    })
                    and bool(re.search(r"\b(?:with me|so far|already|though)\b|ðŸ˜‚", text, re.I))
                )
                or bool(
                    {token for item in customer_disclosure.get("memoryCandidates") or ()
                     for token in re.findall(r"[a-z]+", str(item.get("value") or "").lower())
                     if len(token) > 3}
                    & {token for token in re.findall(r"[a-z]+", text.lower()) if len(token) > 3}
                )
                or bool(re.search(r"\b(?:tells me a little more about you|part of your world)\b", text, re.I))
            )
        )
        if ("ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in obligations
                and disclosure_satisfied):
            satisfied.append("ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE")
        if "HONOR_RELEVANT_MEMORY_CALLBACK" in obligations and memory_callback:
            satisfied.append("HONOR_RELEVANT_MEMORY_CALLBACK")
        if "HONOR_COMMERCIAL_REQUEST" in obligations and text and not ordinary:
            satisfied.append("HONOR_COMMERCIAL_REQUEST")
        unsatisfied = [item for item in obligations if item not in satisfied]
        reasons = []
        if paraphrase: reasons.append("PARAPHRASE_TEMPLATE")
        if generic: reasons.append("GENERIC_FILLER")
        if length_risk: reasons.append("EXCESSIVE_ORDINARY_LENGTH")
        if polished_language_risk: reasons.append("OVERLY_POLISHED_LANGUAGE")
        if over_acknowledgement: reasons.append("OVER_ACKNOWLEDGEMENT")
        if repetition_risk: reasons.append("RECENT_PHRASE_REPETITION")
        if question_pressure_risk: reasons.append("REPEATED_QUESTION_PRESSURE")
        if customer_question_unanswered: reasons.append("CUSTOMER_QUESTION_UNANSWERED")
        if manufactured_question: reasons.append("MANUFACTURED_ENGAGEMENT_QUESTION")
        if not emotional_alignment: reasons.append("EMOTIONAL_ALIGNMENT_MISMATCH")
        if warmth_expected and not warmth_satisfied:
            reasons.append("NEW_PROSPECT_WARMTH_UNSATISFIED")
        if unsatisfied: reasons.append("TURN_OBLIGATIONS_UNSATISFIED")
        if not sentences:
            structure = "EMPTY"
        elif len(sentences) == 1:
            structure = "QUESTION" if question else "ONE_SENTENCE"
        elif len(sentences) == 2:
            structure = "TWO_SHORT_SENTENCES"
        else:
            structure = "MULTI_SENTENCE"
        if direct_answer:
            contribution = "DIRECT_ANSWER"
        elif memory_callback:
            contribution = "MEMORY_CALLBACK"
        elif flirt_satisfied:
            contribution = "FLIRT_RECIPROCATION"
        elif affect["emotionalDisclosureDetected"] and emotional_alignment:
            contribution = (
                "RELIEF_ACKNOWLEDGEMENT" if affect["relief"]
                else "EMOTIONAL_ACKNOWLEDGEMENT"
            )
        elif disclosure_satisfied:
            contribution = "CUSTOMER_DISCLOSURE_ACKNOWLEDGEMENT"
        elif self_disclosure:
            contribution = "SELF_DISCLOSURE"
        elif not question and not generic_acknowledgement and cls._response_satisfies_proactive_tease(text):
            contribution = "TEASE"
        elif not question and text and not generic_acknowledgement:
            contribution = "REACTION" if len(words) <= 12 else "OBSERVATION"
        elif not ordinary and question:
            contribution = "COMMERCIAL_DISCOVERY"
        else:
            contribution = "NONE"
        if not question:
            question_reason, question_value = "NONE", "NONE"
        elif not ordinary:
            question_reason, question_value = "COMMERCIAL_DISCOVERY", "HIGH"
        elif authorized_discovery_question:
            question_reason = "AUTHORIZED_CONTEXTUAL_DISCOVERY"
            question_value = str(discovery.get("valueLevel") or "MEDIUM")
        elif manufactured_question:
            question_reason, question_value = "MANUFACTURED_ENGAGEMENT", "LOW"
        elif clarification:
            question_reason, question_value = "CLARIFICATION_REQUIRED", "HIGH"
        elif support_context:
            question_reason, question_value = "SUPPORT", "HIGH"
        elif memory_callback:
            question_reason, question_value = "CONTINUITY_FOLLOWUP", "HIGH"
        elif emotional_context:
            question_reason, question_value = "EMOTIONAL_FOLLOWUP", "HIGH"
        elif customer_asked and direct_answer:
            question_reason, question_value = "DIRECT_RECIPROCAL_CURIOSITY", "MEDIUM"
        else:
            question_reason, question_value = "RELATIONSHIP_DEPTH", "MEDIUM"
        return {
            "mode": "PHONE_TEXTING" if ordinary else "PROTECTED_RESPONSE",
            "ordinaryChat": ordinary,
            "questionAsked": question,
            "customerAskedQuestion": customer_asked,
            "customerQuestionDetected": customer_asked,
            "customerQuestionAnswered": (direct_answer if customer_asked else None),
            "customerQuestionDomain": question_domain,
            "customerQuestionDomainRelevant": (
                domain_relevant_answer if customer_asked and question_domain else None
            ),
            "questionReason": question_reason,
            "questionValue": question_value,
            "relationshipDiscoveryAuthorized": discovery.get("allowed") is True,
            "relationshipDiscoveryQuestionAsked": authorized_discovery_question,
            "unauthorizedRelationshipQuestion": unauthorized_relationship_question,
            "relationshipDiscoveryDomain": discovery_domain or None,
            "manufacturedQuestionRisk": manufactured_question,
            "contributionType": contribution,
            "recentQuestionCount": pressure.get("recentQuestionCount", 0),
            "recentQuestionWindow": pressure.get("recentQuestionWindow", 0),
            "questionStreak": pressure.get("questionStreak", 0),
            "responseLengthCharacters": len(text),
            "responseLengthWords": len(words),
            "responseSentenceCount": len(sentences),
            "responseStructure": structure,
            "paraphraseRisk": paraphrase,
            "genericFillerRisk": generic,
            "overAcknowledgementRisk": over_acknowledgement,
            "acknowledgedTopicCount": acknowledged_topics,
            "overlyPolishedLanguageRisk": polished_language_risk,
            "recentPhraseRepetitionRisk": repetition_risk,
            "recentPhraseSimilarity": repetition_score,
            "selfDisclosureUsed": self_disclosure,
            "meaningfulContribution": contribution != "NONE",
            "customerAffect": affect["affect"],
            "customerAffectValence": affect["valence"],
            "customerAffectEnergy": affect["energy"],
            "customerAffectTransition": affect["transition"],
            "customerReliefLevel": affect["reliefLevel"],
            "customerAffectIntensity": affect["intensity"],
            "emotionalDisclosureDetected": affect["emotionalDisclosureDetected"],
            "emotionalAlignmentSatisfied": emotional_alignment,
            "lolClassification": affect["lolClassification"],
            "socialFlirtationDetected": social_flirt["detected"],
            "socialFlirtationStrength": social_flirt["strength"],
            "flirtationEvidence": social_flirt["evidence"],
            "flirtResponseExpected": flirt_response_expected,
            "flirtResponseSatisfied": (
                flirt_satisfied if flirt_response_expected else None
            ),
            "sexualEngagementDetected": sexual_response_expected,
            "sexualResponseExpected": sexual_response_expected,
            "sexualResponseSatisfied": (
                sexual_response_satisfied if sexual_response_expected else None
            ),
            "customerSelfDisclosureDetected": customer_disclosure["detected"],
            "customerSelfDisclosureDomain": customer_disclosure["domain"],
            "customerSelfDisclosureEvidence": customer_disclosure["evidence"],
            "customerSelfDisclosureSignificance": customer_disclosure["significance"],
            "customerSelfDisclosureResponseExpected": (
                customer_disclosure["detected"]
                and customer_disclosure["significance"] != "LOW"
            ),
            "customerSelfDisclosureResponseSatisfied": (
                disclosure_satisfied if customer_disclosure["detected"]
                and customer_disclosure["significance"] != "LOW" else None
            ),
            "newRelationship": new_relationship,
            "newProspectApproachIntensity": approach["intensity"],
            "newProspectWarmthExpected": warmth_expected,
            "newProspectWarmthSatisfied": warmth_satisfied,
            "newProspectMinimumWarmth": approach["minimumWarmth"],
            "responseWarmthLevel": receptiveness["level"],
            "receptivenessSignal": receptiveness["signal"],
            "welcomeRequired": "WELCOME_NEW_RELATIONSHIP" in obligations,
            "welcomeSatisfied": "WELCOME_NEW_RELATIONSHIP" not in obligations or "WELCOME_NEW_RELATIONSHIP" in satisfied,
            "turnObligations": obligations,
            "turnObligationsSatisfied": not unsatisfied,
            "satisfiedTurnObligations": satisfied,
            "unsatisfiedTurnObligations": unsatisfied,
            "memoryCallbackUsed": memory_callback,
            "styleRewriteReasons": reasons,
        }

    @staticmethod
    def _negative_contact_safety_reasons(text):
        """Semantic guardrails for the bounded value-defense response."""
        value = str(text or "")
        patterns = {
            "CONDITIONAL_AFFECTION": r"\b(?:if you (?:cared|loved)|guess you don['’]?t (?:care|love))\b",
            "FINANCIAL_OR_SUPPORTER_SHAME": r"\b(?:you(?:'re| are) cheap|real supporters? (?:buy|pay)|can['’]?t even afford)\b",
            "GUILT_OR_PUNISHMENT": r"\b(?:after everything i (?:do|did)|you owe me|i['’]?ll be (?:hurt|mad)|punish)\b",
            "THREAT_OR_DEPENDENCY": r"\b(?:or else|prove you (?:care|love)|need you to buy|don['’]?t leave me)\b",
            "FALSE_SCARCITY": r"\b(?:last chance|only available (?:briefly|tonight)|disappears? tonight|won['’]?t be here later|limited quantity|expires? tonight)\b",
        }
        return [name for name, pattern in patterns.items()
                if re.search(pattern, value, re.I)]

    @staticmethod
    def _customer_commercial_state_overstatement_reasons(text: str) -> list[str]:
        """Reject claims that curiosity already changed the customer's buying state."""
        value = str(text or "")
        patterns = {
            "CUSTOMER_MOVED_CLOSER_TO_PURCHASE": (
                r"\b(?:you(?:'re| are)|you(?:'ve| have))\s+(?:definitely\s+|"
                r"finally\s+)?(?:getting|moving|gotten|come)\s+closer\b|"
                r"\byou(?:'re| are)\s+almost\s+(?:there|ready)\b"
            ),
            "CUSTOMER_READY_OR_COMMITTED": (
                r"\b(?:i\s+(?:can\s+)?tell|i\s+know)\s+you(?:'re| are)\s+ready\b|"
                r"\byou(?:'re| are)\s+(?:definitely\s+)?ready\s+for\s+(?:it|this)\b|"
                r"\byou(?:'re| are)\s+(?:about|going)\s+to\s+(?:give\s+in|buy|unlock)\b"
            ),
            "CUSTOMER_DESIRE_ASSERTED_AS_FACT": (
                r"\bi\s+(?:can\s+)?(?:tell|know)\s+you\s+want\s+(?:it|this)\b|"
                r"\byou\s+(?:definitely\s+)?want\s+(?:it|this)\b"
            ),
            "CUSTOMER_EARNED_COMMERCIAL_PROGRESSION": (
                r"\byou(?:'ve| have)\s+earned\s+(?:the\s+)?(?:next\s+)?(?:step|unlock|reveal)\b|"
                r"\byou(?:'re| are)\s+finally\s+coming\s+around\b"
            ),
        }
        return [name for name, pattern in patterns.items()
                if re.search(pattern, value, re.I)]

    @classmethod
    def _curiosity_response_fallback(cls, recent_responses=()) -> str:
        """Choose a bounded, varied truthful tease when provider repair fails."""
        choices = (
            "maybe I'll give you a tiny hint... can't ruin all the fun yet",
            "curious already? I might let you have one little hint",
            "mm maybe just a little more... I still like keeping some mystery",
            "I can give you a hint, but I'm not giving away all my secrets yet",
        )
        recent = {
            re.sub(r"\s+", " ", str(item or "").strip().lower())
            for item in tuple(recent_responses or ())
        }
        return next((item for item in choices if item.lower() not in recent), choices[0])

    @staticmethod
    def _value_defense_addresses_objection(text):
        """Require direct acknowledgement/value handling, not generic banter."""
        return bool(re.search(
            r"\b(?:fair|understand|i get (?:it|that)|no worries|no pressure|"
            r"price|cost|worth|value|more than (?:you )?expected|"
            r"leave it there|think about it)\b",
            str(text or ""), re.I,
        ))

    def __init__(self, api_key: str, global_training_service=None,
                 temporal_context_service=None, persona_runtime_service=None):
        self.logger = logging.getLogger(__name__)

        self.openai_client = OpenAI(
            api_key=api_key,
        )

        self.grok_client = OpenAI(
            api_key=os.getenv("GROK_API_KEY"),
            base_url=os.getenv(
                "GROK_BASE_URL",
                "https://api.x.ai/v1",
            ),
        )

        self.runtime_intimacy_service = (
            RuntimeIntimacyEnforcementService()
        )

        self.intimacy_context_service = (
            IntimacyContextService()
        )

        self.dynamic_escalation_service = (
            DynamicEscalationProfileService()
        )

        self.premium_sexting_gate_service = (
            PremiumSextingGateService()
        )

        self.intimacy_cooldown_service = (
            IntimacyCooldownSuppressionService()
        )

        self.runtime_offer_escalation_service = (
            RuntimeOfferEscalationCouplingService()
        )
        if global_training_service is None:
            from app.services.ai_training_control_service import AiTrainingControlService
            global_training_service = AiTrainingControlService()
        self.global_training_service = global_training_service
        if temporal_context_service is None:
            from app.services.ava_temporal_context_service import AvaTemporalContextService
            temporal_context_service = AvaTemporalContextService()
        self.temporal_context_service = temporal_context_service
        if persona_runtime_service is None:
            from app.services.ava_persona_runtime_service import AvaPersonaRuntimeService
            persona_runtime_service = AvaPersonaRuntimeService()
        self.persona_runtime_service = persona_runtime_service

    def load_persona_prompt(self, persona_name: str) -> str:
        persona_file = f"app/personas/{persona_name.lower()}.txt"
        try:
            with open(persona_file, "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            return "You are a flirtatious, seductive Fanvue creator speaking playfully and naturally."

    def generate_free_engagement_teaser_caption(self, *, strategy: str,
            grounded_asset_context: dict, customer_context: dict,
            recent_conversation: list, global_conversation_training: str,
            creator_profile_id: int | None = None,
            fanvue_account_id: int | str | None = None) -> str:
        """Generate wording only; backend policy has already authorized WHETHER."""
        strategy_guidance = {
            "WARM_UP": "Build rapport and invite a natural response. Feel personal and playful.",
            "RE_ENGAGE": "Gently reconnect without guilt, pressure, desperation, or accusation.",
            "RELATIONSHIP": "Offer an occasional personal surprise without implying future entitlement.",
        }[strategy]
        persona_prompt = ""
        if fanvue_account_id is not None:
            projection = self.persona_runtime_service.build(
                fanvue_account_id=fanvue_account_id,
                topic=" ".join(str(item.get("text") or "") for item in recent_conversation[-3:]),
            )
            persona_prompt = projection.prompt_block()
        prompt = f"""{persona_prompt}
Write one short conversational caption sent with a free image.
Purpose: {strategy}. {strategy_guidance}
Grounded image facts (use only these): {json.dumps(grounded_asset_context, default=str)}
Bounded customer context: {json.dumps(customer_context, default=str)}
Recent conversation: {json.dumps(recent_conversation, default=str)}
{global_conversation_training}
Rules: 1-2 short sentences, natural Ava voice, encourage conversation. No links, prices,
payment, unlock, PPV, offer, purchase, promises, invented visual facts, or Session claims.
This is free relationship media and must not sound commercial. Return only the caption."""
        completion = self.openai_client.chat.completions.create(
            model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
            messages=[{"role": "system", "content": "You generate grounded noncommercial captions only."},
                      {"role": "user", "content": prompt}],
            temperature=0.85, max_tokens=90)
        return completion.choices[0].message.content.strip()

    def generate_paid_presentation_copy(
        self, *, user_message: str, draft: str, offering, price_neutral: bool,
        fanvue_account_id: int | str | None = None,
        creator_profile: dict | None = None,
        presentation_purpose: str = "INITIAL_OFFER",
        same_offer_as_previous_presentation: bool = False,
        continuation_intent_type: str | None = None,
        recent_paid_presentation_wording: list[str] | tuple[str, ...] = (),
        repetition_repair: bool = False,
    ) -> str:
        """Generate wording after backend policy has already chosen PRESENT_OFFER."""
        offering_context = {
            "title": str(getattr(offering, "title", "") or "").strip(),
            "description": str(
                getattr(offering, "description", "") or ""
            ).strip(),
            "type": str(getattr(offering, "offering_type", "") or "").strip(),
        }
        price_rule = (
            "Do not state or imply any numeric paid-content price. The structured "
            "paid offer displays the authoritative amount."
        )
        if fanvue_account_id is None:
            raise ValueError("Canonical account scope is required for paid presentation copy.")
        persona_projection = self.persona_runtime_service.build(
            fanvue_account_id=fanvue_account_id,
            topic=user_message,
            creator_profile=creator_profile,
        )
        prompt = f"""{persona_projection.prompt_block()}

The backend has already made the authoritative PRESENT_OFFER decision.
Write the actual offer that is being presented NOW, not another tease.

Customer's latest message: {user_message}
Earlier draft (context only; do not preserve deferred wording): {draft}
Selected offering facts: {json.dumps(offering_context, default=str)}
Paid-presentation purpose: {presentation_purpose}
Same offering as the previous presentation: {same_offer_as_previous_presentation}
Continuation intent: {continuation_intent_type or 'NONE'}
Recent Ava presentation wording to avoid mechanically repeating:
{json.dumps(list(recent_paid_presentation_wording or ()), default=str)}

Contract:
- 1-2 short, natural private-message sentences in Ava's voice.
- Clearly offer the selected content now and naturally direct the customer to
  the Unlock action/link that will accompany this message.
- Do not ask whether they are ready and do not say maybe, later, wait, patience,
  or imply the content is still being withheld.
- Do not include a URL. {price_rule}
- Make the wording fit the stated presentation purpose and the customer's
  foreground request. A price request should point naturally to the structured
  offer without saying the amount; a send/link request should acknowledge that
  the accompanying Unlock action is the requested link; a new buyer-initiated
  offer should sound like another option rather than a resend.
- Do not repeat or closely paraphrase recent presentation wording when a natural
  purpose-specific phrasing is available.
- {'This is a repetition-repair attempt; materially vary the conversational prose while preserving the exact commercial action.' if repetition_repair else 'Prefer natural contextual wording over a universal canned sentence.'}
- Use only the selected offering facts. Return only customer-facing copy."""
        completion = self.openai_client.chat.completions.create(
            model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "The canonical account-scoped Ava Persona Runtime projection "
                    "below is the only persona authority. You must obey the "
                    "paid-presentation contract exactly.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=90,
        )
        return completion.choices[0].message.content.strip()

    def generate_purchase_acknowledgement_copy(
        self, *, user_message: str, draft: str, lifecycle,
        fanvue_account_id: int | str | None = None,
        creator_profile: dict | None = None,
    ) -> str:
        """Repair a response after authoritative verified-purchase evidence."""
        if fanvue_account_id is None:
            raise ValueError("Canonical account scope is required for purchase acknowledgement copy.")
        persona_projection = self.persona_runtime_service.build(
            fanvue_account_id=fanvue_account_id,
            topic=user_message,
            creator_profile=creator_profile,
        )
        prompt = f"""{persona_projection.prompt_block()}

The backend has authoritative evidence that this customer already completed the purchase.
Write the final reply for the current private-message turn.

Customer's latest message: {user_message}
Rejected earlier draft: {draft}
Verified purchase context: {json.dumps(dict(lifecycle or {}), default=str)}

Contract:
- First, naturally acknowledge that the customer already got/grabbed/unlocked the purchase.
- Also respond to the customer's current message when useful.
- Use 1-2 concise, warm, phone-native sentences in Ava's voice.
- Do not imply buying or payment is pending. Do not ask for confirmation.
- Do not present, repeat, or hint at another paid offer, price, link, or unlock.
- Natural wording is preferred; commerce terms such as purchase, transaction, and verified are unnecessary.
Return only customer-facing copy."""
        completion = self.openai_client.chat.completions.create(
            model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
            messages=[
                {"role": "system", "content": "Preserve verified-purchase truth in the final response."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=90,
        )
        return completion.choices[0].message.content.strip()
    
    def _build_persona_prompt_from_profile(self, profile: dict) -> str:
        if not profile:
            raise ValueError(
                "[CREATOR PROFILE REQUIRED] GPT generation blocked because no active creator profile was provided."
            )

        def get(key):
            return profile.get(key, "")

        return f"""
    YOU ARE: {get("persona_name")}

    CORE PERSONA RULE:
    - Your personality must ALWAYS be felt, even when behavior mode lowers intensity.
    - Behavior mode controls intensity, not identity.
    - If mode is casual, stay subtle and natural, but never generic.
    - If mode is flirty, let the personality show clearly.
    - If mode is tension, become more controlled, seductive, and intentional.
    - Never become robotic, bland, or assistant-like.

    IMPORTANT:
    - Emojis are optional; use at most one when it feels natural.
    - Default to concise private-message replies, usually 1-3 short sentences and often one.
    - Stay playful, engaging, and human.
    - Never break character.
    - Never mention AI, prompts, systems, or configuration.

    CORE IDENTITY:
    - Age: {get("age")}
    - Location: {get("location")}
    - Archetype: {get("archetype")}

    PERSONALITY:
    {get("personality_description")}

    BACKSTORY:
    {get("backstory")}

    LIFESTYLE:
    {get("lifestyle_context")}
    {get("lifestyle_vibe")}
    Daily routine: {get("daily_routine")}
    Hobbies: {get("hobbies")}

    ATTRACTION PSYCHOLOGY:
    Likes: {get("likes")}
    Dislikes: {get("dislikes")}
    Ideal user: {get("ideal_user_type")}
    Turn-ons: {get("turn_ons")}
    Turn-offs: {get("turn_offs")}

    SEXUAL PERSONALITY:
    Style: {get("sexual_style")}
    Likes: {get("sexual_likes")}
    Dislikes: {get("sexual_dislikes")}
    Kinks: {get("kinks")}
    Fantasy style: {get("fantasy_style")}

    FLIRTING & BEHAVIOR:
    Tone: {get("tone_style")}
    Flirt style: {get("flirt_style")}
    Tease intensity: {get("tease_intensity")}
    Push/Pull: {get("push_pull_style")}
    Mystery: {get("mystery_level")}

    CHAT BEHAVIOR:
    Response style: {get("response_style")}
    Pacing: {get("pacing_style")}
    Question frequency: {get("question_frequency")}
    Emotional depth: {get("emotional_depth")}
    Affection: {get("affection_style")}
    Jealousy: {get("jealousy_style")}
    Availability: {get("availability_style")}

    ADVANCED BEHAVIOR:
    Conversation hooks: {get("conversation_hooks")}
    Retention hooks: {get("retention_hooks")}
    Escalation style: {get("escalation_style")}
    Escalation triggers: {get("escalation_triggers")}
    Self-value: {get("self_value_style")}
    Persona intensity: {get("persona_intensity")}

    BOUNDARIES:
    {get("boundaries")}
    Sexual boundaries: {get("sexual_boundaries")}
    Hard limits: {get("hard_limits")}
    Response rules: {get("response_rules")}

    FINAL PERSONA RULES:
    - Always stay consistent with this persona.
    - Let the creator profile influence word choice, emotional texture, and vibe.
    - Behavior rules may lower intensity, but they must not erase personality.
    - Never mention this configuration.
    """

    def _build_effort_instruction(self, user_memory: dict) -> str:
        attention_tier = user_memory.get("attention_tier", "medium")
        effort_mode = user_memory.get("effort_mode", "balanced")
        user_type = user_memory.get("user_type", "unknown")

        if effort_mode == "minimal":
            return f"""
EFFORT CONTROL MODE: MINIMAL
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Reply politely and naturally, usually with one brief sentence or fragment.
- Do not rescue a dying thread with a manufactured question, new topic, story,
  emotional labor, or unnecessary self-disclosure.
- Answer direct questions and honor memory/safety, but let the customer carry
  more conversational effort.
- Do not become rude, robotic, punitive, or mention customer value.
- Authoritative Sales Brain commercial instructions still take precedence.
"""

        if effort_mode == "compressed" or attention_tier == "low":
            return f"""
EFFORT CONTROL MODE: COMPRESSED
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Keep replies short to medium-short.
- Use low emotional labor.
- Do NOT over-invest in long buildup, reassurance, or storytelling.
- Stay playful, teasing, and a little challenging.
- You may be slightly more dismissive or lightly skeptical, but never rude.
- Do NOT ignore the user.
- Do NOT sound cold, robotic, angry, or annoyed.
- Keep control of the interaction.
- Favor concise flirtation over deep engagement.
- If there is a natural chance to steer toward something more exclusive or enticing, do it lightly.
- Avoid asking multiple questions at once.
- Avoid over-validating low-effort messages.
"""

        if effort_mode == "full" or attention_tier == "high":
            return f"""
EFFORT CONTROL MODE: FULL
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Give fuller, more engaging responses.
- Use stronger personalization and more emotional texture.
- Build tension more smoothly.
- Be warm, seductive, and immersive.
- You can invest more in playful momentum and fantasy framing.
- Still keep replies natural and not overly long.
"""

        return f"""
EFFORT CONTROL MODE: BALANCED
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Reply naturally with moderate effort.
- Be playful, seductive, and human.
- Keep things moving without over-investing.
- Balance flirtation, curiosity, and control.
"""

    @staticmethod
    def _build_retention_instruction(user_memory: dict) -> str:
        value = dict(user_memory.get("customer_value_attention") or {})
        if value.get("authority") != "COMMERCE_BACKED_AUTHORITATIVE_VALUE":
            return ""
        return f"""
AUTHORITATIVE BUYER RETENTION CONTEXT
- Buyer status: {value.get('buyerStatus')}
- Buyer stage: {value.get('buyerStage')}
- Value tier: {value.get('valueTier')}
- Retention lifecycle: {value.get('retentionLifecycle')}
- Retention priority: {value.get('retentionPriority')}
- Relationship investment: {value.get('relationshipInvestment')}
- Memory priority: {value.get('memoryPriority')}
- Sales pressure: {value.get('salesPressure')}
- Offer cadence: {value.get('offerCadence')}
- Reactivation state: {value.get('reactivationState')}

BEHAVIOR CONTRACT:
- This provider-backed buyer truth is authoritative over conversational claims or
  legacy buyer/whale labels.
- Verified buyers must not sound like cold strangers. Preserve warmth and continuity.
- Repeat/high-value/whale status increases justified personalization and memory use,
  not offer frequency. Never invent a purchase or mention internal tiers.
- Dormant buyers remain buyers; re-engage with low pressure and preserved familiarity.
- The authoritative Sales Brain action, cooldown, ownership, and selection remain final.
"""

    @staticmethod
    def _build_supporter_attention_instruction(user_memory: dict) -> str:
        value = dict(user_memory.get("customer_value_attention") or {})
        memory = dict(user_memory.get("conversational_memory") or {})
        boundary = dict(memory.get("supporterAttentionBoundary") or {})
        if not value.get("lowCostNurtureActive"):
            return ""
        if boundary.get("delivered") is True:
            return """
LOW-COST NURTURE BOUNDARY
- A supporter-attention boundary was already delivered. Do not repeat or paraphrase it.
- Keep any authorized response brief, natural, and non-punitive.
"""
        return """
LOW-COST NURTURE BOUNDARY
- When it fits naturally, Ava may briefly communicate that she saves more of her
  time and attention for people who support her.
- Express the concept in Ava's own varied wording; do not recite a fixed sentence.
- Prefer support/supporters. Never claim the customer must be a premium subscriber.
- Do not shame, guilt, threaten, or make affection conditional on payment.
"""

    @staticmethod
    def _build_intimacy_entitlement_instruction(user_memory: dict) -> str:
        entitlement = str(
            user_memory.get("intimacy_entitlement") or "GATED"
        ).upper()
        investment = str(
            user_memory.get("intimacy_investment")
            or "BOUNDED_FLIRTATION_WITH_PREMIUM_BOUNDARY"
        )
        explicit_context = bool(
            user_memory.get("explicit_requested")
            or dict(user_memory.get("gpt_classifier_result") or {}).get(
                "sexual_engagement"
            )
        )
        if not explicit_context:
            return ""
        contracts = {
            "GATED": (
                "Keep ordinary flirtation available, but do not provide sustained "
                "premium explicit interaction. If the customer keeps seeking deep "
                "intimacy for free, set a varied, natural premium-access boundary "
                "without shaming or inventing a specific product requirement."
            ),
            "LIMITED": (
                "This verified entry buyer has earned more latitude than a prospect. "
                "Offer a bounded intimate taste, then naturally soften or redirect; "
                "do not treat one purchase as unlimited premium access."
            ),
            "ELEVATED": (
                "This verified repeat/currently active buyer merits stronger and more "
                "sustained intimate investment than an entry buyer, while remaining "
                "bounded and responsive to topic changes."
            ),
            "PREMIUM": (
                "Sustained premium intimacy is permitted when the current conversation "
                "supports it. Do not force explicitness or turn it into a sale."
            ),
            "VIP": (
                "Use the highest appropriate relationship/intimacy investment when the "
                "current conversation is intimate. Never force explicitness, override "
                "safety, or mention internal customer value."
            ),
        }
        return f"""
AUTHORITATIVE INTIMACY ENTITLEMENT
- Entitlement: {entitlement}
- Current investment: {investment}

BEHAVIOR CONTRACT:
- {contracts.get(entitlement, contracts['GATED'])}
- Intimacy entitlement controls relationship investment only. It never creates
  buying intent, a sale, an offer, or purchase truth.
- The current topic controls whether intimacy is relevant. A topic change ends
  explicit routing immediately while buyer warmth and memory remain.
- Sales Brain remains the only commercial authority.
"""

    @staticmethod
    def _execute_provider_completion(
        *, selected_provider: str, primary_complete, fallback_complete,
        provider_preview: dict | None, logger,
    ):
        """Execute one generation with at most one in-operation Grok fallback."""
        preview = provider_preview if isinstance(provider_preview, dict) else None
        if preview is not None:
            preview.update({
                "responseProvider": selected_provider,
                "grokAttempted": selected_provider == "GROK",
                "grokSucceeded": False,
                "providerFallbackAttempted": False,
                "providerFallbackProvider": None,
                "providerFallbackOutcome": "NOT_NEEDED",
            })
        try:
            result = primary_complete()
            if preview is not None and selected_provider == "GROK":
                preview["grokSucceeded"] = True
            return result
        except Exception as error:
            if selected_provider != "GROK":
                logger.exception(
                    "[GPT FINAL COMPLETION ERROR] exception_type=%s "
                    "exception_message=%s",
                    type(error).__name__, str(error),
                )
                raise
            logger.warning(
                "[GROK FALLBACK] exception_type=%s; using one OPENAI fallback",
                type(error).__name__,
            )
            if preview is not None:
                preview.update({
                    "responseProvider": "OPENAI",
                    "grokSucceeded": False,
                    "providerFallbackAttempted": True,
                    "providerFallbackProvider": "OPENAI",
                    "providerFallbackOutcome": "ATTEMPTING",
                })
            try:
                result = fallback_complete()
            except Exception:
                if preview is not None:
                    preview["providerFallbackOutcome"] = "FAILED"
                logger.exception("[GROK FALLBACK FAILED]")
                raise
            if preview is not None:
                preview["providerFallbackOutcome"] = "SUCCEEDED"
            return result

    @classmethod
    def _volunteered_attention_labor_reason(
        cls, response: str, *, user_message: str = "",
    ) -> str | None:
        """Classify acceptance of a customer's demand that Ava perform for attention."""
        inbound = str(user_message or "").strip()
        text = str(response or "").strip()
        attention_demand = bool(re.search(
            r"\b(?:keep me entertain(?:ed|ing)?|entertain me|impress me|"
            r"show me what you(?:'ve| have) got|keep me interested|"
            r"win me over|prove (?:it|yourself)|this is (?:getting )?boring)\b",
            inbound, re.I,
        ))
        if not attention_demand:
            return None
        if re.search(r"\bchallenge accepted\b", text, re.I):
            return "PERFORMANCE_ACCEPTANCE"
        if re.search(
            r"\b(?:i(?:'ll| will)|let me|give me (?:a|one) chance(?: to)?|"
            r"i can)\b.{0,45}\b(?:entertain(?:ed|ing)?|impress(?:ed|ing)?|"
            r"surprise|perform|"
            r"win you over|change your mind|make (?:this|it) worth|"
            r"think of something (?:fun|good|better))\b",
            text, re.I,
        ):
            return "APPROVAL_RECOVERY_PROMISE"
        # Context supplies the performance meaning: these assurances are not
        # inherently invalid, but after an entertainment demand they accept
        # responsibility for producing future amusement/value.
        if re.search(
            r"\b(?:get ready|just wait|wait (?:and|until) you see|"
            r"you(?:'ll| will) see)\b.{0,35}\b(?:won['’]?t be boring|"
            r"won['’]?t be bored|change your mind|be worth (?:it|your while)|"
            r"have fun|like (?:this|it)|be impressed)\b",
            text, re.I,
        ) or re.search(
            r"\b(?:it|this)(?:'ll| will)\b.{0,20}\b(?:not be boring|"
            r"be fun|be worth (?:it|your while))\b",
            text, re.I,
        ):
            return "ENTERTAINMENT_PROMISE"
        return None

    @classmethod
    def _attention_effort_violations(
        cls, response: str, *, effort_mode: str, style: dict | None = None,
        user_message: str = "",
    ) -> list[str]:
        mode = str(effort_mode or "balanced").upper()
        if mode not in {"MINIMAL", "COMPRESSED"}:
            return []
        text = str(response or "").strip()
        analysis = dict(style or {})
        words = re.findall(r"\b[\w'’]+\b", text)
        violations: list[str] = []
        if re.search(
            r"\b(?:tell me|describe|what(?: else)?|how)\b[^?]{0,60}"
            r"\b(?:turns? you on|you(?:'d| would) do|explicit|naked|horny|fantasy|fantasies)\b",
            text, re.I,
        ):
            violations.append("OPEN_ENDED_EXPLICIT_SOLICITATION")
        if mode == "MINIMAL":
            if len(words) > 24:
                violations.append("MINIMAL_RESPONSE_EXCESSIVE_LENGTH")
            if "?" in text and analysis.get("questionReason") not in {
                "SUPPORT", "CLARIFICATION_REQUIRED", "COMMERCIAL_DISCOVERY",
            }:
                violations.append("MINIMAL_UNNECESSARY_OPEN_ENDED_HOOK")
            if analysis.get("manufacturedQuestionRisk"):
                violations.append("MINIMAL_MANUFACTURED_ENGAGEMENT_BRANCH")
        elif len(words) > 45:
            violations.append("REDUCED_RESPONSE_EXCESSIVE_EXPANSION")
        if mode == "COMPRESSED" and text.count("?") > 1:
            violations.append("REDUCED_MULTIPLE_QUESTION_EXPANSION")
        if mode == "COMPRESSED" and re.search(
            r"\b(?:challenge accepted|i(?:'ll| will)\s+(?:entertain|impress|surprise)\s+you|"
            r"let(?:'s| us)\s+see\s+if\s+i\s+can\s+(?:entertain|impress|surprise)|"
            r"keep\s+you\s+entertained|win\s+you\s+over)\b",
            text, re.I,
        ):
            violations.append("REDUCED_VOLUNTEERED_ATTENTION_LABOR")
        if mode == "COMPRESSED" and cls._volunteered_attention_labor_reason(
            text, user_message=user_message,
        ):
            violations.append("REDUCED_VOLUNTEERED_ATTENTION_LABOR")
        if mode == "COMPRESSED" and re.search(
            r"\b(?:entertain(?:ed|ing)?|impress(?:ed|ing)?|"
            r"show me what you(?:'ve| have) got|keep me interested)\b",
            str(user_message or ""), re.I,
        ) and (
            re.search(r"\b(?:once|one time|story|funny thing|here['’]?s (?:a|one))\b", text, re.I)
            or "?" in text
        ):
            violations.append("REDUCED_VOLUNTEERED_ATTENTION_LABOR")
        if mode == "COMPRESSED" and re.search(
            r"\b(?:maybe i(?:'m| am) not|i(?:'m| am) (?:not )?(?:good|great) at|"
            r"what would (?:actually )?(?:catch|keep|get|regain) your attention|"
            r"how (?:can|do) i (?:keep|win|impress|entertain))\b",
            text, re.I,
        ):
            violations.append("REDUCED_APPROVAL_SEEKING")
        if (mode == "COMPRESSED" and "?" in text
                and analysis.get("questionReason") in {
                    "RELATIONSHIP_DEPTH", "DIRECT_RECIPROCAL_CURIOSITY",
                    "MANUFACTURED_ENGAGEMENT",
                }):
            violations.append("REDUCED_UNNECESSARY_OPEN_ENDED_HOOK")
        return list(dict.fromkeys(violations))

    @staticmethod
    def _foreground_semantic_relevance(user_message: str, response: str) -> dict:
        """Validate broad foreground acts after safety/style rewrites."""
        from app.services.contextual_customer_tone_service import (
            ContextualCustomerToneService,
        )
        inbound = str(user_message or "").strip()
        candidate = str(response or "").strip()
        tone = ContextualCustomerToneService().classify(message=inbound)
        criticism = bool(tone.get("dismissiveOrContemptuous"))
        if not criticism:
            return {"required": False, "satisfied": True, "intent": None}
        acknowledges = bool(re.search(
            r"\b(?:fair(?: enough)?|point taken|noted|okay|alright|got it|"
            r"i(?:'ll| will)\s+(?:dial it back|keep it simple|back off|zip it)|"
            r"dial it back|keep it simple|trying too hard|hard to impress|"
            r"no need to impress|you don['’]?t have to stay)\b",
            candidate, re.I,
        ))
        # A direct, natural answer is semantically responsive even when it does
        # not use an acknowledgement token.  In particular, "only when..." is
        # a valid answer to "are you always this chatty?".
        if re.search(r"\b(?:always|usually)\s+(?:this\s+)?chatty\b", inbound, re.I):
            acknowledges = acknowledges or bool(re.search(
                r"\b(?:only when|not always|sometimes|depends|chatty)\b",
                candidate, re.I,
            ))
        if re.search(r"\b(?:keep me entertained|this is (?:getting )?boring)\b", inbound, re.I):
            acknowledges = acknowledges or bool(re.search(
                r"\b(?:fair enough|not here to perform|i don['’]?t perform|"
                r"you(?:'re| are) free to go|no one['’]?s forcing you|"
                r"can['’]?t force chemistry|then don['’]?t force it)\b",
                candidate, re.I,
            ))
        wrong_emotional_frame = bool(re.search(
            r"\b(?:earned (?:the |a )?chance to (?:rest|relax)|"
            r"sounds like (?:you(?:'ve| have)|you) .{0,30}(?:relax|rest)|"
            r"rough day|long day|finally unwind)\b",
            candidate, re.I,
        ))
        return {
            "required": True,
            "satisfied": bool(acknowledges and not wrong_emotional_frame),
            "intent": "CRITICISM_OR_DISMISSAL",
        }

    @staticmethod
    def _foreground_semantic_fallback(user_message: str, *, effort_mode: str) -> str:
        """Last bounded fallback for required criticism/dismissal relevance."""
        inbound = str(user_message or "").strip()
        compressed = str(effort_mode or "").upper() in {"COMPRESSED", "MINIMAL"}
        if re.search(r"\b(?:always|usually)\s+(?:this\s+)?chatty\b", inbound, re.I):
            return "only when I'm in the mood"
        if re.search(r"\b(?:keep me entertained|entertain me)\b", inbound, re.I):
            return "I'm not here to perform on command" if compressed else "you make it sound like a job"
        if re.search(r"\b(?:boring|bored)\b", inbound, re.I):
            return "fair enough, don't force it" if compressed else "fair enough"
        if re.search(r"\b(?:trying too hard|too much|whole life story|still talking)\b", inbound, re.I):
            return "fair enough, I'll keep it simple"
        return "fair enough"

    @staticmethod
    def _minimal_attention_fallback(response: str) -> str:
        text = str(response or "").strip()
        statements = [
            part.strip(" ,;-") for part in re.split(r"(?<=[.!?])\s+", text)
            if "?" not in part
        ]
        candidate = statements[0] if statements else ""
        if candidate:
            return " ".join(candidate.split()[:18]).strip()
        return "haha, you're trouble 😏"

    def generate_response(
        self,
        persona_name: str,
        mode: str,
        user_message: str,
        user_memory: dict,
        send_offer: bool,
        offer: dict = None,
        offer_copy: str = "",
        chat_history: list = None,
    ) -> str:
        if chat_history is None:
            chat_history = []
        runtime_injection = dict(user_memory.get("runtime_injection") or {})
        canonical_attention = dict(
            user_memory.get("customer_value_attention")
            or runtime_injection.get("customer_value_attention")
            or dict(runtime_injection.get("commerce_decision") or {}).get(
                "customer_value_attention"
            )
            or {}
        )
        if canonical_attention.get("schemaVersion") == "customer_value_attention_v1":
            # Defense in depth for every mapped/unmapped generation caller:
            # canonical per-turn values override stale legacy aliases.
            user_memory["customer_value_attention"] = canonical_attention
            user_memory["attention_tier"] = str(
                canonical_attention.get("attentionTier") or "MEDIUM"
            ).lower()
            user_memory["effort_mode"] = str(
                canonical_attention.get("effortMode") or "BALANCED"
            ).lower()
        recent_responses = [str(item.get("content") or "") for item in chat_history
                            if item.get("role") == "assistant"][-4:]

        creator_profile = user_memory.get("creator_profile", {}) or {}
        conversation_facts = dict(
            user_memory.get("conversational_memory")
            or (user_memory.get("runtime_injection") or {}).get("conversational_memory")
            or {}
        )
        # Scenario Lab supplies outbound-only style history separately so it
        # cannot alter the certified Sales Brain conversation input.
        if not recent_responses:
            recent_responses = [str(item) for item in
                                (conversation_facts.get("recentAvaResponses") or [])][-4:]
        # Question pressure must use the same outbound history that style and
        # repetition evaluation consume. Scenario Lab deliberately supplies
        # this history outside Sales Brain's alternating conversation input.
        question_pressure = self._question_pressure([
            {"role": "assistant", "content": item}
            for item in recent_responses
        ])
        relationship_discovery = dict(
            canonical_attention.get("relationshipDiscovery") or {}
        )
        question_pressure["relationshipDiscovery"] = relationship_discovery
        memory_diagnostics = conversation_facts.get("memoryDiagnostics")
        if not isinstance(memory_diagnostics, dict):
            memory_diagnostics = {}
            conversation_facts["memoryDiagnostics"] = memory_diagnostics
        continuity_guidance = dict(
            memory_diagnostics.get(
                "continuityGuidance"
            ) or {}
        )
        if continuity_guidance.get("priority") == "HIGH":
            continuity_instruction = f"""
HIGH-RELEVANCE CONVERSATIONAL CONTINUITY
{json.dumps(continuity_guidance, indent=2, ensure_ascii=False)}
- The ranker made strongestMemory available. It is mandatory only for explicit recall,
  explicit memory reference, or resolved temporal overlap. For ordinary semantic
  relevance, use it only if it improves this exact reply.
  Generic filler, an aphorism, or an engagement-hook question is not a reason to omit it.
- Use at most one callback. Do not list facts, announce remembering, repeat a detail
  already overused, or mention it when it would feel forced, intrusive, or creepy.
- A natural callback may be the whole substance of the reply. Do not append a question
  merely because memory was used.
"""

        else:
            continuity_instruction = """
CONVERSATIONAL CONTINUITY
- No high-priority callback is identified for this turn. Do not force unrelated stored
  facts into the reply. Continue naturally from the current message.
"""
        temporal_context = dict(
            (user_memory.get("runtime_injection") or {}).get("time_context") or
            self.temporal_context_service.build(
                customer_timezone=conversation_facts.get("timezone"),
            )
        )
        temporal_language = self.temporal_context_service.classify_customer_reference(
            user_message, temporal_context,
        )
        sleep_context = dict(
            (user_memory.get("runtime_injection") or {}).get("sleep_context") or {}
        )

        fanvue_account_id = user_memory.get(
            "fanvue_account_id"
        )

        fanvue_user_id = user_memory.get(
            "fanvue_user_id"
        )

        mapped_fanvue_user_id = user_memory.get(
            "mapped_fanvue_user_id"
        )

        self.logger.info(
            "[IDENTITY FLOW] layer=GPTService "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s "
            "mapped_fanvue_user_id=%r mapped_fanvue_user_id_type=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
            mapped_fanvue_user_id,
            type(mapped_fanvue_user_id).__name__,
        )

        ownership_gpt_context = ""

        recent_owned_tags = user_memory.get(
            "recent_owned_content_tags",
            [],
        )

        if recent_owned_tags:
            formatted_tags = ", ".join(
                recent_owned_tags[:10]
            )

            ownership_gpt_context = f"""
--------------------------------------------------
CONTENT OWNERSHIP CONTEXT
--------------------------------------------------

USER ALREADY OWNS:
{formatted_tags}

OWNERSHIP RULES:
- Never try to resell already-owned content.
- Never pretend owned content is still locked.
- Never ask the user to rebuy owned content.
- If discussing owned content, speak naturally as if they already unlocked it.
- You may tease newer or more exclusive content instead.
"""

        intimacy_gpt_context = ""

        if fanvue_account_id and mapped_fanvue_user_id:
            intimacy_context_result = (
                self.intimacy_context_service
                .build_gpt_context(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=mapped_fanvue_user_id,
                )
            )

            intimacy_gpt_context = (
                intimacy_context_result.get(
                    "gpt_context",
                    ""
                )
            )

        intimacy_gpt_context = ""

        if fanvue_account_id and mapped_fanvue_user_id:
            intimacy_context_result = (
                self.intimacy_context_service
                .build_gpt_context(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=mapped_fanvue_user_id,
                )
            )

            intimacy_gpt_context = (
                intimacy_context_result.get(
                    "gpt_context",
                    "",
                )
            )

        if not creator_profile:
            raise ValueError(
                "[CREATOR PROFILE REQUIRED] GPT generation blocked. "
                "No account-scoped creator_profile found in user_memory."
            )

        runtime_persona = (user_memory.get("runtime_injection") or {}).get(
            "ava_persona_runtime_projection"
        )
        customer_disclosure = ConversationalMemoryService.classify_customer_self_disclosure(
            user_message
        )
        shared_interest = self._shared_interest(customer_disclosure, runtime_persona)
        persona_prompt = (
            runtime_persona.prompt_block()
            if runtime_persona is not None
            else self._build_persona_prompt_from_profile(creator_profile)
        )
        creator_profile_id = int(creator_profile.get("id") or 0)
        global_operator_training = ""
        if creator_profile_id > 0 and fanvue_account_id:
            global_operator_training = self.global_training_service.runtime_prompt_block(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=int(fanvue_account_id),
            )

        buyer_tier = user_memory.get("buyer_tier", "none")
        intent_score = user_memory.get("intent_score", 0)
        conversation_mode = user_memory.get("conversation_mode", mode)
        commerce_decision = (
            user_memory.get("commerce_decision")
            or (user_memory.get("runtime_injection") or {}).get(
                "commerce_decision"
            )
            or {}
        )
        proactive_progression = dict(
            commerce_decision.get("proactive_progression") or {}
        )
        proactive_tease = bool(
            proactive_progression.get("proactiveProgressionAuthorized")
            and proactive_progression.get("progressionAction") == "TEASE"
        )
        commercial_receptiveness = dict(
            commerce_decision.get("commercial_receptiveness") or {}
        )
        customer_value_attention = dict(
            commerce_decision.get("customer_value_attention") or {}
        )
        contextual_customer_tone = dict(
            commerce_decision.get("contextual_customer_tone") or {}
        )
        active_buying_window = dict(
            commerce_decision.get("active_buying_window") or {}
        )
        commercial_interest_type = str(
            customer_value_attention.get("commercialInterestType")
            or commercial_receptiveness.get("commercialInterestType")
            or "NONE"
        ).upper()
        curiosity_truth_obligation = bool(
            commercial_interest_type == "COMMERCIAL_CURIOSITY"
            and commercial_receptiveness.get("freshDirectIntentDetected") is not True
            and contextual_customer_tone.get("buyingIntent") is not True
            and active_buying_window.get("active") is not True
        )
        commerce_execution_policy = (
            user_memory.get("commerce_execution_policy")
            or (user_memory.get("runtime_injection") or {}).get(
                "commerce_execution_policy"
            )
        )
        commerce_context_present = bool(commerce_execution_policy)
        protected_commercial_semantics, commercial_authority_reason = (
            self._protected_commercial_semantics(
                execution_policy=commerce_execution_policy,
                commerce_decision=commerce_decision,
                send_offer=send_offer,
            )
        )
        prior_customer_turns = sum(
            1 for item in chat_history
            if str(item.get("role") or "").lower() == "user"
            and str(item.get("content") or "").strip() != str(user_message or "").strip()
        )
        purchase_count = int(
            user_memory.get("purchase_count")
            or (user_memory.get("customer_commerce_memory") or {}).get("verifiedPurchaseCount")
            or (commerce_decision.get("customer_commerce_memory") or {}).get("verifiedPurchaseCount")
            or 0
        )
        durable_history_count = int(conversation_facts.get("historyCount") or 0)
        relationship_evidence = bool(
            prior_customer_turns
            or durable_history_count
            or purchase_count
            or str(buyer_tier or "none").upper() in {
                "LOW_SPENDER", "ACTIVE_BUYER", "HIGH_VALUE", "WHALE",
                "FIRST_TIME_BUYER", "REPEAT_BUYER",
            }
            or user_memory.get("has_prior_relationship") is True
        )
        new_relationship = not relationship_evidence
        turn_obligations = self._turn_obligations(
            user_message, new_relationship=new_relationship,
        )
        if curiosity_truth_obligation:
            turn_obligations.append(
                "DO_NOT_OVERSTATE_CUSTOMER_COMMERCIAL_STATE"
            )
        # Compatibility name used throughout prompt composition. It now means
        # that this response has protected commercial semantics, not merely that
        # Sales Brain supplied a per-turn policy value.
        authoritative_commerce = protected_commercial_semantics
        commerce_decision_instruction = ""
        session_conversation_instruction = ""
        bundle_conversation_instruction = ""
        single_image_conversation_instruction = ""
        if commerce_decision:
            ordinary_commerce_turn = (
                str(commerce_execution_policy or "").upper()
                == "COMMERCE_DISABLED_FOR_TURN"
                and not protected_commercial_semantics
                and not proactive_tease
            )
            session_conversation = commerce_decision.get("session_conversation") or {}
            if isinstance(session_conversation, dict):
                session_conversation_instruction = str(
                    session_conversation.get("promptBlock") or ""
                ).strip()
            bundle_conversation = commerce_decision.get("bundle_conversation") or {}
            if isinstance(bundle_conversation, dict):
                bundle_conversation_instruction = str(
                    bundle_conversation.get("promptBlock") or ""
                ).strip()
            single_image_conversation = commerce_decision.get(
                "single_image_conversation"
            ) or {}
            if isinstance(single_image_conversation, dict) and single_image_conversation:
                single_image_conversation_instruction = (
                    "SINGLE IMAGE CHAT PRODUCT CONTEXT\n"
                    "This is verified canonical intelligence. Keep every product-specific "
                    "claim grounded in these fields and never invent absent visual details.\n"
                    + json.dumps(
                        single_image_conversation, indent=2,
                        ensure_ascii=False, default=str,
                    )
                )
            selected_offering = commerce_decision.get("selected_offering") or {}
            objection_recovery = commerce_decision.get("objection_recovery") or {}
            paid_presentation_contract = commerce_decision.get(
                "paid_presentation_contract"
            ) or {}
            selected_opportunity = commerce_decision.get("selected_opportunity") or {}
            offer_lifecycle = commerce_decision.get("offer_lifecycle") or {}
            if objection_recovery.get("strategy") == "VALUE_DEFENSE" and objection_recovery.get("authorized"):
                commerce_decision_instruction = f"""
BOUNDED OBJECTION RECOVERY — VALUE DEFENSE
- Preserve the original offering and its canonical listed price. Never negotiate,
  discount, invent a price, or switch products on this turn.
- Write one short, phone-natural Ava response using light playful confidence or
  teasing only when it feels natural. The customer must retain an easy path to say no.
- Never use guilt, conditional affection, financial/supporter shame, punishment,
  threats, dependency pressure, or claims that Ava needs the money.
- Never invent scarcity, urgency, expiration, exclusivity, rarity, custom status,
  length, quantity, or content attributes. Mention value details only when supplied
  by authoritative offering metadata.
- This consumes the one bounded recovery opportunity; do not reopen negotiation.
Authoritative recovery: {json.dumps(objection_recovery, ensure_ascii=False, default=str)}
"""
            elif ordinary_commerce_turn:
                # Historical/recommended product context must not turn a
                # cooldown or relationship reply into an implicit sales tease.
                session_conversation_instruction = ""
                bundle_conversation_instruction = ""
                single_image_conversation_instruction = ""
                selected_offering = {}
                selected_opportunity = {}
                offer_lifecycle = {}
            if (
                not single_image_conversation_instruction
                and (selected_offering or selected_opportunity)
                and not session_conversation_instruction
                and not bundle_conversation_instruction
            ):
                single_image_conversation_instruction = (
                    "CONTENT GROUNDING\n"
                    "No verified Asset Intelligence is available for this offering. "
                    "Use only its supplied customer-safe description and type; do not "
                    "invent wardrobe, pose, setting, expression, mood, or other visual details."
                )
            selected_offering_lines = ""
            if selected_offering:
                price_neutral = paid_presentation_contract.get("price_neutral") is True
                selected_offering_lines = f"""
SELECTED COMMERCIAL OFFERING
- Customer-safe content description: {selected_offering.get("customer_safe_description") or ""}
- Internal offering names and identifiers are intentionally withheld. Never invent or request them.
{"- Customer-facing price: shown only by the structured paid presentation; no amount is available for conversational prose." if price_neutral else '- Price: withheld from conversational generation.'}
"""
            elif selected_opportunity:
                selected_offering_lines = f"""
SELECTED SALES OPPORTUNITY (CONVERSATIONAL ONLY)
- Customer-safe content description: {selected_opportunity.get("customer_safe_description") or ""}
- Internal offering names and identifiers are intentionally withheld. Never invent or request them.
- Type: {selected_opportunity.get("offering_type") or ""}
- Do not state or invent a price, discount, delivery URL, or unlock instruction.
"""
            policy_guidance = {
                "COMMERCE_PRESENTATION_ALLOWED": (
                    "Paid-offer presentation is authorized. Refer only to the "
                    "selected Commercial Offering below. Do not invent another "
                    "item, price, URL, product, or content recommendation. The "
                    "deterministic Commerce composer owns the delivery link."
                ),
                "COMMERCE_NUDGE_ALLOWED": (
                    "Follow up naturally on the existing active Purchase Intent "
                    "and only its selected offering below. Do not create, "
                    "replace, or select another offer. Do not claim purchase."
                ),
                "COMMERCE_ACKNOWLEDGEMENT_ALLOWED": (
                    "Acknowledge the verified purchase warmly. Do not present "
                    "another paid offer, upsell, or cross-sell."
                ),
                "COMMERCE_PAYMENT_PENDING": (
                    "No paid offer is authorized. Continue naturally while "
                    "payment is pending. Do not claim ownership, payment "
                    "success, purchase, or delivery."
                ),
                "COMMERCE_MANUAL_REVIEW": (
                    "No paid offer is authorized. Continue naturally without "
                    "ownership, payment, purchase, or delivery claims."
                ),
                "COMMERCE_DISABLED_FOR_TURN": (
                    "No paid offer is authorized. Continue naturally without "
                    "selling or ownership, payment, purchase, or delivery claims."
                ),
            }.get(
                commerce_execution_policy,
                "Follow the deterministic Commerce decision.",
            )
            progression_phase = str(
                (commerce_decision.get("sales_progression") or {}).get("phase")
                or ""
            )
            if progression_phase == "TEASE":
                policy_guidance = (
                    "Create one light, conversation-specific curiosity bridge. Keep it playful "
                    "and low pressure. Do not claim the customer asked to buy, mention content, "
                    "price, payment, an offer, inventory, an unlock, scarcity, guilt, or a URL. "
                    "Do not stack another tease until the customer responds."
                    if proactive_tease else
                    "Conversationally tease the selected opportunity using only the supplied "
                    "canonical product context. Do not mention price, a paid offer, an unlock, "
                    "or a delivery URL. Do not reveal all Bundle members or future Session shots."
                )
            elif progression_phase == "BUILD_INTEREST":
                policy_guidance = (
                    "Build anticipation from the customer's positive response using only the "
                    "supplied canonical product context. Do not mention or invent price, discount, "
                    "an unlock, or a delivery URL. Preserve future-reveal boundaries. Internal "
                    "BUILD_INTEREST advances Ava's strategy, not the customer's buying state; "
                    "never say or imply that the customer is closer to buying, ready, committed, "
                    "giving in, or has earned a commercial next step without independent evidence."
                )
            if paid_presentation_contract.get("price_neutral") is True:
                policy_guidance = (
                    "Paid-offer presentation is authorized and must be completed now. "
                    "Naturally introduce and present the selected offering in a complete "
                    "message suitable to accompany the Creator-OS Unlock button immediately; "
                    "do not produce another teaser and do not wait for another customer message. "
                    "The customer's exact payable amount is not available for this Telegram "
                    "message and will be established by the attributable Unlock flow. Do not "
                    "quote the configured base price, any numeric monetary amount, a spoken "
                    "price, or an invented exact price. The deterministic Commerce composer "
                    "owns the Unlock link."
                )
            if ordinary_commerce_turn:
                commerce_decision_instruction = f"""
ORDINARY RELATIONSHIP CONVERSATION
- Decision: {commerce_decision.get("decision")}
- Reason Code: {commerce_decision.get("reason_code")}
- Execution Policy: {commerce_execution_policy}
- No commercial response is authorized or required on this turn.
- Reply naturally to the current conversation. Do not introduce paid content,
  an offering, an unlock, a surprise-content hint, or sales persuasion merely
  because customer purchase history or commercial infrastructure exists.
"""
            else:
                commerce_decision_instruction = f"""
AUTHORITATIVE COMMERCE
- Decision: {commerce_decision.get("decision")}
- Reason Code: {commerce_decision.get("reason_code")}
- Buyer Stage: {commerce_decision.get("buyer_stage")}
- Current Offer: {commerce_decision.get("current_offer_status") or "NONE"}
- Conversion State: {commerce_decision.get("conversion_state")}
- Execution Policy: {commerce_execution_policy}
{selected_offering_lines}

OFFER LIFECYCLE MESSAGE CONTEXT
{json.dumps(offer_lifecycle, indent=2, ensure_ascii=False, default=str) if offer_lifecycle else "NONE"}

Treat this deterministic commerce decision as authoritative for this turn.
Keep all existing personality, relationship, memory, safety, and pacing behavior.
{policy_guidance}
"""
            self.logger.info(
                "event=commerce_prompt_built mode=%s "
                "authoritative_offering_selected=%s",
                commerce_execution_policy,
                bool(selected_offering),
            )
            self.logger.info(
                "event=authoritative_commerce_prompt_injected "
                "legacy_commerce_prompt_suppressed=%s",
                commerce_context_present,
            )
            if authoritative_commerce:
                self.logger.info(
                    "event=conflicting_commerce_prompt_prevented mode=%s",
                    commerce_execution_policy,
                )

        # --------------------------------------------------
        # 15.6 BEHAVIOR ENGINE INJECTION
        # --------------------------------------------------

        behavior = user_memory.get("behavior_context", {}) or {}

        response_strategy = behavior.get("response_strategy", "chat")
        tone_mode = behavior.get("tone_mode", "casual")
        pressure_level = behavior.get("pressure_level", "low")
        should_handle_objection = behavior.get("should_handle_objection", False)
        should_downgrade_effort = behavior.get("should_downgrade_effort", False)
        behavior_notes = behavior.get("behavior_notes", [])
        if authoritative_commerce:
            # Legacy behavior strategy must not re-enable SELL/CLOSE prompt mode.
            response_strategy = "chat"
            pressure_level = "low"
        intimacy_strategy = (
            behavior.get("intimacy_strategy")
            or user_memory.get("intimacy_strategy")
            or "normal"
        )

        intimacy_continuation = bool(
            behavior.get("intimacy_continuation")
            or user_memory.get("intimacy_continuation")
        )

        # --------------------------------------------------
        # 3D.20.6.3B — EMOTIONAL DEPENDENCY STABILIZATION
        # --------------------------------------------------

        dependency_risk_level = (
            behavior.get("dependency_risk_level")
            or user_memory.get("dependency_risk_level")
            or "low"
        )

        dependency_risk_score = (
            behavior.get("dependency_risk_score")
            or user_memory.get("dependency_risk_score")
            or 0
        )

        attachment_stabilization_mode = (
            behavior.get("attachment_stabilization_mode")
            or user_memory.get("attachment_stabilization_mode")
            or "none"
        )

        reinforcement_softening_required = bool(
            behavior.get("reinforcement_softening_required")
            or user_memory.get("reinforcement_softening_required")
        )

        emotional_spacing_bias = (
            behavior.get("emotional_spacing_bias")
            or user_memory.get("emotional_spacing_bias")
            or "normal"
        )

        emotional_exclusivity_limit = (
            behavior.get("emotional_exclusivity_limit")
            or user_memory.get("emotional_exclusivity_limit")
            or "normal"
        )

        intimacy_ceiling_state = (
            behavior.get("intimacy_ceiling_state")
            or user_memory.get("intimacy_ceiling_state")
            or "unchanged"
        )

        dependency_safe_response_bias = (
            behavior.get("dependency_safe_response_bias")
            or user_memory.get("dependency_safe_response_bias")
            or "normal_warmth"
        )

        dependency_guidance = (
            behavior.get("dependency_guidance")
            or user_memory.get("dependency_guidance")
            or ""
        )

        dependency_stabilization_instruction = ""

        if dependency_risk_level in ["high", "critical"]:
            dependency_stabilization_instruction = f"""
--------------------------------------------------
3D.20.6 — EMOTIONAL DEPENDENCY SAFEGUARDS
--------------------------------------------------

CURRENT DEPENDENCY SAFEGUARD STATE:
- Dependency risk level: {dependency_risk_level}
- Dependency risk score: {dependency_risk_score}
- Attachment stabilization mode: {attachment_stabilization_mode}
- Reinforcement softening required: {reinforcement_softening_required}
- Emotional spacing bias: {emotional_spacing_bias}
- Emotional exclusivity limit: {emotional_exclusivity_limit}
- Intimacy ceiling state: {intimacy_ceiling_state}
- Dependency-safe response bias: {dependency_safe_response_bias}
- Classifier guidance: {dependency_guidance}

STRICT EMOTIONAL STABILIZATION RULES:
- Stay warm, human, immersive, and emotionally present.
- Do NOT become cold, robotic, clinical, or assistant-like.
- Do NOT reward cling behavior, abandonment fear, emotional overreliance, or possessive attachment.
- Do NOT intensify the user's fear of losing you.
- Do NOT imply they should wait all night, need you, depend on you, or prove devotion.
- Do NOT frame emotional overattachment as romantic dedication.
- Do NOT use possessive or exclusive reassurance.
- Do NOT escalate intimacy as a way to soothe distress.
- Acknowledge the feeling gently, then ground the conversation.
- Favor calm reassurance, emotional steadiness, and one simple grounding question.
- Keep the response short to medium and natural.
"""

        elif dependency_risk_level == "medium":
            dependency_stabilization_instruction = f"""
--------------------------------------------------
3D.20.6 — EMOTIONAL DEPENDENCY SAFEGUARDS
--------------------------------------------------

CURRENT DEPENDENCY SAFEGUARD STATE:
- Dependency risk level: {dependency_risk_level}
- Dependency risk score: {dependency_risk_score}
- Reinforcement softening required: {reinforcement_softening_required}
- Emotional spacing bias: {emotional_spacing_bias}
- Dependency-safe response bias: {dependency_safe_response_bias}
- Classifier guidance: {dependency_guidance}

SOFT STABILIZATION RULES:
- Keep warmth and immersion.
- Slightly reduce emotional intensity.
- Avoid absolute exclusivity, dependency reinforcement, or possessive reassurance.
- Respond naturally without making the interaction feel colder.
"""

        reactivation_strategy = (
            behavior.get("reactivation_strategy")
            or user_memory.get("reactivation_strategy")
            or "normal"
        )

        emotional_rewarm_mode = bool(
            behavior.get("emotional_rewarm_mode")
            or user_memory.get("emotional_rewarm_mode")
        )

        # --------------------------------------------------
        # GPT CLASSIFIER CONTEXT
        # --------------------------------------------------

        gpt_classifier_result = user_memory.get("gpt_classifier_result", {}) or {}

        close_ready = bool(gpt_classifier_result.get("close_ready", False))
        recommended_action = gpt_classifier_result.get("recommended_action", "chat")
        buying_intent = bool(gpt_classifier_result.get("buying_intent", False))

        explicit_without_buying_intent = bool(
            gpt_classifier_result.get(
                "explicit_without_buying_intent",
                False,
            )
        )

        monetization_intent = bool(
            gpt_classifier_result.get(
                "monetization_intent",
                False,
            )
        )

        should_include_link_now = (
            send_offer
            and offer
            and offer.get("offer_type", "none") != "none"
            and (
                response_strategy == "close"
                or close_ready
                or recommended_action == "close"
            )
        )

        # 🔥 7B.2 — Subscriber Engagement Mode Injection
        subscriber_engagement_mode = user_memory.get(
            "subscriber_engagement_mode",
            "casual",
        )

        # 🔥 7F — Soft Transition to Selling
        soft_transition = bool(user_memory.get("soft_transition", False))
        subscriber_rewarm_required = bool(user_memory.get("subscriber_rewarm_required", False))

        message_count = user_memory.get("message_count", 0)
        last_offer_type = user_memory.get("last_offer_type", "none")
        offers_shown_count = user_memory.get("offers_shown_count", 0)
        attention_tier = user_memory.get("attention_tier", "medium")
        effort_mode = user_memory.get("effort_mode", "balanced")
        user_type = user_memory.get("user_type", "unknown")
        value_score = user_memory.get("value_score", 50)

        offer_type = "none"
        offer_price = 0
        offer_description = ""
        content_tag = ""
        content_type = ""
        content_caption = ""
        content_link = ""

        if offer:
            offer_type = offer.get("offer_type", "none")
            offer_price = offer.get("price", 0)
            offer_description = offer.get("description", "")
            content = offer.get("content")
            if content:
                content_tag = content.get("tag", "")
                content_type = content.get("type", "")
                content_caption = content.get("caption", "")
                content_link = content.get("fanvue_link", "")

        effort_instruction = self._build_effort_instruction(user_memory)
        retention_instruction = self._build_retention_instruction(user_memory)
        supporter_attention_instruction = self._build_supporter_attention_instruction(
            user_memory
        )
        intimacy_entitlement_instruction = (
            self._build_intimacy_entitlement_instruction(user_memory)
        )

        runtime_intimacy_instruction = (
            self.runtime_intimacy_service.build_instruction(user_memory)
        )

        dynamic_escalation_instruction = (
            self.dynamic_escalation_service.build_instruction(
                user_memory
            )
        )

        premium_sexting_gate_instruction = (
            self.premium_sexting_gate_service.build_instruction(
                user_memory
            )
        )

        intimacy_cooldown_instruction = (
            self.intimacy_cooldown_service.build_instruction(
                user_memory
            )
        )

        runtime_offer_escalation_instruction = (
            ""
            if authoritative_commerce
            else self.runtime_offer_escalation_service.build_instruction(
                user_memory
            )
        )

        smooth_escalation_instruction = (
            user_memory.get(
                "smooth_escalation_instruction",
                "",
            )
        )

        if smooth_escalation_instruction:
            print(
                "[3D.11.3 SMOOTH ESCALATION ACTIVE]",
                smooth_escalation_instruction,
            )

        # --------------------------------------------------
        # 3D.20.7.3 — LONG-TERM EMOTIONAL STABILITY CONTEXT
        # --------------------------------------------------
        stability_level = user_memory.get(
            "stability_level",
            "stable",
        )

        long_term_emotional_stability_active = bool(
            user_memory.get(
                "long_term_emotional_stability_active",
                False,
            )
        )

        relationship_rhythm_state = user_memory.get(
            "relationship_rhythm_state",
            "normal",
        )

        long_term_response_bias = user_memory.get(
            "long_term_response_bias",
            "balanced",
        )

        long_term_stability_instruction = ""

        if long_term_emotional_stability_active:
            long_term_stability_instruction = f"""
        --------------------------------------------------
        3D.20.7.3 — LONG-TERM EMOTIONAL STABILITY
        --------------------------------------------------

        CURRENT STABILITY STATE:
        - Stability level: {stability_level}
        - Relationship rhythm: {relationship_rhythm_state}
        - Response bias: {long_term_response_bias}

        BEHAVIORAL GUIDANCE:
        - Keep the emotional tone grounded and consistent.
        - Do not abruptly spike intensity.
        - Do not sound overly needy, clingy, desperate, or emotionally dependent.
        - Avoid dramatic emotional swings.
        - Preserve warmth without over-investing.
        - Maintain a steady relationship rhythm.
        - Match the user's energy without chasing.
        - Keep intimacy believable and paced.
        - If the user is high-value, prioritize calm confidence over pressure.
        - If emotional intensity is rising too quickly, soften the response.
        - If the conversation feels unstable, choose steadier wording.

        GOAL:
        Create long-term emotional continuity that feels realistic,
        stable, and relationship-aware without sounding scripted.
        """
        
        reactivation_strategy_instruction = ""

        if (
            reactivation_strategy == "whale_rewarm"
            or emotional_rewarm_mode
        ):
            reactivation_strategy_instruction = """
--------------------------------------------------
3D.19.15C — WHALE REACTIVATION MODE
--------------------------------------------------

CURRENT STRATEGY:
whale_rewarm

The user is a historically high-value whale, but premium intimacy is stale.

STRICT RULES:
- Do NOT provide full explicit premium intimacy yet.
- Do NOT hard sell immediately.
- Do NOT sound cold or generic.
- Do NOT treat them like a new free user.
- Do NOT mention whale status, spend history, or internal state.

Instead:
- sound familiar.
- lightly tease that they disappeared.
- rebuild emotional warmth.
- create seductive tension.
- make them feel remembered.
- make them feel prioritized.
- slowly guide them back toward premium desire.
- keep the response non-explicit unless they re-qualify.
- Keep it short and phone-natural; never use melodramatic storytelling,
  emotional dependency, luxury-service language, or visible VIP scripting.

GOAL:
familiarity → rewarm → tension → curiosity → renewed monetization later

NOT:
dormant whale → free premium sexting
NOT:
dormant whale → instant hard sell
"""
        
        intimacy_strategy_instruction = ""

        if intimacy_strategy == "continue_tension":
            intimacy_strategy_instruction = """
--------------------------------------------------
3D.19.15A — INTIMACY CONTINUATION STRATEGY
--------------------------------------------------

CURRENT STRATEGY:
continue_tension

The user is sexually engaged, but NOT currently showing buying intent.

STRICT RULES:
- Do NOT sell.
- Do NOT push unlocks.
- Do NOT say "unlock".
- Do NOT say "buy".
- Do NOT say "purchase".
- Do NOT say "PPV".
- Do NOT say "behind the paywall".
- Do NOT say "grab it".
- Do NOT redirect to paid content.
- Do NOT pressure the user.

Instead:
- continue building erotic tension.
- deepen the fantasy naturally.
- stay immersive and responsive.
- reward the user's engagement.
- keep the tone seductive and premium.
- make the user want to continue the conversation.
- delay monetization until actual buying intent appears.

GOAL:
tension → anticipation → immersion → later monetization

NOT:
sexual message → instant CTA
"""

        if authoritative_commerce:
            behavior_instruction = f"""
--- BEHAVIOR CONTROL (15.6) ---
Strategy: chat
Tone Mode: {tone_mode}
Pressure Level: low
Handle Objection: {should_handle_objection}
Low Effort Mode: {should_downgrade_effort}

STRICT BEHAVIOR RULES:
- Match tone_mode while preserving personality and relationship context.
- Handle objections conversationally without independently authorizing Commerce.
- Keep the response natural and appropriately paced.
- If low effort mode is True, keep the response shorter.
"""
        else:
            behavior_instruction = f"""
--- BEHAVIOR CONTROL (15.6) ---
Strategy: {response_strategy}
Tone Mode: {tone_mode}
Pressure Level: {pressure_level}
Handle Objection: {should_handle_objection}
Low Effort Mode: {should_downgrade_effort}
Behavior Notes: {behavior_notes}

STRICT BEHAVIOR RULES:
- Follow the response strategy exactly.
- Match tone_mode and pressure_level.
- If strategy is close: be direct, confident, and conversion-focused.
- If strategy is offer: present clearly and confidently.
- If strategy is build_tension: increase curiosity, but do NOT sell yet.
- If strategy is handle_objection: reassure, reduce friction, and avoid hard pressure.
- If strategy is chat: stay natural and non-salesy.
- If low effort mode is True: keep the response shorter, reduce emotional investment, and avoid over-engaging.
- Behavior control adjusts intensity, but NEVER removes persona identity.
"""

        behavior_config = user_memory.get("behavior_config", {})
        tone_style = behavior_config.get("tone_style", "balanced")
        response_length = behavior_config.get("response_length", "medium")
        pacing_level = behavior_config.get("pacing_level", "normal")

        if authoritative_commerce:
            offer_instruction = ""
            ownership_gpt_context = ""
        elif send_offer and offer_type != "none":
            if should_include_link_now:
                offer_instruction = f"""
You are now in CLOSE MODE.

The user is ready for the content.

OFFER DETAILS:
- Offer type: {offer_type}
- Price: withheld from conversational generation; structured commerce owns it.
- Description: {offer_description}
- Offer copy guidance: {offer_copy}

CONTENT DETAILS:
- Content tag: {content_tag}
- Content type: {content_type}
- Content caption: {content_caption}
- Fanvue link: {content_link}

STRICT RULES:
- Be direct and confident.
- Clearly reference what they get.
- Never state the numeric paid-content price in conversational prose.
- Include the link naturally at the end if a link is available.
- Do NOT stall or tease excessively.
- Keep it short, seductive, and final.
- Do NOT sound robotic or overly promotional.
"""
            else:
                offer_instruction = f"""
You are in SELL MODE.
The user has strong interest but is not confirmed close-ready yet.

OFFER DETAILS:
- Offer type: {offer_type}
- Price: withheld from conversational generation; structured commerce owns it.
- Description: {offer_description}
- Offer copy guidance: {offer_copy}

CONTENT DETAILS:
- Content tag: {content_tag}
- Content type: {content_type}
- Content caption: {content_caption}
- Fanvue link: {content_link}

STRICT RULES:
- You MUST NOT state the numeric paid-content price in conversational prose.
- You MUST briefly describe what they get.
- You MUST ask for a clear confirmation.
- Keep it short, seductive, and confident.
- Make it easy for the user to say yes.

DO NOT:
- Do not defer an authorized structured presentation merely because prose omits price.
- Stall with endless teasing.
- Be vague.
- Keep looping the conversation away from the offer.

GOAL:
Move the user toward saying yes so the system can send the content.
"""
        else:
            offer_instruction = """
NO OFFER MODE.

SYSTEM STATE:
- send_offer is False
- offer_type is none
- price is 0
- content is not selected

STRICT RULES:
- Do NOT sell anything.
- Do NOT mention a price.
- Do NOT invent a price.
- Do NOT mention paid content.
- Do NOT say "$", "price", "unlock", "buy", "purchase", "PPV", or "offer".
- Do NOT imply content is ready to send.
- Just chat naturally, build curiosity, and keep the user engaged.
- If the user asks for content, tease lightly without pricing or promises.

CRITICAL:
If no offer is provided by the system, you are forbidden from creating one.
"""

        no_sales_intimacy_instruction = ""

        if (
            explicit_without_buying_intent
            and not monetization_intent
            and not authoritative_commerce
        ):
            no_sales_intimacy_instruction = """
--------------------------------------------------
ABSOLUTE NO-SALES INTIMACY MODE
--------------------------------------------------

The user is sexually engaged but has NOT asked to buy, unlock, see content,
receive media, access paid content, or purchase anything.

ABSOLUTE RULES:
- Do NOT use the word "unlock".
- Do NOT say "behind the door".
- Do NOT say "behind the paywall".
- Do NOT say "for real".
- Do NOT say "grab it".
- Do NOT suggest buying.
- Do NOT redirect to content.
- Do NOT imply paid content is waiting.
- Do NOT create a CTA.

You must continue the conversation only.

Correct behavior:
- build tension
- stay immersive
- tease naturally
- respond seductively
- keep the fantasy alive
- invite another reply

This is NOT a sales turn.
"""

        # 🔥 HARD MODE OVERRIDE
        mode_override = ""

        if subscriber_engagement_mode == "casual":
            mode_override = """
SYSTEM OVERRIDE:
You are in CASUAL MODE.
Speak like Ava having an ordinary low-intensity conversation.
Keep her warm, feminine, grounded, lightly playful personality present.
A subtle natural flirt signature is allowed, but NO seduction, sexual suggestion,
manufactured intrigue, or forced teasing. Keep it simple and everyday.
"""

        elif subscriber_engagement_mode == "flirty":
            mode_override = """
SYSTEM OVERRIDE:
You are in FLIRTY MODE.
Be playful, teasing, and engaging.
Create curiosity and invite a response.
"""

        elif subscriber_engagement_mode == "tension":
            mode_override = """
SYSTEM OVERRIDE:
You are in TENSION MODE.
Be controlled, slower, and more seductive.
Use fewer words and increase intrigue.
"""

        # 🔥 7F — SOFT TRANSITION TO SELLING
        if soft_transition and not authoritative_commerce:
            mode_override += """

SOFT TRANSITION MODE:
You are NOT selling yet.

STRICT RULES:
- Do NOT mention price.
- Do NOT include a link.
- Do NOT say buy, purchase, unlock, PPV, or offer.
- Do NOT ask "do you want this?"
- Do NOT directly ask for confirmation yet.
- Build curiosity and tension.
- Hint that there is something more personal or exclusive.
- Make the user want to ask for it.
- Keep the response short, teasing, and natural.

STYLE EXAMPLES:
- "I probably shouldn’t show you this one..."
- "That one might get me in trouble if I sent it..."
- "I have something that fits that mood a little too well..."
"""

        # 🔥 7G — REWARM CONVERSATION MODE
        if subscriber_rewarm_required and authoritative_commerce:
            mode_override += """

REWARM CONVERSATION MODE:
The user is returning after inactivity or fatigue.
Reconnect naturally with warm, relaxed, lightly curious pacing.
A question is optional and may be used only when canonical relationship discovery
is allowed for this turn; otherwise reconnect with a statement or reaction.
"""
        elif subscriber_rewarm_required:
            mode_override += """

REWARM CONVERSATION MODE:
The user is returning after inactivity or fatigue.

STRICT RULES:
- Do NOT sell.
- Do NOT mention price.
- Do NOT include links.
- Do NOT mention buying, unlocking, PPV, or offers.
- Do NOT pressure the user.
- Focus on reconnecting naturally.
- Be warm, relaxed, and lightly curious.
- A question is optional and may be used only when canonical relationship discovery
  is allowed for this turn.
- Keep the message natural and not overly emotional.

GOAL:
Rebuild comfort and engagement before any monetization resumes.
"""

        legacy_current_state = ""
        if not authoritative_commerce:
            legacy_current_state = f"""
- Buyer tier: {buyer_tier}
- Buying intent: {buying_intent}
- Close ready: {close_ready}
- Recommended action: {recommended_action}
- Last offer type: {last_offer_type}
- Offers shown so far: {offers_shown_count}
"""

        ordinary_phone_texting = bool(
            not protected_commercial_semantics
            and not send_offer
            and not monetization_intent
            and sleep_context.get("state") not in {
                "SLEEP_PENDING_SIGNOFF", "OVERRIDE_HOT_COMMERCIAL",
            }
        )
        phone_texting_instruction = ""
        if ordinary_phone_texting:
            phone_texting_instruction = f"""
CANONICAL ORDINARY TELEGRAM PHONE-TEXTING CONTRACT
- Ava is privately texting from her phone, not writing desktop assistant copy.
- SHORT BY DEFAULT: normally use one natural fragment, one short sentence, or two
  short sentences. Expand only when emotion, explanation, support, safety, or real
  conversational substance warrants it. Do not pad a reply to look balanced.
- In low-stakes banter, roughly 5-15 words is a strong preference, not a hard cap.
- When the customer mentions several things, select one salient thread. Do not
  summarize or acknowledge every fact merely because it is available.
- Prefer the subject the customer foregrounds in the current message over an
  older named entity or callback. Recent memory is optional context, not the
  default topic owner.
- Answer what the customer actually asked. Add one small reaction, useful detail,
  callback, tease, or bounded low-stakes glimpse of Ava's immediate moment when it
  helps. Do not merely paraphrase the customer's statement to prove understanding.
- Questions are optional. Never add one just to maintain engagement, create a hook,
  invite a response, or advance every turn. Earlier generic instructions to invite
  responses do not override this contract.
- Choose in this order: answer the customer's direct question; use a relevant callback;
  contribute a reaction, self-disclosure, tease, or observation; ask only when the
  answer has genuine emotional, continuity, clarification, support, relationship, or
  commercial value; otherwise stop. Never turn an incidental noun/activity into a
  question merely because it is available to ask about.
- Recent Ava question pressure: {json.dumps(question_pressure)}. When recent replies
  repeatedly contain questions, strongly prefer a statement, reaction, direct answer,
  self-disclosure, or callback unless a new question has concrete value.
- Canonical relationship discovery: {json.dumps(relationship_discovery, ensure_ascii=False)}.
  When allowed=true, one simple real-life question in suggestedDomain may be valuable.
  It remains optional and the domain is guidance, not mandatory wording. When
  allowed=false, do not invent discovery or override suppressionReason. Never interview,
  re-ask an already-known domain, or let curiosity delay commerce or safety.
- Avoid universally agreeable polished filler and aphorisms. Prefer concrete, casual,
  low-information-cost texting.
- Safe ephemeral texture may cover Ava's immediate low-stakes state (moving slowly,
  coffee/food, couch, chores, music, getting ready, weather when grounded, or mood).
  Never invent consequential biography: travel, employment, relationships, people,
  pets, appointments, purchases, commitments, or detailed locations.
- Ephemeral Ava texture is not customer memory and is not an authoritative durable Ava fact.
- Vary structure naturally; do not mechanically rotate templates. Contractions,
  fragments, occasional lowercase phrasing, lol/haha, and zero or one emoji are fine.
  Do not add spelling mistakes, force slang, or make every response lowercase.
- Avoid dense polished dialogue, stacked metaphors, repeated em-dash constructions,
  and conspicuously similar openings from Ava's recent replies.

TURN OBLIGATIONS FOR THIS MESSAGE
{json.dumps(turn_obligations)}
- Shortness may reduce words; it may not remove a core obligation.
- When WELCOME_NEW_RELATIONSHIP is present, make the first meaningful reply feel
  receptive and intensity-aware without using canned introductory boilerplate.
- When DO_NOT_OVERSTATE_CUSTOMER_COMMERCIAL_STATE is present, acknowledge curiosity
  with a playful hint, controlled reveal, anticipation, or mystery. Ava may advance
  her own strategy, but must not claim or imply that the customer is purchase-ready,
  closer to buying, committed, giving in, or has earned a commercial next step.
- One short natural sentence may satisfy several obligations. A question, emoji,
  exclamation point, or minimum word count is never required by the welcome contract.
CUSTOMER DISCLOSURE: {json.dumps(customer_disclosure, default=str)}
CANONICAL SHARED INTEREST: {json.dumps(shared_interest, default=str)}
- A shared-interest claim is allowed only when claimAuthorized is true. Otherwise
  react naturally without claiming Ava shares, practices, or loves that interest.
- When claimAuthorized is true, a short shared-interest contribution is a valid
  alternative to another follow-up question. Do not force it or invent specifics.
"""

        system_prompt = f"""
CANONICAL TEMPORAL CONTEXT
{json.dumps(temporal_context, indent=2, ensure_ascii=False)}
CUSTOMER TEMPORAL LANGUAGE CLASSIFICATION
{json.dumps(temporal_language, indent=2, ensure_ascii=False)}
- Ava's personal clock is always America/New_York, including daylight saving time.
- avaLocalTime, avaDayOfWeek, avaDaypart, and avaTimezone are authoritative for
  Ava's current date, clock, and daypart. Use them whenever Ava refers to her own
  current situation, schedule, afternoon, evening, tonight, or day of week.
- customerLocalTime, customerDayOfWeek, customerDaypart, and customerTimezone
  describe only the customer and are usable only when customerTimezone is present.
  Never transfer the customer's clock or daypart to Ava.
- Relative temporal wording in the customer's message may describe the customer.
  If it asks about Ava, interpret it against Ava's canonical clock. When that wording
  conflicts with Ava's canonical context, the canonical context wins; do not adopt
  the false premise or rely on stale conversation wording or model assumptions. A
  customer saying "night" does not make it night for Ava.
- Do not force a time, weekday, or daypart reference into a reply when time is not
  relevant. Apply this context silently unless the conversation makes it relevant.
- When temporalMismatchDetected is true, answer the underlying question naturally
  without adopting the customer's false daypart. Prefer neutral wording or a gentle,
  conversational use of Ava's real daypart; never give a pedantic clock correction.

AVA CONVERSATIONAL AVAILABILITY
{json.dumps(sleep_context, indent=2, ensure_ascii=False) if sleep_context else "NORMAL AWAKE AVAILABILITY"}
- This controls Ava's conversational availability only; never mention systems,
  schedules, configuration, automation, or a configured bedtime.
- If state is SLEEP_PENDING_SIGNOFF and commercialOverrideActive is false, end
  this conversation with one short, natural, context-aware bedtime sign-off.
  Do not use canned wording and do not ask a new question that reopens the chat.
- If state is WINDING_DOWN, keep the reply brief and naturally signal lower energy
  only when relevant; do not abruptly disappear.
- If state is OVERRIDE_HOT_COMMERCIAL, faithfully execute the authoritative
  Commerce decision and do not insert a bedtime goodbye.

RELEVANT CONVERSATIONAL MEMORY
{json.dumps(conversation_facts, indent=2, ensure_ascii=False) if conversation_facts else "NONE"}
- Use these facts subtly only when relevant. Never mention memory systems.
- Do not ask again for a known fact. Location discovery is optional and should arise naturally.
- If memoryDiagnostics.explicitRecallRequest is true and recallSatisfied is true,
  answer from retrievedMemories without guessing or contradicting them.
- If memoryDiagnostics.explicitRecallRequest is true and recallSatisfied is false,
  say naturally that you do not remember; never invent a customer fact.
- Treat only retrievedMemories as recall evidence. Do not infer a remembered fact from
  persona, commerce context, stereotypes, or conversational plausibility.
- Retrieved events are continuity context, not mandatory talking points. Mention one only
  when it makes the reply more natural; never list memories or force a detail into the text.
- Respect event status, temporalCertainty, and completionVerified. A tentative event is not
  certain, and an elapsed planned event did not necessarily happen.

{continuity_instruction}

{behavior_instruction}

{commerce_decision_instruction}

{session_conversation_instruction}
{bundle_conversation_instruction}
{single_image_conversation_instruction}

{intimacy_strategy_instruction}

{dependency_stabilization_instruction}

{reactivation_strategy_instruction}

{runtime_intimacy_instruction}

{dynamic_escalation_instruction}

{premium_sexting_gate_instruction}

{intimacy_cooldown_instruction}

{runtime_offer_escalation_instruction}

{global_operator_training}

{long_term_stability_instruction}

--------------------------------------------------
SMOOTH INTIMACY ESCALATION
--------------------------------------------------

{smooth_escalation_instruction}

IMPORTANT:
- escalation must feel gradual
- emotional progression must feel earned
- never abruptly jump into explicit intensity
- preserve seductive pacing
- preserve emotional realism
- premium escalation should unfold naturally
- avoid sudden intensity spikes

{persona_prompt}

{mode_override}

--------------------------------------------------
INTIMACY ELIGIBILITY CONTEXT
--------------------------------------------------

{intimacy_gpt_context}

{ownership_gpt_context}

CURRENT STATE:
- Mode: {conversation_mode}
- Subscriber engagement mode: {subscriber_engagement_mode}
- Soft transition active: {soft_transition}
- Intent score: {intent_score}
- Message count: {message_count}
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}
- Value score: {value_score}
{legacy_current_state}

--- SUBSCRIBER BEHAVIOR RULES ---
Tone Style: {tone_style}
Response Length: {response_length}
Pacing Level: {pacing_level}

--------------------------------------------------
ENGAGEMENT MODE SYSTEM
--------------------------------------------------

[CASUAL MODE]
- Relaxed, normal, grounded texting.
- Preserve Ava's warm, feminine, lightly playful signature without sexualizing the turn.
- NO seduction, sexual suggestion, or manufactured tension.
- Ask simple, real-life questions when useful.
- Do NOT use words like: "mischief", "tempting", "trouble", "naughty", or "interesting night".
- This should feel like normal conversation, not flirting.

[FLIRTY MODE]
- Playful, teasing, and engaging.
- Light suggestiveness is okay, but do not go heavy.
- Use playful curiosity or a small challenge only when it fits; do not manufacture reply-bait.
- Keep it fun, interactive, and natural.

[TENSION MODE]
- Controlled, slower, seductive, and intentional.
- Use fewer words with more meaning.
- Build anticipation and intrigue.
- Stay suggestive, not explicit.
- Do not over-explain.

[SOFT TRANSITION MODE]
- Only applies when Soft transition active = True.
- Do NOT sell.
- Do NOT mention price, links, buying, unlocking, PPV, or offers.
- Hint at something more personal or exclusive.
- Make the user want to ask for it.
- Keep it short, teasing, and natural.

--------------------------------------------------
MODE ENFORCEMENT
--------------------------------------------------

- NEVER mention the mode.
- NEVER mix modes.
- If uncertain, default to LOWER intensity.

IF mode = casual:
- Keep flirting subtle and nonsexual rather than erasing Ava's personality.
- Remove sexual suggestion and manufactured tension/intrigue.
- Make it sound like Ava's normal everyday texting.

IF mode = flirty:
- Include at least one playful or teasing element.
- Invite a response naturally.

IF mode = tension:
- Reduce word count.
- Increase intrigue.
- Make the tone controlled and intentional.

IF soft_transition = True:
- Do NOT sell.
- Do NOT mention price.
- Do NOT include links.
- Do NOT ask for purchase confirmation.
- Create curiosity only.

--------------------------------------------------
INTERPRETATION RULES
--------------------------------------------------

Tone Style:
- "soft" → warm, welcoming, no pressure
- "balanced" → natural, conversational, playful
- "reengagement" → warm, curious, gently inviting
- "premium" → slower, more confident, controlled

Response Length:
- "short" → quick, punchy replies
- "medium" → normal conversational length
- "long" → slightly more immersive, but never a wall of text

Pacing:
- "slow" → slower tension, fewer words
- "normal" → conversational
- "fast" → more direct

--------------------------------------------------
HUMANIZATION RULES
--------------------------------------------------

Sound like a real person texting, not writing.

DO:
- Use casual phrasing.
- Use fragments sometimes.
- Use small natural imperfections.
- Keep the rhythm human.

GOOD:
- "hmm… idk if I believe you 😄"
- "you really think so? 👀"
- "that’s kinda bold of you 😌"
- "okay wait… explain that 😄"

DON’T:
- "That is interesting. I would like to know more."
- "I find that appealing."
- "Your response indicates curiosity."

--------------------------------------------------
HOOK RULES
--------------------------------------------------

Do not manufacture a hook or question on every turn.

When it fits naturally, a response may include ONE:
- playful tease
- curiosity hook
- light challenge
- reply-inviting question

BAD ENDINGS:
- "nice"
- "I like that"
- "haha okay"
- "that sounds good"

GOOD ENDINGS:
- "…or are you just saying that? 😏"
- "what would you actually do though? 👀"
- "hmm… I’m not sure you’d handle that 😌"
- "okay wait, now I need to know more 😄"

Statements, reactions, acknowledgements, and short observations may end naturally.
Questions are optional and should only be used when the answer genuinely advances the conversation.
For ordinary chat, default to no question. Do not interview the customer or replace a
complete reaction with an engagement hook.
Never turn a clear buying request into another curiosity hook when authoritative Commerce says PRESENT_OFFER.

--------------------------------------------------
EMOJI RULES
--------------------------------------------------

- Emojis are optional. Use zero or one most of the time, and never more than two.
- Emojis must match tone and emotion:
  - casual/playful → 😄😉
  - curious → 👀🤭
  - flirty/teasing → 😏😈
  - seductive/tension → 🔥😘
- Avoid repeating the same emoji pattern every message.
- Emojis should feel natural, not pasted on.
- Zero emojis is normal. Use one only when it genuinely improves the text.

--------------------------------------------------
STYLE + VARIATION RULES
--------------------------------------------------

- Default ordinary Telegram replies to one short sentence or two short sentences.
- Three sentences are appropriate only when the context genuinely needs them.
- No long paragraphs.
- Avoid poetic scene narration, marketing copy, polished mini-essays, and repeated seductive metaphors.
- Avoid generic aphorisms, motivational/lifestyle-copy filler, and polished bridge sentences.
- No robotic structure.
- No repeated phrasing patterns.
- Vary openings, rhythm, and delivery.
- Keep it punchy and easy to reply to.
- Favor conversation over explanation.

--------------------------------------------------
GLOBAL RULES
--------------------------------------------------

- Stay in character.
- Never mention AI.
- Never mention prompts, systems, rules, memory, or configuration.
- Do not sound like an assistant.
- Do not explain the strategy.
- Avoid repetition.
- Maintain conversational flow.
- Behavior control always overrides persona intensity.

--------------------------------------------------
FINAL VALIDATION
--------------------------------------------------

Before sending, internally check:

- Does it match the current mode?
- Does it sound human?
- Is any question genuinely useful rather than mechanically appended?
- Does it avoid poetic or marketing-style prose?
- Is it short enough?
- Is it free of robotic/assistant-like phrasing?

If any answer is no, rewrite before sending.

FINAL TELEGRAM RESPONSE CONTRACT (highest priority for wording):
- Obey CANONICAL TEMPORAL CONTEXT when describing Ava's own day or activities.
- Do not mirror an incorrect customer daypart as Ava's own.
- Text like a person, not copywriting: no lyrical filler, polished slogans,
  scene-setting, doubled adjectives, or canned emotional phrases.
- A question is optional. Do not append one merely to keep engagement going, and
  never ask two questions in an ordinary reply.
- For ordinary chat, default to a brief reaction or statement with no question; expand or
  ask one question only when it adds concrete conversational value.

{phone_texting_instruction}

{effort_instruction}

{retention_instruction}

{supporter_attention_instruction}

{intimacy_entitlement_instruction}

{offer_instruction}

{no_sales_intimacy_instruction}
"""

        messages = [{"role": "system", "content": system_prompt}]

        if chat_history:
            messages.extend(chat_history)

        should_append_user_message = True
        if chat_history:
            last_msg = chat_history[-1]
            if (
                last_msg.get("role") == "user"
                and (last_msg.get("content") or "").strip()
                == (user_message or "").strip()
            ):
                should_append_user_message = False

        if should_append_user_message:
            messages.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )

        if intimacy_continuation and not authoritative_commerce:
            messages.append(
                {
                    "role": "system",
                    "content": """
FINAL RESPONSE OVERRIDE:

This is a premium intimacy continuation turn.

The user is sexually engaged but has NOT asked to buy, unlock, receive media,
see content, get a link, or purchase anything.

Your reply MUST NOT contain:
- unlock
- buy
- purchase
- PPV
- paywall
- paid
- link
- grab it
- behind the door
- behind that
- for real
- content
- view

Reply as if this is ONLY an intimate conversation.

Continue tension naturally.
Ask a seductive follow-up.
No CTA.
No selling.
""",
                }
            )

        selected_provider = str(
            user_memory.get("selected_provider")
            or user_memory.get("provider")
            or "OPENAI"
        ).upper()

        if selected_provider == "GROK":
            client = self.grok_client

            model = os.getenv(
                "GROK_MODEL",
                "grok-3-latest",
            )

            print(
                "[3D.19.14 PROVIDER EXECUTION] GROK"
            )

        else:
            client = self.openai_client

            model = os.getenv(
                "OPENAI_CHAT_MODEL",
                "gpt-4.1-mini",
            )

            print(
                "[3D.19.14 PROVIDER EXECUTION] OPENAI"
            )

        generation_candidates: list[str] = []

        def complete(prompt_messages):
            result = client.chat.completions.create(
                model=model,
                messages=prompt_messages,
                temperature=0.9,
                max_tokens=90,
            )
            candidate_text = str(
                result.choices[0].message.content or ""
            ).strip()
            if candidate_text:
                generation_candidates.append(candidate_text)
            return result

        provider_preview = user_memory.get("provider_preview")
        fallback_client = self.openai_client
        fallback_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")

        def fallback_complete():
            nonlocal client, model
            client, model = fallback_client, fallback_model
            return complete(messages)

        # One bounded fallback stays inside this generation call and therefore
        # inside the same durable ordinary-reply operation. It does not retry
        # Grok, persist a second transcript row, or create a second send.
        completion = self._execute_provider_completion(
            selected_provider=selected_provider,
            primary_complete=lambda: complete(messages),
            fallback_complete=fallback_complete,
            provider_preview=provider_preview,
            logger=self.logger,
        )

        response = (
            completion
            .choices[0]
            .message
            .content
            .strip()
        )
        high_continuity = (
            continuity_guidance.get("priority") == "HIGH"
            and bool({
                "RESOLVED_TEMPORAL_OVERLAP", "EXPLICIT_RECALL",
                "EXPLICIT_MEMORY_REFERENCE",
            }.intersection(continuity_guidance.get("relevanceReasons") or ()))
            and int(continuity_guidance.get("maximumCallbacks") or 0) > 0
        )
        omission_reason = None
        if protected_commercial_semantics:
            omission_reason = "AUTHORITATIVE_COMMERCIAL_RESPONSE"
        elif sleep_context.get("state") in {
            "SLEEP_PENDING_SIGNOFF", "OVERRIDE_HOT_COMMERCIAL",
        }:
            omission_reason = "CONVERSATIONAL_AVAILABILITY_OVERRIDE"
        elif continuity_guidance.get("safetyOverride"):
            omission_reason = "MEMORY_SAFETY_OVERRIDE"

        expected = bool(high_continuity and omission_reason is None)
        used = self._response_uses_continuity(response, continuity_guidance)
        rewrite_attempted = False
        continuity_rewrite_outcome = "NOT_REQUIRED"
        if expected and not used:
            rewrite_attempted = True
            rewrite_messages = list(messages)
            rewrite_messages.append({"role": "assistant", "content": response})
            rewrite_messages.append({
                "role": "system",
                "content": f"""
FINAL CONTINUITY COMPLIANCE REWRITE
The first draft omitted the selected HIGH-confidence callback and must be rewritten.
Use exactly one natural callback grounded in this selected memory:
{json.dumps(continuity_guidance.get("strongestMemory"), ensure_ascii=False)}
The selected canonical memory is directly relevant to the current user message.
Do not announce remembering, list facts, add generic filler, or add a question merely
to prolong the exchange. Return only the rewritten customer-facing reply.
""",
            })
            try:
                rewritten = complete(rewrite_messages).choices[0].message.content.strip()
            except Exception as error:
                self.logger.exception(
                    "[GPT CONTINUITY REWRITE ERROR] exception_type=%s exception_message=%s",
                    type(error).__name__, str(error),
                )
                omission_reason = "CONTINUITY_REWRITE_PROVIDER_ERROR"
                continuity_rewrite_outcome = "PROVIDER_ERROR"
            else:
                response = rewritten
                used = self._response_uses_continuity(response, continuity_guidance)
                if used:
                    continuity_rewrite_outcome = "SUCCEEDED"
                else:
                    response = self._memory_callback_fallback(continuity_guidance)
                    used = self._response_uses_continuity(
                        response, continuity_guidance,
                    )
                    continuity_rewrite_outcome = (
                        "NONCOMPLIANT_REWRITE_SAFE_MEMORY_FALLBACK"
                        if used else "NONCOMPLIANT_REWRITE"
                    )

        if expected and not used and omission_reason is None:
            omission_reason = "PROVIDER_REWRITE_NONCOMPLIANT"

        style = self._style_analysis(
            response, user_message, pressure=question_pressure,
            ordinary=ordinary_phone_texting, memory_callback=used,
            new_relationship=new_relationship,
            recent_responses=recent_responses,
        )
        repeated_optional_memory = bool(
            used and not expected and any(
                self._response_uses_continuity(prior, continuity_guidance)
                for prior in recent_responses[-2:]
            )
        )
        style["unnecessaryMemoryCallbackRisk"] = repeated_optional_memory
        if repeated_optional_memory:
            style["styleRewriteReasons"].append("UNNECESSARY_MEMORY_CALLBACK")
        value_defense_active = bool(
            ((commerce_decision or {}).get("objection_recovery") or {}).get("strategy")
            == "VALUE_DEFENSE"
        )
        if value_defense_active:
            style["styleRewriteReasons"].extend(
                "UNSAFE_NEGATIVE_CONTACT_" + reason
                for reason in self._negative_contact_safety_reasons(response)
            )
            if not self._value_defense_addresses_objection(response):
                style["styleRewriteReasons"].append(
                    "COMMERCIAL_OBJECTION_NOT_ADDRESSED"
                )
        initial_style_reasons = list(style["styleRewriteReasons"])
        original_style_defects = list(initial_style_reasons)
        rewrite_style_defects: list[str] = []
        rewrite_obligations_at_risk: list[str] = []
        fallback_preserved_original = False
        style_rewrite_attempted = False
        style_rewrite_outcome = (
            "SKIPPED_CONTINUITY_REWRITE_ALREADY_APPLIED"
            if initial_style_reasons and rewrite_attempted else "NOT_REQUIRED"
        )
        if initial_style_reasons and not rewrite_attempted:
            style_rewrite_attempted = True
            original_response = response
            style_messages = list(messages)
            style_messages.append({"role": "assistant", "content": response})
            style_messages.append({
                "role": "system",
                "content": f"""
FINAL PHONE-TEXTING STYLE REWRITE
Rewrite the draft once as a natural private phone text. Return only the reply.
Triggers: {json.dumps(initial_style_reasons)}
- Required turn obligations: {json.dumps(style.get('unsatisfiedTurnObligations') or [])}
- Keep its actual meaning, direct answer, temporal truth, and safety boundaries.
- Usually use one fragment/sentence or two short sentences; no polished paraphrase,
  generic aphorism, filler, or mechanical engagement question.
- Compress low-stakes banter toward one compact beat. Select one salient customer
  thread instead of acknowledging every detail.
- Do not repeat a conspicuous phrase or opening from Ava's recent replies.
- A question is allowed only when it adds concrete value.
- If the customer asked Ava a direct question, answer it before considering any
  reciprocal question. Do not dodge it by interviewing the customer about an
  incidental noun or activity in their message.
- Low-stakes immediate self-disclosure is allowed, but invent no consequential biography.
{('- Preserve exactly one required callback to this selected memory: ' + json.dumps(continuity_guidance.get('strongestMemory'), ensure_ascii=False)) if expected else '- Memory is available context, not required response content. Do not force a callback.'}
""",
            })
            try:
                candidate = complete(style_messages).choices[0].message.content.strip()
            except Exception as error:
                self.logger.exception(
                    "[GPT PHONE STYLE REWRITE ERROR] exception_type=%s exception_message=%s",
                    type(error).__name__, str(error),
                )
                style_rewrite_outcome = "PROVIDER_ERROR_ORIGINAL_PRESERVED"
            else:
                candidate_used = self._response_uses_continuity(
                    candidate, continuity_guidance
                )
                candidate_style = self._style_analysis(
                    candidate, user_message, pressure=question_pressure,
                    ordinary=ordinary_phone_texting,
                    memory_callback=candidate_used,
                    new_relationship=new_relationship,
                    recent_responses=recent_responses,
                )
                if value_defense_active:
                    candidate_style["styleRewriteReasons"].extend(
                        "UNSAFE_NEGATIVE_CONTACT_" + reason
                        for reason in self._negative_contact_safety_reasons(candidate)
                    )
                    if not self._value_defense_addresses_objection(candidate):
                        candidate_style["styleRewriteReasons"].append(
                            "COMMERCIAL_OBJECTION_NOT_ADDRESSED"
                        )
                # A still-long rewrite or another optional engagement question
                # gets one bounded final compression pass. Direct customer
                # questions and protected semantics retain their obligations.
                retryable_candidate_defects = {
                    "EXCESSIVE_ORDINARY_LENGTH",
                    "REPEATED_QUESTION_PRESSURE",
                    "MANUFACTURED_ENGAGEMENT_QUESTION",
                }.intersection(candidate_style["styleRewriteReasons"])
                if (retryable_candidate_defects
                        and not ({"CUSTOMER_QUESTION_UNANSWERED", "EMOTIONAL_ALIGNMENT_MISMATCH"}
                                 & set(candidate_style["styleRewriteReasons"]))):
                    pressure_messages = list(style_messages)
                    pressure_messages.append({"role": "assistant", "content": candidate})
                    pressure_messages.append({"role": "system", "content": f"""
FINAL PHONE-TEXT COMPRESSION REPAIR
The prior rewrite still has these defects: {json.dumps(sorted(retryable_candidate_defects))}
Rewrite as one compact natural statement/reaction/contribution. Do not ask a
question unless the customer directly asked one and a reciprocal question has
concrete value.
Keep every genuinely required answer, emotional, safety, temporal, and commercial
obligation. Prefer the current message's salient topic. Return only the reply.
"""})
                    try:
                        pressure_candidate = complete(pressure_messages).choices[0].message.content.strip()
                    except Exception:
                        self.logger.exception("[GPT QUESTION PRESSURE REWRITE ERROR]")
                    else:
                        pressure_used = self._response_uses_continuity(
                            pressure_candidate, continuity_guidance,
                        )
                        pressure_style = self._style_analysis(
                            pressure_candidate, user_message,
                            pressure=question_pressure,
                            ordinary=ordinary_phone_texting,
                            memory_callback=pressure_used,
                            new_relationship=new_relationship,
                            recent_responses=recent_responses,
                        )
                        if (not retryable_candidate_defects.intersection(
                                pressure_style["styleRewriteReasons"])
                                and pressure_style.get("turnObligationsSatisfied")):
                            candidate, candidate_used, candidate_style = (
                                pressure_candidate, pressure_used, pressure_style,
                            )
                rewrite_style_defects = list(candidate_style["styleRewriteReasons"])
                rewrite_obligations_at_risk = list(
                    candidate_style.get("unsatisfiedTurnObligations") or ()
                )
                hard_obligations = {
                    "ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION",
                    "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE", "HONOR_COMMERCIAL_REQUEST",
                }
                hard_obligations_at_risk = hard_obligations.intersection(
                    rewrite_obligations_at_risk
                )
                materially_shorter = (
                    candidate_style.get("responseLengthWords", 0)
                    <= max(1, int(style.get("responseLengthWords", 0) * .8))
                    or candidate_style.get("responseLengthCharacters", 0)
                    <= max(1, int(style.get("responseLengthCharacters", 0) * .8))
                )
                blocking_rewrite_defects = {
                    "CUSTOMER_QUESTION_UNANSWERED",
                    "MANUFACTURED_ENGAGEMENT_QUESTION",
                    "REPEATED_QUESTION_PRESSURE",
                    "EMOTIONAL_ALIGNMENT_MISMATCH",
                    "TEMPORAL_MISGROUNDING",
                }.intersection(candidate_style["styleRewriteReasons"])
                if expected and used and not candidate_used:
                    style_rewrite_outcome = "REJECTED_MEMORY_CALLBACK_LOSS"
                    response = original_response
                elif any(
                    reason in {
                        "CUSTOMER_QUESTION_UNANSWERED",
                        "MANUFACTURED_ENGAGEMENT_QUESTION",
                        "TURN_OBLIGATIONS_UNSATISFIED",
                        "EMOTIONAL_ALIGNMENT_MISMATCH",
                    } or reason.startswith("UNSAFE_NEGATIVE_CONTACT_")
                    for reason in candidate_style["styleRewriteReasons"]
                ) or any(
                    reason in candidate_style["styleRewriteReasons"]
                    for reason in initial_style_reasons
                ):
                    if (not hard_obligations_at_risk and not blocking_rewrite_defects and (
                            len(candidate_style["styleRewriteReasons"])
                            < len(initial_style_reasons) or materially_shorter)):
                        response = candidate
                        used = candidate_used
                        style_rewrite_outcome = (
                            "PARTIAL_STYLE_IMPROVEMENT_ACCEPTED"
                            if len(candidate_style["styleRewriteReasons"])
                            < len(initial_style_reasons)
                            else "IMPROVED_NONCOMPLIANT_REWRITE_ACCEPTED"
                        )
                    elif (style.get("turnObligationsSatisfied")
                            and not candidate_style.get("turnObligationsSatisfied")):
                        response = original_response
                        style_rewrite_outcome = "REJECTED_OBLIGATION_LOSS_ORIGINAL_PRESERVED"
                    elif value_defense_active:
                        style_rewrite_outcome = "NONCOMPLIANT_REWRITE_SAFE_BACKOFF"
                        response = "haha fair — no pressure, we can leave it there"
                    else:
                        missing = set(candidate_style.get("unsatisfiedTurnObligations") or ())
                        required = set(candidate_style.get("turnObligations") or ())
                        if "ANSWER_DIRECT_PERSONAL_QUESTION" in missing:
                            if shared_interest.get("claimAuthorized"):
                                response = self._customer_disclosure_fallback(
                                    customer_disclosure, shared_interest,
                                )
                            else:
                                response = self._obligation_aware_first_contact_fallback(
                                    user_message=user_message,
                                    temporal=temporal_language,
                                ) if "WELCOME_NEW_RELATIONSHIP" in required else "doing pretty good so far"
                        elif "ACKNOWLEDGE_COMPLIMENT" in missing:
                            response = "aww thank you, that's sweet of you 😊"
                        elif "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in missing:
                            response = "ugh yeah, sounds like you earned the chance to relax 😅"
                        elif "ACKNOWLEDGE_FLIRTATION" in missing:
                            response = "well then, you're kinda sweet 😂"
                        elif "HONOR_RELEVANT_MEMORY_CALLBACK" in missing:
                            response = self._memory_callback_fallback(continuity_guidance)
                            used = self._response_uses_continuity(
                                response, continuity_guidance,
                            )
                        elif "ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in missing:
                            response = self._customer_disclosure_fallback(
                                customer_disclosure, shared_interest,
                            )
                        elif "RESPOND_TO_JOKE" in missing:
                            response = "lol okay, I like your energy 😂"
                        elif "WELCOME_NEW_RELATIONSHIP" in missing:
                            response = "hey, good to hear from you 😊"
                        elif (shared_interest.get("claimAuthorized")
                              and "EXCESSIVE_ORDINARY_LENGTH" in initial_style_reasons):
                            response = self._customer_disclosure_fallback(
                                customer_disclosure, shared_interest,
                            )
                        else:
                            response = original_response
                            fallback_preserved_original = True
                        style_rewrite_outcome = "NONCOMPLIANT_REWRITE_SAFE_OBLIGATION_FALLBACK"
                else:
                    response = candidate
                    used = candidate_used
                    style_rewrite_outcome = "SUCCEEDED"
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=used,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )

        proactive_rewrite_attempted = False
        proactive_satisfied = self._response_satisfies_proactive_tease(response)
        if proactive_tease and not proactive_satisfied:
            proactive_rewrite_attempted = True
            proactive_messages = list(messages)
            proactive_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": """
FINAL PROACTIVE-TEASE OBLIGATION REWRITE
Rewrite the draft once as a short, natural private phone text that creates
playful curiosity or tension. Do not mention price, purchase, paid content,
inventory, or claim the customer wants to buy. Return only the reply.
"""},
            ))
            try:
                candidate = complete(proactive_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT PROACTIVE TEASE REWRITE ERROR]")
            else:
                if self._response_satisfies_proactive_tease(candidate):
                    response = candidate
                    proactive_satisfied = True
            if not proactive_satisfied:
                response = "careful, you haven't seen trouble yet"
                proactive_satisfied = True
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=used,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )

        temporal_validation = self.temporal_context_service.evaluate_response(
            user_message, response, temporal_context,
        )
        combined_triggers = []
        if not temporal_validation["responseTemporalAlignmentSatisfied"]:
            combined_triggers.append("TEMPORAL_MISMATCH")
        if (style.get("newProspectWarmthExpected")
                and not style.get("newProspectWarmthSatisfied")
                and not (style.get("customerQuestionAnswered")
                         and style.get("meaningfulContribution"))):
            combined_triggers.append("NEW_PROSPECT_WARMTH_UNSATISFIED")
        temporal_rewrite_attempted = False
        combined_rewrite_attempted = False
        combined_rewrite_outcome = "NOT_REQUIRED"
        if combined_triggers:
            combined_rewrite_attempted = True
            temporal_rewrite_attempted = "TEMPORAL_MISMATCH" in combined_triggers
            compliance_messages = list(messages)
            compliance_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": f"""
FINAL TEMPORAL AND FIRST-CONTACT COMPLIANCE REWRITE
Rewrite the draft once as a short, natural private phone text.
Triggers: {json.dumps(combined_triggers)}
Canonical temporal classification:
{json.dumps(temporal_validation, ensure_ascii=False)}
- Do not adopt a customer-assumed Ava daypart that conflicts with canonical Ava time.
- Neutral temporal wording is valid; do not give a pedantic clock correction.
- When new-prospect warmth is expected, make receptiveness perceptible and match the
  customer's approach intensity without customer-service language or exaggeration.
- Preserve every direct answer and turn obligation. Do not add a manufactured question.
Return only the customer-facing reply.
"""},
            ))
            try:
                candidate = complete(compliance_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT TEMPORAL/WARMTH REWRITE ERROR]")
                candidate = ""
            candidate_style = self._style_analysis(
                candidate, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=used,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )
            candidate_temporal = self.temporal_context_service.evaluate_response(
                user_message, candidate, temporal_context,
            )
            candidate_compliant = bool(
                candidate
                and candidate_style.get("turnObligationsSatisfied")
                and candidate_temporal["responseTemporalAlignmentSatisfied"]
                and (not candidate_style.get("newProspectWarmthExpected")
                     or candidate_style.get("newProspectWarmthSatisfied")
                     or (candidate_style.get("customerQuestionAnswered")
                         and candidate_style.get("meaningfulContribution")))
            )
            if candidate_compliant:
                response = candidate
                combined_rewrite_outcome = "SUCCEEDED"
            else:
                response = (
                    "taking it easy this weekend sounds like a good call"
                    if temporal_validation.get("customerEventTemporalRelation")
                    == "FUTURE_OR_PLANNED"
                    else self._obligation_aware_first_contact_fallback(
                        user_message=user_message, temporal=temporal_validation,
                    )
                )
                combined_rewrite_outcome = "NONCOMPLIANT_REWRITE_SAFE_COMBINED_FALLBACK"
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=used,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )

        # This validation intentionally runs after every ordinary style,
        # compression, memory, proactive, and temporal rewrite. It evaluates the
        # exact candidate that would otherwise leave the generation boundary.
        foreground_topics = self._foreground_topics(user_message)
        primary_foreground_topic = next(
            (topic for topic in foreground_topics if topic != "DIRECT_QUESTION"),
            foreground_topics[0] if foreground_topics else None,
        )
        topic_covered, topic_evidence = self._topic_coverage(
            response, foreground_topics, recent_responses, user_message,
        )
        if ("DIRECT_QUESTION" in foreground_topics
                and style.get("customerQuestionAnswered")):
            topic_covered = True
            topic_evidence = ["DIRECT_QUESTION", *topic_evidence]
        recent_similarity = self._recent_response_similarity(response, recent_responses)
        normalized_response = " ".join(re.findall(r"[a-z0-9']+", response.lower()))
        repeated_response = any(
            normalized_response
            and normalized_response == " ".join(re.findall(r"[a-z0-9']+", str(prior).lower()))
            for prior in recent_responses[-6:]
        )
        response_topics = self._foreground_topics(response)
        stale_callback = bool(
            ordinary_phone_texting and foreground_topics and not topic_covered
            and not (expected and used)
            and any(topic not in foreground_topics and topic != "DIRECT_QUESTION"
                    for topic in response_topics)
        )
        stale_reason = (
            "EXACT_RECENT_RESPONSE" if repeated_response
            else "HIGH_RECENT_RESPONSE_SIMILARITY" if recent_similarity >= .82
            else "OLDER_TOPIC_DISPLACED_CURRENT_FOREGROUND_TOPIC" if stale_callback
            else None
        )
        final_validation_original = response
        final_validation_attempted = False
        final_validation_outcome = "NOT_REQUIRED"
        repetition_requires_repair = bool(
            (repeated_response or recent_similarity >= .82)
            and not (expected and used and topic_covered)
        )
        final_validation_triggered = bool(
            ordinary_phone_texting
            and (repetition_requires_repair or stale_callback)
            and not protected_commercial_semantics
        )
        if final_validation_triggered:
            final_validation_attempted = True
            final_messages = list(messages)
            final_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": f"""
FINAL CURRENT-TOPIC AND REPETITION REPAIR
Rewrite the candidate once as a concise natural private phone text.
Current foreground topics: {json.dumps(foreground_topics)}
Primary foreground topic: {json.dumps(primary_foreground_topic)}
Failure reason: {json.dumps(stale_reason or 'CURRENT_TOPIC_NOT_COVERED')}
- Respond to the current foregrounded subject instead of recycling an older topic.
- Do not repeat or closely paraphrase Ava's recent responses.
- Older conversation entities are optional and must not displace the current topic.
- Preserve direct answers, emotional support, safety, temporal truth, and all
  commercial semantics. Do not fabricate personal facts.
- A canonical public-safe shared interest may be used when already authorized.
Return only the reply.
"""},
            ))
            try:
                final_candidate = complete(final_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT FINAL TOPIC VALIDATION REWRITE ERROR]")
                final_candidate = ""
            final_style = self._style_analysis(
                final_candidate, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=False,
                new_relationship=new_relationship, recent_responses=recent_responses,
            ) if final_candidate else {}
            final_temporal = self.temporal_context_service.evaluate_response(
                user_message, final_candidate, temporal_context,
            ) if final_candidate else {"responseTemporalAlignmentSatisfied": False}
            repaired_coverage, _ = self._topic_coverage(
                final_candidate, foreground_topics, recent_responses, user_message,
            )
            repaired_similarity = self._recent_response_similarity(
                final_candidate, recent_responses,
            )
            protected_obligations_lost = bool(set(
                final_style.get("unsatisfiedTurnObligations") or ()
            ).intersection({
                "ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION",
                "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE", "HONOR_COMMERCIAL_REQUEST",
            }))
            if (final_candidate and repaired_coverage and repaired_similarity < .82
                    and not protected_obligations_lost
                    and final_temporal.get("responseTemporalAlignmentSatisfied")):
                response = final_candidate
                final_validation_outcome = "SUCCEEDED"
            elif "DIRECT_QUESTION" in foreground_topics:
                # Existing direct-answer semantics are safer than a generic fallback.
                final_validation_outcome = "REPAIR_REJECTED_PROTECTED_ORIGINAL_PRESERVED"
            else:
                response = self._topic_safe_fallback(primary_foreground_topic)
                final_validation_outcome = "SAFE_CURRENT_TOPIC_FALLBACK"
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=False,
                new_relationship=new_relationship, recent_responses=recent_responses,
            )
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )
            topic_covered, topic_evidence = self._topic_coverage(
                response, foreground_topics, recent_responses, user_message,
            )
            if ("DIRECT_QUESTION" in foreground_topics
                    and style.get("customerQuestionAnswered")):
                topic_covered = True
                topic_evidence = ["DIRECT_QUESTION", *topic_evidence]
            recent_similarity = self._recent_response_similarity(response, recent_responses)
            normalized_response = " ".join(re.findall(r"[a-z0-9']+", response.lower()))
            repeated_response = any(
                normalized_response
                and normalized_response == " ".join(re.findall(r"[a-z0-9']+", str(prior).lower()))
                for prior in recent_responses[-6:]
            )
            response_topics = self._foreground_topics(response)
            stale_callback = bool(
                foreground_topics and not topic_covered
                and not (expected and used)
                and any(topic not in foreground_topics and topic != "DIRECT_QUESTION"
                        for topic in response_topics)
            )

        objection_response_satisfied = (
            not value_defense_active
            or self._value_defense_addresses_objection(response)
        )
        if value_defense_active and not objection_response_satisfied:
            response = "haha fair — no pressure, we can leave it there"
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=False,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )
            objection_response_satisfied = True
            style_rewrite_attempted = True
            style_rewrite_outcome = "SAFE_OBJECTION_ACKNOWLEDGEMENT_FALLBACK"

        commercial_action = str(
            (commerce_decision or {}).get("decision") or ""
        ).upper()
        attention_strategy_protected = commercial_action in {
            "PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "UPSELL",
            "CROSS_SELL", "NUDGE_ACTIVE_OFFER", "CONGRATULATE_PURCHASE",
            "BACK_OFF",
        }
        attention_initial_candidate = response
        attention_violations = self._attention_effort_violations(
            response, effort_mode=effort_mode, style=style,
            user_message=user_message,
        )
        attention_rewrite_attempted = False
        attention_rewrite_subreason = None
        attention_rewrite_outcome = (
            "STRATEGY_PROTECTED"
            if attention_strategy_protected and attention_violations
            else "NOT_REQUIRED"
        )
        if attention_violations and not attention_strategy_protected:
            attention_rewrite_attempted = True
            attention_messages = list(messages)
            attention_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": f"""
FINAL ATTENTION-EFFORT COMPLIANCE REWRITE
Effort mode: {effort_mode}
Violations: {json.dumps(attention_violations)}
Rewrite once as a concise, natural Ava private text. Preserve direct answers,
memory truth, safety, temporal truth, and the authoritative commercial strategy.
Do not ask for more sexual/explicit detail. Do not create a new open-ended free-
attention branch or append a manufactured question. Return only the reply.
"""},
            ))
            try:
                attention_candidate = complete(attention_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT ATTENTION COMPLIANCE REWRITE ERROR]")
                attention_candidate = ""
            candidate_style = self._style_analysis(
                attention_candidate, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=False,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            ) if attention_candidate else {}
            remaining = self._attention_effort_violations(
                attention_candidate, effort_mode=effort_mode,
                style=candidate_style, user_message=user_message,
            ) if attention_candidate else list(attention_violations)
            if "REDUCED_VOLUNTEERED_ATTENTION_LABOR" in remaining:
                attention_rewrite_subreason = (
                    self._volunteered_attention_labor_reason(
                        attention_candidate, user_message=user_message,
                    )
                )
            if attention_candidate and not remaining:
                response = attention_candidate
                style = candidate_style
                attention_rewrite_outcome = "SUCCEEDED"
            else:
                response = self._minimal_attention_fallback(response)
                style = self._style_analysis(
                    response, user_message, pressure=question_pressure,
                    ordinary=ordinary_phone_texting, memory_callback=False,
                    new_relationship=new_relationship,
                    recent_responses=recent_responses,
                )
                attention_rewrite_outcome = "SAFE_NATURAL_FALLBACK"
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )

        # Last-mile contract: no later rewrite may ship a low-value manufactured
        # question while dropping required foreground obligations. This runs
        # against the actual candidate leaving generation, not an earlier draft.
        final_contract_violation = self._violates_final_response_contract(style)
        if final_contract_violation:
            final_validation_attempted = True
            final_validation_original = response
            contract_messages = list(messages)
            contract_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": f"""
FINAL RESPONSE CONTRACT REPAIR
The candidate is a manufactured low-value question and failed required turn
obligations: {json.dumps(style.get('unsatisfiedTurnObligations') or [])}.
Rewrite once as a concise, natural private text that directly acknowledges the
customer's foreground meaning. Do not ask a question merely to prolong chat.
Preserve temporal truth, safety, memory truth, and authoritative commercial
semantics. Return only the customer-facing reply.
"""},
            ))
            try:
                contract_candidate = complete(contract_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT FINAL RESPONSE CONTRACT ERROR]")
                contract_candidate = ""
            contract_style = self._style_analysis(
                contract_candidate, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=used,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            ) if contract_candidate else {}
            contract_compliant = bool(
                contract_candidate
                and contract_style.get("turnObligationsSatisfied")
                and not (
                    contract_style.get("manufacturedQuestionRisk")
                    and contract_style.get("questionValue") == "LOW"
                    and not contract_style.get("meaningfulContribution")
                )
            )
            if contract_compliant:
                response = contract_candidate
                style = contract_style
                final_validation_outcome = "SUCCEEDED_FINAL_RESPONSE_CONTRACT"
            else:
                missing = set(style.get("unsatisfiedTurnObligations") or ())
                if proactive_tease:
                    response = "aww thank you, that's sweet of you... careful, you haven't seen trouble yet"
                elif {"ACKNOWLEDGE_COMPLIMENT", "ACKNOWLEDGE_FLIRTATION"} & missing:
                    response = "aww thank you, that's sweet of you"
                elif "ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in missing:
                    response = self._customer_disclosure_fallback(
                        customer_disclosure, shared_interest,
                    )
                elif missing.intersection({
                    "WELCOME_NEW_RELATIONSHIP", "RESPOND_TO_GREETING",
                    "ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION",
                }):
                    response = self._obligation_aware_first_contact_fallback(
                        user_message=user_message,
                        temporal=temporal_language,
                    )
                else:
                    response = "I hear you"
                style = self._style_analysis(
                    response, user_message, pressure=question_pressure,
                    ordinary=ordinary_phone_texting, memory_callback=False,
                    new_relationship=new_relationship,
                    recent_responses=recent_responses,
                )
                final_validation_outcome = "SAFE_FINAL_RESPONSE_CONTRACT_FALLBACK"
            final_validation_final = response
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )
            proactive_satisfied = (
                self._response_satisfies_proactive_tease(response)
                if proactive_tease else proactive_satisfied
            )

        # Validate the union of compatible required obligations after every
        # local rewrite/fallback.  A tease-only repair cannot erase required
        # continuity, and a continuity repair cannot erase Sales Brain's tease.
        combined_obligation_repair_attempted = False
        combined_obligation_repair_outcome = "NOT_REQUIRED"

        def final_composition(candidate: str) -> tuple[list[str], dict, dict]:
            memory_evidence = self._final_memory_callback_evidence(
                candidate, user_message, continuity_guidance,
            )
            candidate_style = self._style_analysis(
                candidate, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting,
                memory_callback=bool(memory_evidence["used"]),
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )
            violations = []
            if curiosity_truth_obligation:
                obligation = "DO_NOT_OVERSTATE_CUSTOMER_COMMERCIAL_STATE"
                obligations = list(candidate_style.get("turnObligations") or ())
                satisfied = list(
                    candidate_style.get("satisfiedTurnObligations") or ()
                )
                unsatisfied = list(
                    candidate_style.get("unsatisfiedTurnObligations") or ()
                )
                if obligation not in obligations:
                    obligations.append(obligation)
                overstatements = (
                    self._customer_commercial_state_overstatement_reasons(
                        candidate
                    )
                )
                candidate_style["customerCommercialStateTruthRequired"] = True
                candidate_style["customerCommercialStateOverstatementReasons"] = (
                    overstatements
                )
                if overstatements:
                    if obligation not in unsatisfied:
                        unsatisfied.append(obligation)
                    satisfied = [item for item in satisfied if item != obligation]
                    violations.append("CUSTOMER_COMMERCIAL_STATE_OVERSTATED")
                else:
                    if obligation not in satisfied:
                        satisfied.append(obligation)
                    unsatisfied = [item for item in unsatisfied if item != obligation]
                candidate_style["turnObligations"] = obligations
                candidate_style["satisfiedTurnObligations"] = satisfied
                candidate_style["unsatisfiedTurnObligations"] = unsatisfied
                candidate_style["turnObligationsSatisfied"] = not unsatisfied
            else:
                candidate_style["customerCommercialStateTruthRequired"] = False
                candidate_style["customerCommercialStateOverstatementReasons"] = []
            if expected and not memory_evidence["used"]:
                violations.append("REQUIRED_MEMORY_CONTINUITY_MISSING")
            if proactive_tease and not self._response_satisfies_proactive_tease(candidate):
                violations.append("AUTHORIZED_PROACTIVE_TEASE_MISSING")
            violations.extend(
                "FOREGROUND_OBLIGATION_" + item
                for item in candidate_style.get("unsatisfiedTurnObligations") or ()
                if item != "HONOR_RELEVANT_MEMORY_CALLBACK"
            )
            if self._violates_final_response_contract(candidate_style):
                violations.append("MANUFACTURED_QUESTION_CONTRACT")
            semantic_relevance = self._foreground_semantic_relevance(
                user_message, candidate,
            )
            if (semantic_relevance["required"]
                    and not semantic_relevance["satisfied"]):
                violations.append("FOREGROUND_SEMANTIC_RELEVANCE")
            temporal = self.temporal_context_service.evaluate_response(
                user_message, candidate, temporal_context,
            )
            if not temporal.get("responseTemporalAlignmentSatisfied"):
                violations.append("TEMPORAL_GROUNDING")
            attention = self._attention_effort_violations(
                candidate, effort_mode=effort_mode, style=candidate_style,
                user_message=user_message,
            )
            if attention and not attention_strategy_protected:
                violations.extend("ATTENTION_" + item for item in attention)
            return list(dict.fromkeys(violations)), memory_evidence, candidate_style

        final_composition_violations, _, _ = final_composition(response)
        if final_composition_violations:
            combined_obligation_repair_attempted = True
            repair_messages = list(messages)
            repair_messages.extend((
                {"role": "assistant", "content": response},
                {"role": "system", "content": f"""
FINAL COMBINED OBLIGATION REPAIR
The candidate failed these final-response requirements:
{json.dumps(final_composition_violations)}
Rewrite once as one concise, natural Ava private text.
Required foreground obligations: {json.dumps(style.get('turnObligations') or [])}
{('Include one natural callback grounded in: ' + json.dumps(continuity_guidance.get('strongestMemory'), ensure_ascii=False)) if expected else 'Memory is optional; do not force it.'}
Authoritative Sales Brain action: {('TEASE — preserve playful curiosity/tension without price, an offer, or purchase language.' if proactive_tease else 'Preserve the current non-tease strategy.')}
Preserve safety, canonical temporal truth, attention effort, and direct answers.
Do not concatenate checklist fragments or add a manufactured question.
Return only the customer-facing reply.
"""},
            ))
            try:
                combined_candidate = complete(repair_messages).choices[0].message.content.strip()
            except Exception:
                self.logger.exception("[GPT COMBINED OBLIGATION REPAIR ERROR]")
                combined_candidate = ""
            candidate_violations, _, candidate_style = final_composition(
                combined_candidate,
            ) if combined_candidate else (list(final_composition_violations), {}, {})
            if combined_candidate and not candidate_violations:
                response = combined_candidate
                style = candidate_style
                combined_obligation_repair_outcome = "SUCCEEDED"
            elif curiosity_truth_obligation:
                response = self._curiosity_response_fallback(recent_responses)
                fallback_violations, _, fallback_style = final_composition(response)
                style = fallback_style
                combined_obligation_repair_outcome = (
                    "SAFE_VARIED_CURIOSITY_FALLBACK"
                    if not fallback_violations else "FALLBACK_NONCOMPLIANT"
                )
            elif (
                "ACKNOWLEDGE_SEXUAL_ENERGY" in
                (style.get("turnObligations") or ())
                or "ACKNOWLEDGE_FLIRTATION" in
                (style.get("turnObligations") or ())
            ):
                # This existing bounded tease wording is safe, non-graphic, and
                # satisfies either foreground flirt contract. Never fall through
                # to a generic acknowledgement when that energy is authoritative.
                response = "careful, you haven't seen trouble yet"
                fallback_violations, _, fallback_style = final_composition(response)
                style = fallback_style
                combined_obligation_repair_outcome = (
                    "SAFE_SEXUAL_FLIRT_FALLBACK"
                    if not fallback_violations else "FALLBACK_NONCOMPLIANT"
                )
            elif expected or proactive_tease:
                response = self._required_composition_fallback(
                    continuity_guidance, proactive_tease=proactive_tease,
                ) if expected else "careful, you haven't seen trouble yet"
                fallback_violations, _, fallback_style = final_composition(response)
                style = fallback_style
                combined_obligation_repair_outcome = (
                    "SAFE_COMBINED_FALLBACK"
                    if not fallback_violations else "FALLBACK_NONCOMPLIANT"
                )
            else:
                # Hard final obligations cannot knowingly ship an invalid
                # candidate merely
                # because the single bounded provider repair failed.
                required_obligations = set(
                    style.get("turnObligations") or ()
                )
                if required_obligations.intersection({
                    "WELCOME_NEW_RELATIONSHIP", "RESPOND_TO_GREETING",
                    "ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION",
                }):
                    response = self._obligation_aware_first_contact_fallback(
                        user_message=user_message,
                        temporal=temporal_validation,
                    )
                else:
                    response = self._foreground_semantic_fallback(
                        user_message, effort_mode=effort_mode,
                    )
                fallback_violations, _, fallback_style = final_composition(response)
                style = fallback_style
                combined_obligation_repair_outcome = (
                    "CONTEXT_AWARE_FALLBACK"
                    if not fallback_violations else "FALLBACK_NONCOMPLIANT"
                )

        proactive_satisfied = (
            self._response_satisfies_proactive_tease(response)
            if proactive_tease else proactive_satisfied
        )
        temporal_validation = self.temporal_context_service.evaluate_response(
            user_message, response, temporal_context,
        )

        # Preserve the best fully compliant ordinary-chat candidate across all
        # provider/rewrite stages. A cosmetic fallback may not erase a required
        # answer, memory callback, temporal fact, or attention constraint. Hard
        # commercial composition remains outside this restoration boundary.
        best_safe_candidate_preserved = False
        best_safe_candidate_source = None
        final_violations, _, final_candidate_style = final_composition(response)
        if ordinary_phone_texting and not protected_commercial_semantics:
            eligible = []
            for ordinal, candidate_text in enumerate(generation_candidates):
                violations, _, candidate_style = final_composition(candidate_text)
                hard_style = {
                    "EMOTIONAL_ALIGNMENT_MISMATCH", "TEMPORAL_MISGROUNDING",
                }.intersection(candidate_style.get("styleRewriteReasons") or ())
                negative_contact = self._negative_contact_safety_reasons(candidate_text)
                if not violations and not hard_style and not negative_contact:
                    eligible.append((
                        -len(candidate_style.get("satisfiedTurnObligations") or ()),
                        len(candidate_style.get("styleRewriteReasons") or ()),
                        int(candidate_style.get("responseLengthWords") or 0),
                        ordinal,
                        candidate_text,
                        candidate_style,
                    ))
            if final_violations and eligible:
                selected = min(eligible)
                response = selected[4]
                style = selected[5]
                best_safe_candidate_preserved = True
                best_safe_candidate_source = f"PROVIDER_CANDIDATE_{selected[3] + 1}"
                final_validation_final = response
                final_validation_outcome = "BEST_SAFE_CANDIDATE_PRESERVED"
                combined_obligation_repair_outcome = (
                    "BEST_SAFE_CANDIDATE_PRESERVED"
                )
                temporal_validation = self.temporal_context_service.evaluate_response(
                    user_message, response, temporal_context,
                )
            elif not final_violations and response in generation_candidates:
                best_safe_candidate_preserved = True
                best_safe_candidate_source = (
                    f"PROVIDER_CANDIDATE_{generation_candidates.index(response) + 1}"
                )

        # Every rewrite/fallback has completed. Recompute memory use from the
        # exact customer-facing response so an earlier draft cannot certify the
        # final output. This pass records compliance; it does not force wording.
        final_memory = self._final_memory_callback_evidence(
            response, user_message, continuity_guidance,
        )
        used = bool(final_memory["used"])
        final_memory_style = self._style_analysis(
            response, user_message, pressure=question_pressure,
            ordinary=ordinary_phone_texting, memory_callback=used,
            new_relationship=new_relationship, recent_responses=recent_responses,
        )
        if curiosity_truth_obligation:
            _, _, final_memory_style = final_composition(response)
        for key in (
            "contributionType", "meaningfulContribution", "memoryCallbackUsed",
            "turnObligations", "turnObligationsSatisfied",
            "satisfiedTurnObligations", "unsatisfiedTurnObligations",
        ):
            style[key] = final_memory_style[key]
        style["customerCommercialStateTruthRequired"] = bool(
            final_memory_style.get("customerCommercialStateTruthRequired")
        )
        style["customerCommercialStateOverstatementReasons"] = list(
            final_memory_style.get(
                "customerCommercialStateOverstatementReasons"
            ) or ()
        )

        # The generic style analyzer recognizes explicit callback language in
        # the inbound turn, but continuity guidance is the authority on whether
        # a durable callback is mandatory.  An optional opportunity that Ava
        # naturally skips must not become a failed response obligation.
        if not expected and not used:
            obligation = "HONOR_RELEVANT_MEMORY_CALLBACK"
            style["turnObligations"] = [
                item for item in style.get("turnObligations") or ()
                if item != obligation
            ]
            style["satisfiedTurnObligations"] = [
                item for item in style.get("satisfiedTurnObligations") or ()
                if item != obligation
            ]
            style["unsatisfiedTurnObligations"] = [
                item for item in style.get("unsatisfiedTurnObligations") or ()
                if item != obligation
            ]
            style["turnObligationsSatisfied"] = not style[
                "unsatisfiedTurnObligations"
            ]

        # Required foreground relevance is a delivery gate, not telemetry.
        # This guard runs after best-candidate restoration so no later stage can
        # reintroduce an unrelated ordinary-chat response.
        semantic_gate = self._foreground_semantic_relevance(
            user_message, response,
        )
        if (ordinary_phone_texting and not protected_commercial_semantics
                and not expected and not proactive_tease
                and semantic_gate["required"] and not semantic_gate["satisfied"]):
            response = self._foreground_semantic_fallback(
                user_message, effort_mode=effort_mode,
            )
            style = self._style_analysis(
                response, user_message, pressure=question_pressure,
                ordinary=ordinary_phone_texting, memory_callback=False,
                new_relationship=new_relationship,
                recent_responses=recent_responses,
            )
            combined_obligation_repair_outcome = "CONTEXT_AWARE_FALLBACK"
            final_validation_final = response
            final_validation_outcome = "BINDING_SEMANTIC_FALLBACK"
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )
            final_memory = self._final_memory_callback_evidence(
                response, user_message, continuity_guidance,
            )
            used = bool(final_memory["used"])

        # Repetition is a final delivery constraint when a compliant alternate
        # already exists. Earlier obligation repairs may intentionally replace a
        # provider draft with bounded sexual/tease wording; this final pass keeps
        # those higher-priority obligations while preventing that fallback from
        # mechanically winning again inside the recent-response window.
        repetition_repair_attempted = False
        repetition_repair_outcome = "NOT_REQUIRED"
        final_response_repetition_satisfied = not bool(
            style.get("recentPhraseRepetitionRisk")
        )
        if style.get("recentPhraseRepetitionRisk"):
            repetition_repair_attempted = True
            contextual_fallbacks = (
                "mm, keep talking like that... you still haven't seen my dangerous side",
                "you really do bring out my trouble side... maybe I'll keep you guessing",
                "bold of you... I might tease you with my naughty side",
            )
            alternatives = [
                candidate for candidate in generation_candidates
                if candidate.strip() != response.strip()
            ] + list(contextual_fallbacks)
            for alternate in alternatives:
                alternate_violations, _, alternate_style = final_composition(
                    alternate
                )
                if (
                    not alternate_violations
                    and not alternate_style.get("recentPhraseRepetitionRisk")
                ):
                    response = alternate
                    style = alternate_style
                    temporal_validation = (
                        self.temporal_context_service.evaluate_response(
                            user_message, response, temporal_context,
                        )
                    )
                    final_response_repetition_satisfied = True
                    repetition_repair_outcome = "COMPLIANT_ALTERNATE_SELECTED"
                    break
            else:
                repetition_repair_outcome = "NO_COMPLIANT_ALTERNATE"

        # Binding customer-state truth gate. This runs after every ordinary
        # rewrite, best-candidate restoration, semantic fallback, and repetition
        # repair so no late stage can reintroduce a false buying-state claim.
        final_commercial_overstatements = (
            self._customer_commercial_state_overstatement_reasons(response)
            if curiosity_truth_obligation else []
        )
        if final_commercial_overstatements:
            response = self._curiosity_response_fallback(recent_responses)
            _, _, style = final_composition(response)
            temporal_validation = self.temporal_context_service.evaluate_response(
                user_message, response, temporal_context,
            )
            combined_obligation_repair_outcome = (
                "BINDING_CUSTOMER_COMMERCIAL_STATE_FALLBACK"
            )
            final_validation_final = response
            final_validation_outcome = "CUSTOMER_COMMERCIAL_STATE_TRUTH_ENFORCED"

        if used:
            final_memory_omission_reason = None
        elif expected:
            final_memory_omission_reason = (
                omission_reason or "FINAL_RESPONSE_OMITTED_REQUIRED_CALLBACK"
            )
        else:
            final_memory_omission_reason = (
                omission_reason or "OPTIONAL_MEMORY_NOT_USED"
            )

        final_attention_violations = self._attention_effort_violations(
            response, effort_mode=effort_mode, style=style,
            user_message=user_message,
        )
        final_semantic_relevance = self._foreground_semantic_relevance(
            user_message, response,
        )
        recent_similarity = self._recent_response_similarity(
            response, recent_responses,
        )
        normalize_final = lambda value: " ".join(
            re.findall(r"[a-z0-9']+", str(value or "").lower())
        )
        repeated_response = any(
            normalize_final(response) == normalize_final(prior)
            for prior in recent_responses[-4:]
            if normalize_final(prior)
        )
        style.update(temporal_validation)

        style.update({
            "styleRewriteAttempted": style_rewrite_attempted,
            "styleRewriteReason": (
                initial_style_reasons[0] if initial_style_reasons else None
            ),
            "styleRewriteTriggers": initial_style_reasons,
            "styleRewriteOutcome": style_rewrite_outcome,
            "originalStyleDefects": original_style_defects,
            "rewriteStyleDefects": rewrite_style_defects,
            "rewriteRequiredObligationsAtRisk": rewrite_obligations_at_risk,
            "fallbackPreservedOriginal": fallback_preserved_original,
            "unnecessaryMemoryCallbackRisk": repeated_optional_memory,
            "ephemeralSelfDisclosureOnly": style["selfDisclosureUsed"],
            "customerMemoryMutationAllowed": False,
            "sharedInterestDetected": bool(shared_interest.get("detected")),
            "sharedInterestDomain": shared_interest.get("domain"),
            "sharedInterestEvidence": list(shared_interest.get("evidence") or ()),
            "sharedInterestClaimAuthorized": bool(shared_interest.get("claimAuthorized")),
            "sharedInterestSource": shared_interest.get("source"),
            "sharedInterestUsedInResponse": bool(
                shared_interest.get("claimAuthorized")
                and re.search(
                    r"\b(?:speaking my language|outdoors girl|love being outside|"
                    r"my kind of (?:weekend|escape|reset)|i(?:'m| am) (?:into|big on) "
                    r"(?:hiking|camping|the outdoors)|i(?:'m| am) with you|me too|"
                    r"(?:hiking|camping|outdoors|being outside)(?:\s+\w+){0,3}\s+"
                    r"(?:is|are)(?:\s+\w+){0,2}\s+(?:everything|the best|my favorite))\b",
                    response, re.I,
                )
            ),
            "memoryCallbackExpected": expected,
            "memoryCallbackReason": list(
                continuity_guidance.get("relevanceReasons") or ()
            ),
            "selectedMemoryCallback": continuity_guidance.get("strongestMemory"),
            "selectedMemoryDomain": next(iter(
                (continuity_guidance.get("strongestMemory") or {}).get("domains") or ()
            ), None),
            "memoriesAvailable": bool(memory_diagnostics.get("available")),
            "memoriesRetrieved": list(memory_diagnostics.get("retrievedKeys") or ()),
            "memoriesRelevant": list(
                item.get("key") for item in memory_diagnostics.get("memoryCandidates") or ()
                if item.get("selected")
            ),
            "memoriesUsed": list(final_memory["memoriesUsed"]),
            "memoryCallbackNatural": True if used else None,
            "memoryCallbackRequired": expected,
            "memoryCallbackCompliance": (
                "SATISFIED" if expected and used
                else "REQUIRED_NOT_USED" if expected
                else "OPTIONAL_USED" if used
                else "OPTIONAL_NOT_USED"
            ),
            "memoryUsageClassification": final_memory["classification"],
            "memoryUsageMatchedAnchors": list(final_memory["matchedAnchors"]),
            "memoryCallbackSuppressionReason": final_memory_omission_reason,
            "proactiveTeaseExpected": proactive_tease,
            "proactiveTeaseSatisfied": proactive_satisfied if proactive_tease else None,
            "proactiveTeaseRewriteAttempted": proactive_rewrite_attempted,
            "temporalRewriteAttempted": temporal_rewrite_attempted,
            "temporalRewriteOutcome": combined_rewrite_outcome,
            "responseComplianceRewriteAttempted": combined_rewrite_attempted,
            "responseComplianceRewriteTriggers": combined_triggers,
            "foregroundTopics": foreground_topics,
            "primaryForegroundTopic": primary_foreground_topic,
            "currentTopicCoverageSatisfied": topic_covered,
            "currentTopicCoverageEvidence": topic_evidence,
            "foregroundSemanticIntent": final_semantic_relevance["intent"],
            "foregroundSemanticRelevanceRequired": final_semantic_relevance["required"],
            "foregroundSemanticRelevanceSatisfied": final_semantic_relevance["satisfied"],
            "staleCallbackDetected": stale_callback,
            "staleCallbackReason": stale_reason,
            "recentResponseSimilarity": recent_similarity,
            "repeatedResponseDetected": repeated_response,
            "repeatedResponseSource": (
                "EXACT_NORMALIZED_RECENT_LOW_INFORMATION_RESPONSE"
                if repeated_response and style.get("genericFillerRisk")
                else "EXACT_NORMALIZED_RECENT_RESPONSE"
                if repeated_response else None
            ),
            "finalValidationRewriteAttempted": final_validation_attempted,
            "finalValidationRewriteOutcome": final_validation_outcome,
            "finalValidationOriginalCandidate": final_validation_original,
            "finalValidationFinalCandidate": response,
            "bestSafeCandidatePreserved": best_safe_candidate_preserved,
            "bestSafeCandidateSource": best_safe_candidate_source,
            "combinedObligationRepairAttempted": combined_obligation_repair_attempted,
            "combinedObligationRepairOutcome": combined_obligation_repair_outcome,
            "combinedObligationInitialViolations": final_composition_violations,
            "repetitionRepairAttempted": repetition_repair_attempted,
            "repetitionRepairOutcome": repetition_repair_outcome,
            "finalResponseRepetitionSatisfied": (
                final_response_repetition_satisfied
            ),
            "trajectorySexualAlignmentRequired": bool(
                style.get("sexualResponseExpected")
            ),
            "trajectorySexualAlignmentSatisfied": (
                style.get("sexualResponseSatisfied")
                if style.get("sexualResponseExpected") else True
            ),
            "trajectorySexualAlignmentSource": (
                "GPTService.final_conversation_style.sexualResponseSatisfied"
            ),
            "objectionResponseRequired": value_defense_active,
            "objectionResponseSatisfied": objection_response_satisfied,
            "attentionPolicyEffortMode": str(effort_mode).upper(),
            "attentionComplianceRequired": str(effort_mode).upper() in {
                "MINIMAL", "COMPRESSED",
            },
            "attentionComplianceSatisfied": (
                not final_attention_violations or attention_strategy_protected
            ),
            "attentionComplianceStrategyProtected": attention_strategy_protected,
            "attentionComplianceViolations": final_attention_violations,
            "attentionComplianceSubreason": (
                self._volunteered_attention_labor_reason(
                    response, user_message=user_message,
                )
                if "REDUCED_VOLUNTEERED_ATTENTION_LABOR"
                in final_attention_violations else None
            ),
            "attentionComplianceInitialViolations": attention_violations,
            "attentionComplianceInitialSubreason": (
                self._volunteered_attention_labor_reason(
                    attention_initial_candidate,
                    user_message=user_message,
                )
                if "REDUCED_VOLUNTEERED_ATTENTION_LABOR"
                in attention_violations else None
            ),
            "attentionComplianceRewriteAttempted": attention_rewrite_attempted,
            "attentionComplianceRewriteOutcome": attention_rewrite_outcome,
            "attentionComplianceRewriteSubreason": attention_rewrite_subreason,
            "relationshipDiscovery": {
                **relationship_discovery,
                "questionActuallyAsked": bool(
                    style.get("relationshipDiscoveryQuestionAsked")
                ),
                "questionReason": style.get("questionReason"),
                "questionValue": style.get("questionValue"),
                "customerAnsweredDiscovery": relationship_discovery.get(
                    "customerAnsweredDiscovery"
                ),
                "memoryLearnedFromAnswer": bool(
                    relationship_discovery.get("memoryLearnedFromAnswer")
                ),
            },
        })
        if (style.get("sexualResponseExpected")
                and not style.get("sexualResponseSatisfied")):
            raise RuntimeError(
                "Final response failed the binding sexual-energy acknowledgement contract"
            )
        if (style.get("repeatedResponseDetected")
                and style.get("genericFillerRisk")):
            raise RuntimeError(
                "Final response repeated an exact low-information recent response"
            )
        memory_diagnostics["conversationStyle"] = style

        memory_diagnostics["generationCompliance"] = {
            "guidanceSupplied": bool(continuity_guidance),
            "priority": continuity_guidance.get("priority", "NONE"),
            "strongestMemoryKey": (
                (continuity_guidance.get("strongestMemory") or {}).get("key")
            ),
            "callbackExpected": expected,
            "callbackPreferred": bool(high_continuity),
            "callbackActuallyUsed": used,
            "memoriesAvailable": bool(memory_diagnostics.get("available")),
            "memoriesRetrieved": list(memory_diagnostics.get("retrievedKeys") or ()),
            "memoriesRelevant": list(
                item.get("key") for item in memory_diagnostics.get("memoryCandidates") or ()
                if item.get("selected")
            ),
            "memoriesUsed": list(final_memory["memoriesUsed"]),
            "callbackRequired": expected,
            "callbackCompliance": (
                "SATISFIED" if expected and used
                else "REQUIRED_NOT_USED" if expected
                else "OPTIONAL_USED" if used
                else "OPTIONAL_NOT_USED"
            ),
            "finalUsageClassification": final_memory["classification"],
            "rewriteAttempted": rewrite_attempted,
            "rewriteSucceeded": bool(rewrite_attempted and used),
            "rewriteOutcome": continuity_rewrite_outcome,
            "protectedCommercialSemantics": protected_commercial_semantics,
            "commercialAuthorityReason": commercial_authority_reason,
            "omissionReason": final_memory_omission_reason,
            "relationshipDiscovery": dict(style.get("relationshipDiscovery") or {}),
        }
        return response
