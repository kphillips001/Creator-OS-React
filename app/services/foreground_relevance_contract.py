"""Deterministic conversational acts and grounded professional disclosure coverage.

No provider calls. Category evidence describes what an acknowledgement addresses,
not whether a particular topic keyword was repeated.
"""
import re


class ForegroundRelevanceContract:
    VERSION = 'FOREGROUND_OBLIGATION_V2'
    WORK_CATEGORIES = {
        'PROFESSIONAL_ACTIVITY': r'\b(?:work(?:ing)?|job|career|profession(?:al)?|business|office|shift|occupation|camera operator|filming|captur(?:e|ing)|shoot(?:ing)?|manag(?:e|es|ing)|administration)\b',
        'RESPONSIBILITY': r'\b(?:responsibilit(?:y|ies)|clients?|customers?|owners?|team|staff|properties|property|condos?|condominiums?|portfolio)\b',
        'CAPACITY': r'\b(?:workload|busy|slammed|swamped|overload(?:ed)?|burnout|boundaries|limits|say(?:ing)? no|turn(?:ing)? down|tak(?:e|ing) on|too much|more work|manage(?:able)?)\b',
        'REST': r'\b(?:rest|sleep|early start|wind(?:ing)? down|recharg(?:e|ing)|break|time off)\b',
    }

    @staticmethod
    def normalize(value):
        return str(value or '').replace('\u2019', "'").strip()

    @classmethod
    def work_evidence(cls, text):
        return [name for name,pattern in cls.WORK_CATEGORIES.items() if re.search(pattern,cls.normalize(text),re.I)]

    @classmethod
    def work_disclosure(cls, text):
        # Responsibility/capacity alone is not sufficient to invent a work topic.
        value=cls.normalize(text)
        return bool(re.search(r'\b(?:work(?:ing)?|job|career|profession(?:al)?|business|office|shift|occupation|camera operator|administration)\b',value,re.I)
            or (re.search(r'\bmanag(?:e|es|ing)\b',value,re.I)
                and 'RESPONSIBILITY' in cls.work_evidence(value)))

    @classmethod
    def location_question(cls, message):
        return bool(re.search(r'\b(?:where (?:do you live|are you (?:from|based|located)|did you (?:grow up|move from))|what (?:city|country|town|state) (?:are you|do you)|are you (?:originally )?from|do you live in)\b',cls.normalize(message),re.I))

    @classmethod
    def location_answer(cls, candidate):
        return bool(re.search(r"\b(?:i(?:'m| am) (?:in|from|based)|i live|my (?:city|town|location)|keep (?:my |that )?(?:location|private)|rather not (?:say|share)|prefer not to (?:say|share))\b",cls.normalize(candidate),re.I))

    @classmethod
    def work_coverage(cls, foreground, candidate):
        source=set(cls.work_evidence(foreground));answer=set(cls.work_evidence(candidate))
        if not source:return False,[]
        # A work disclosure permits a grounded acknowledgement of the activity,
        # responsibility or capacity; rest answers need source rest/shift evidence.
        covered=bool(answer & {'PROFESSIONAL_ACTIVITY','RESPONSIBILITY','CAPACITY'})
        if not covered and 'REST' in answer:
            covered=bool('REST' in source or re.search(r'\b(?:shift|busy|tired|exhausted)\b',foreground,re.I))
        return covered,sorted(answer) if covered else []

    @classmethod
    def inventory_question(cls, message):
        value=cls.normalize(message)
        return bool(re.search(
            r'\b(?:do you have|have you got|you got|got any|is there|are there)\b.{0,40}'
            r'\b(?:anything|something|more|new|else|stuff|content|photos?|videos?|sets?)\b|'
            r'\bwhat\s+(?:content|photos?|videos?|sets?|else)\s+(?:do you have|is available)\b|'
            r'\bwhat (?:do you have|is available)\b|'
            r'\bwhat (?:can i|is there to) (?:buy|unlock|purchase)\b|'
            r'\b(?:anything|something)\s+i\s+haven\x27t\s+(?:seen|bought|unlocked)\b|'
            r'^\s*(?:have|got)\s+(?:anything|something)\s+(?:new|else|more)\b',value,re.I))

    @classmethod
    def pricing_question(cls, message):
        value=cls.normalize(message)
        if re.search(r'\b(?:price|pricing|costs?|dollars?|cheaper)\b',value,re.I):return True
        return bool(re.search(
            r'\bhow much\s+(?:is|are|does|do|would|will)\s+(?:it|that|this|the|a|your)\b|'
            r'\bhow much\s+(?:for|to (?:buy|unlock|pay))\b|'
            r'\b(?:how much|what)\s+do you charge\b|'
            r'^\s*how much\s*[?!.]*\s*$',value,re.I))
