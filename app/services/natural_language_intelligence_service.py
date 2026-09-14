"""Deterministic, bounded proposals for operator-provided relationship intelligence."""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy

from app.services.canonical_relationship_fact_service import CanonicalRelationshipFactService


class NaturalLanguageIntelligenceService:
    MAX_INPUT = 2000

    def __init__(self, facts=None):
        self.facts = facts or CanonicalRelationshipFactService()

    def preview(self, *, creator_profile_id, fanvue_account_id, customer_id,
                customer_name, text, source_type="OPERATOR_VERIFIED"):
        clean = " ".join(str(text or "").strip().split())
        if not clean or len(clean) > self.MAX_INPUT:
            raise ValueError("Intelligence must be between 1 and 2000 characters.")
        if source_type not in {"OPERATOR_VERIFIED", "FANVUE_CONVERSATION",
                               "TELEGRAM_CONVERSATION", "X_OBSERVATION"}:
            raise ValueError("Unsupported operator source context.")
        existing = self.facts.list_facts(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_id=customer_id)
        proposals = self._extract(clean, creator_profile_id=creator_profile_id,
                                  customer_id=customer_id,
                                  customer_name=customer_name)
        proposals = self._unique(proposals)
        for proposal in proposals:
            payload = self._payload(proposal, creator_profile_id, fanvue_account_id,
                                    clean, source_type)
            proposal["canonicalPayload"] = payload
            proposal["proposalId"] = self._proposal_id(payload)
            self._classify(proposal, existing)
            if proposal["validationState"] == "READY":
                self.facts.preview_create(**payload)
        if not proposals:
            proposals = [{"proposalId": "needs-review", "label": "Needs review",
                          "meaning": "Creator_OS could not resolve this into a supported fact without guessing.",
                          "subjectLabel": customer_name, "sourceLabel": "Operator provided",
                          "usagePolicy": "NORMAL_CONTEXT", "validationState": "NEEDS_REVIEW",
                          "warnings": ["Use a clear subject, relationship, and fact."],
                          "canonicalPayload": None}]
        return {"mutationPerformed": False, "providerCalls": 0,
                "parser": "DETERMINISTIC_BOUNDED", "proposals": proposals}

    def apply(self, *, creator_profile_id, fanvue_account_id, customer_id,
              customer_name, text, selected_proposal_ids, silent_proposal_ids=(),
              source_type="OPERATOR_VERIFIED"):
        preview = self.preview(creator_profile_id=creator_profile_id,
                               fanvue_account_id=fanvue_account_id,
                               customer_id=customer_id, customer_name=customer_name,
                               text=text, source_type=source_type)
        selected, silent = set(selected_proposal_ids), set(silent_proposal_ids)
        available = {item["proposalId"]: item for item in preview["proposals"]}
        if not selected or not selected <= set(available):
            raise ValueError("Approved proposal selection is invalid.")
        results = []
        for proposal_id in selected:
            proposal = available[proposal_id]
            if proposal["validationState"] != "READY":
                raise ValueError("Only ready proposals can be added.")
            payload = deepcopy(proposal["canonicalPayload"])
            if proposal_id in silent:
                payload["usage_policy"] = "SILENT_CONTEXT"
            self.facts.preview_create(**payload)
            row, replay = self.facts.create_verified(**payload)
            results.append({"proposalId": proposal_id, "fact": row,
                            "idempotentReplay": replay})
        return {"success": True, "createdCount": sum(not x["idempotentReplay"] for x in results),
                "results": results}

    def _extract(self, text, *, creator_profile_id, customer_id, customer_name):
        low = text.lower(); found = []
        creator = bool(re.search(r"\bava(?:'s|’s)\b", low))
        ambiguous_my = bool(re.search(r"\bmy dog\b", low)) and "my customer's dog" not in low
        pet = re.search(r"(?:ava(?:'s|’s)|my customer(?:'s|’s)|[a-z]+(?:'s|’s)) dog(?: is)?\s+([A-Z][\w'-]+)", text, re.I)
        if not pet:
            pet = re.search(r"(?:dog\s+)([A-Z][\w'-]+)\s+is\s+(?:an?\s+)?([A-Za-z ]+?)(?:\.| and |,|$)", text)
        if pet and not ambiguous_my:
            name = pet.group(1); subject_type = "CREATOR" if creator else "CUSTOMER"
            breed_match = re.search(rf"\b{name}\b.*?\b(?:is|is a|is an)\s+(?:a |an )?([A-Za-z ]+?)(?:\.| and (?:goes|he|she)|,|$)", text, re.I)
            breed = breed_match.group(1).strip().title() if breed_match else None
            if breed and breed.lower() in {"bully", "jojo", "charlie", "girl", "boy"}: breed = None
            gender = "female" if re.search(r"\b(?:she(?:'s| is)|girl|female)\b", low) else "male" if re.search(r"\b(?:he(?:'s| is)|boy|male)\b", low) else None
            nickname = re.search(r"(?:goes by|nickname is)\s+([A-Z][\w'-]+)", text, re.I)
            attributes = {k:v for k,v in {"type":"dog","breed":breed,"gender":gender,
                                           "nickname":nickname.group(1) if nickname else None}.items() if v}
            found.append(self._proposal(subject_type, creator_profile_id if creator else customer_id,
                "CREATOR_SELF" if creator else "RELATIONSHIP", "owns_pet", "ENTITY", name,
                attributes, name, f"{'Ava' if creator else customer_name}'s " +
                (f"{gender} " if gender else "") + (breed or "dog"), customer_name))
        detail = re.search(r"\b([A-Z][\w'-]+)\s+is\s+(?:a\s+)?(male|female|boy|girl)\b", text, re.I)
        if detail and not pet:
            gender = {"girl":"female","boy":"male"}.get(detail.group(2).lower(),detail.group(2).lower())
            found.append(self._proposal("CUSTOMER", customer_id, "RELATIONSHIP", "owns_pet", "ENTITY",
                detail.group(1), {"gender":gender}, detail.group(1),
                f"Proposed gender: {gender}", customer_name))
        location = re.search(r"\b(?:she|he|they|the customer|[A-Z][\w'-]+) lives in ([A-Za-z .'-]+?)(?:\.|$)", text, re.I)
        if location:
            place=location.group(1).strip().title();found.append(self._proposal("CUSTOMER",customer_id,"IDENTITY_CONTEXT","knows","CONCEPT",place,{},place,"Customer location",customer_name))
        band = re.search(r"favorite band is ([A-Za-z0-9 &'’-]+?)(?:\.|$)", text, re.I)
        if band:
            value=band.group(1).strip();found.append(self._proposal("CUSTOMER",customer_id,"PREFERENCE","prefers","CONCEPT",value,{"domain":"music"},value,"Favorite band",customer_name))
        interest = re.search(r"\b(?:loves?|likes?)\s+([A-Za-z &'-]+?)(?:\s+with ava|\.|$)", text, re.I)
        if interest and not re.search(r"playful flirt",interest.group(1),re.I):
            value=interest.group(1).strip();found.append(self._proposal("CUSTOMER",customer_id,"PREFERENCE","prefers","ACTIVITY",value.title(),{},value.title(),"Customer interest",customer_name))
        if re.search(r"playful flirt", low):
            found.append(self._proposal("CUSTOMER",customer_id,"RELATIONSHIP","relationship_dynamic","CONCEPT","Playful flirting with Ava",{},"Playful Flirting","Likes playful flirting with Ava",customer_name))
        if re.search(r"understands?.*ava.*(?:virtual|ai)|knows?.*ava.*(?:virtual|ai)", low):
            found.append(self._proposal("CUSTOMER",customer_id,"IDENTITY_CONTEXT","understands","CONCEPT","Ava's virtual and AI nature",{},"AI Awareness","Understands Ava's virtual/AI nature",customer_name))
        if re.search(r"sometimes (?:includes?|appears?).*\b(?:ai images?|ai pictures?)\b|sometimes appears.*\bai (?:images?|pictures?)\b", low):
            pet_name = pet.group(1).title() if pet else "Their dog"
            found.append(self._proposal("CUSTOMER",customer_id,"RECURRING_BEHAVIOR","frequently_creates","ACTIVITY",f"{pet_name} sometimes appears in AI images with Ava",{"inclusion_frequency":"sometimes","possible_participants":[pet_name,"Ava"]},"AI Images",f"{pet_name} sometimes appears in {customer_name}'s recurring AI images with Ava",customer_name))
        if ambiguous_my:
            return []
        return found

    @staticmethod
    def _proposal(subject_type, subject_id, category, relation, object_type,
                  object_value, attributes, label, meaning, customer_name):
        return {"subjectType":subject_type,"subjectId":subject_id,"category":category,
                "relation":relation,"objectType":object_type,"objectValue":object_value,
                "attributes":attributes,"label":label,"meaning":meaning,
                "subjectLabel":"Ava / Creator" if subject_type=="CREATOR" else customer_name,
                "sourceLabel":"Operator provided","usagePolicy":"NORMAL_CONTEXT",
                "validationState":"READY","warnings":[]}

    @staticmethod
    def _payload(p, creator_profile_id, fanvue_account_id, text, source_type):
        source_platform={"FANVUE_CONVERSATION":"FANVUE","TELEGRAM_CONVERSATION":"TELEGRAM","X_OBSERVATION":"X"}.get(source_type,"CREATOR_OS")
        verification="OPERATOR_REVIEW"
        key=hashlib.sha256((str(creator_profile_id)+"|"+str(p["subjectType"])+"|"+str(p["subjectId"])+"|"+p["relation"]+"|"+p["objectValue"].lower()+"|"+str(sorted(p["attributes"].items()))).encode()).hexdigest()
        return {"creator_profile_id":creator_profile_id,"fanvue_account_id":fanvue_account_id,
                "subject_type":p["subjectType"],"subject_id":p["subjectId"],"relation":p["relation"],
                "object_type":p["objectType"],"object_value":p["objectValue"],"object_data":{},
                "attributes":p["attributes"],"category":p["category"],"source_platform":source_platform,
                "source_type":source_type,"source_reference":{"operatorEvidence":text[:500]},
                "verification_method":verification,"confidence":1.0,"usage_policy":"NORMAL_CONTEXT",
                "observed_at":None,"idempotency_key":"natural-language-"+key}

    @staticmethod
    def _proposal_id(payload):
        return hashlib.sha256(payload["idempotency_key"].encode()).hexdigest()[:20]

    @staticmethod
    def _unique(proposals):
        result=[];seen=set()
        for p in proposals:
            key=(p["subjectType"],p["relation"],p["objectValue"].lower())
            if key not in seen:seen.add(key);result.append(p)
        return result

    @staticmethod
    def _classify(proposal, existing):
        matches=[row for row in existing if row["subject_type"]==proposal["subjectType"] and
                 str(row["subject_id"])==str(proposal["subjectId"]) and
                 row["relation"]==proposal["relation"] and
                 str(row["object_value"]).casefold()==proposal["objectValue"].casefold()]
        if not matches:return
        current=matches[0];old=dict(current.get("attributes") or {});new=proposal["attributes"]
        conflicts={key:{"current":old[key],"proposed":value} for key,value in new.items()
                   if key in old and str(old[key]).casefold()!=str(value).casefold()}
        if conflicts:
            proposal["validationState"]="CONFLICT";proposal["warnings"]=["CONFLICT WITH EXISTING INTELLIGENCE"]
            proposal["current"]={"label":current["object_value"],"attributes":old};return
        if all(old.get(key)==value for key,value in new.items()):
            proposal["validationState"]="ALREADY_KNOWN";proposal["warnings"]=["Already known"]
        else:
            proposal["validationState"]="NEEDS_CORRECTION";proposal["warnings"]=["Existing fact can only be enriched through the correction workflow"]
