"""Bounded wording guidance using existing evidence; no generation or authority."""
from __future__ import annotations

import re


class ConversationMomentumStrategy:
    VERSION = "CONVERSATION_MOMENTUM_V1"
    # Recognition of inert whole responses, never a pool of output templates.
    INERT = re.compile(
        r"(?:well then[,. ]*)?message received|okay+y*[,. ]*(?:i felt that|loud and clear)|"
        r"(?:i appreciate that|that'?s nice|good to know|fair enough|gotcha|thank you|thanks)", re.I)
    STOP = set("the a an and or i you your my me it is are was were this that to of in on for with do did have has what how when where would can could really very just about".split())

    @classmethod
    def words(cls, text):
        return {w for w in re.findall(r"[a-z]+", str(text).lower()) if len(w) > 2 and w not in cls.STOP}

    @classmethod
    def plan(cls, customer, *, evidence=None, recent=()):
        e = dict(evidence or {})
        closure = bool(re.fullmatch(r"\s*(?:good\s?night|bye|goodbye|talk later|got to go)[.! ]*", customer, re.I))
        cool = e.get("effortMode") in {"MINIMAL", "COMPRESSED"} or e.get("backoff") is True
        affect = e.get("affect") or {}
        flirt = e.get("flirt") or {}
        classifier = e.get("classifier") or {}
        heat = str(e.get("heat") or "UNKNOWN").upper()
        energy = ("HOT" if heat in {"HOT", "STRONG"} or classifier.get("sexual_engagement") is True or flirt.get("sexual") is True
                  else "FLIRTY" if flirt.get("detected") is True or heat == "FLIRTY"
                  else "PLAYFUL" if heat == "PLAYFUL" or re.search(r"\b(?:bet|dare|challenge|comeback|joking|lucky)\b", customer, re.I)
                  else "WARM" if e.get("compliment") is True or affect.get("emotionalDisclosureDetected") is True
                  else "LOW")
        meaningful = bool(e.get("meaningful") or affect.get("emotionalDisclosureDetected") or e.get("disclosure"))
        intent = "END" if closure else "COOL" if cool else "BUILD" if energy in {"PLAYFUL", "FLIRTY", "HOT"} else "MAINTAIN"
        families = [cls.structure(s) for s in list(recent)[-3:]]
        repeated = next((f for f in families if f != "OTHER" and families.count(f) >= 2), None)
        return {"version": cls.VERSION, "customerEnergyUsed": energy, "heatEvidence": heat,
                "momentumIntent": intent, "meaningfulInvestment": meaningful,
                "varyRecentStrategy": repeated, "questionsOptional": True,
                "ordinaryWordPreference": 36 if meaningful else 28 if intent == "BUILD" else 24,
                "maximumSentences": 2}

    @staticmethod
    def structure(text):
        if re.search(r"\b(?:thanks?|thank you|blush|sweet of you)\b", text, re.I): return "COMPLIMENT_REACTION"
        if "?" in text: return "QUESTION"
        if re.search(r"\b(?:careful|trouble|dangerous)\b", text, re.I): return "CAUTION_TEASE"
        return "OTHER"

    @classmethod
    def contextual_question(cls, customer, candidate, *, pressure=None, recent=()):
        p = pressure or {}
        discovery = p.get("relationshipDiscovery") or {}
        if (candidate.count("?") != 1 or p.get("questionStreak", 0) >= 2
                or p.get("recentQuestionCount", 0) >= 3
                or (discovery.get("allowed") is False and discovery.get("suppressionReason") in
                    {"DOMAIN_ALREADY_KNOWN", "RECENTLY_ASKED", "QUESTION_PRESSURE", "NO_DISCOVERY_GAP"})):
            return False
        # Anchor the question clause itself, not a preceding acknowledgement.
        question = re.split(r"[.!]", candidate)[-1]
        if re.search(r"\b(?:what about you|how about you|anything else|tell me more|what are you up to|how was your day)\b", question, re.I):
            return False
        anchors = cls.words(customer) & cls.words(question)
        if not anchors or any("?" in prior and anchors & cls.words(prior) for prior in list(recent)[-3:]):
            return False
        substantive = bool(re.search(r"\b(?:my|our|i have|i had|i finished|i finally|i lost|i started|i love|i prefer)\b", customer, re.I))
        playful = bool(re.search(r"\b(?:bet|dare|challenge|comeback|lucky|win|beat)\b", customer, re.I))
        return substantive or playful

    @classmethod
    def assess(cls, customer, candidate, *, plan=None, evidence=None, recent=(),
               question_reason="NONE", manufactured=False, contribution="NONE",
               memory_callback=False, known_context=None):
        p = plan or cls.plan(customer, evidence=evidence, recent=recent)
        normalized = re.sub(r"[^a-z' ]", " ", candidate.lower())
        normalized = " ".join(normalized.split())
        inert = bool(cls.INERT.fullmatch(normalized))
        reasons = []
        if inert and (p["momentumIntent"] == "BUILD" or p["meaningfulInvestment"]) and p["momentumIntent"] not in {"COOL", "END"}:
            reasons.append("INERT_ENGAGED_RESPONSE")
        # Narrow, checkable recall claim. General semantic memory verification stays
        # with the existing memory authority; no similarity score certifies a fact.
        recall = re.search(r"\bremember (?:your|our) ([a-z][a-z-]*)", candidate, re.I)
        if recall and known_context is not None and recall.group(1).lower() not in cls.words(known_context):
            reasons.append("UNSUPPORTED_EXPLICIT_CALLBACK")
        category = ("NONE" if "?" not in candidate else "MANUFACTURED_BLOCKED" if manufactured
                    else "CLARIFICATION" if question_reason == "CLARIFICATION_REQUIRED" else "ORGANIC_CONTEXTUAL")
        return {**p, "contributionStrategy": "MEMORY_CALLBACK" if memory_callback else contribution,
                "questionCategory": category, "inertAcknowledgement": inert,
                "variationSuggested": bool(p["varyRecentStrategy"] and cls.structure(candidate) == p["varyRecentStrategy"]),
                "blockingReasons": reasons, "fallbackUsed": False,
                "styleIntervention": False, "candidateReplaced": False}

    @staticmethod
    def prompt(plan):
        return """
AVA CHARACTER AND CONVERSATION MOMENTUM
CONNECT -> PLAY -> BUILD is relationship guidance, never commercial permission.
ACKNOWLEDGE this turn, CONTRIBUTE something of Ava, ADVANCE or intentionally maintain,
cool or end. These are functions, not three mandatory clauses. MATCH ENERGY -> ADD
AVA -> CREATE MOMENTUM. Be warm, confident, playful, occasionally coy or mischievous.
Humor, a preference, a small grounded disclosure, playful disagreement, a challenge,
admitting a good comeback, or a relevant callback can add value. Vary emotional texture;
do not recite stock personality lines or mechanically rotate styles. Enjoy the exchange.
Use only supplied persona facts and real contextual memories; callbacks are optional.
Match existing energy with confidence and tension, never mechanical explicitness.
Respect thoughtful investment by meaning, not length. A tiny input needs no paragraph.
Usually use 1-2 natural sentences. Concise does not mean inert: preserve specificity,
tone and useful contribution when shortening. A question is optional; a grounded tease,
challenge, clarification or genuine curiosity is welcome. No generic engagement hook.
Vary a repeated recent conversational strategy. No forced escalation or mandatory question.
Safety, current commercial authority, reduced investment and closure remain stronger.
""" + "\nDeterministic wording guidance: " + str(plan)
