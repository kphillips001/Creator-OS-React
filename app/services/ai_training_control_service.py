"""Classification and runtime projection for operator-authored AI training."""
import re

from app.models.ai_training_control import AiTrainingInstructionStatus
from app.repositories.ai_training_control_repository import AiTrainingControlRepository


class AiTrainingControlError(ValueError):
    pass


class AiTrainingControlService:
    TREATMENT_DEFAULTS = {
        "sales_pressure": "NORMAL", "free_engagement": "NORMAL",
        "response_length": "NORMAL",
    }
    TREATMENT_ENUMS = {
        "sales_pressure": {"REDUCED", "NORMAL", "INCREASED"},
        "free_engagement": {"MORE_LIMITED", "NORMAL", "MORE_FLEXIBLE"},
        "response_length": {"SHORTER", "NORMAL", "LONGER"},
    }
    CUSTOMER_RESERVED_SAFETY_TERMS = (
        "underage", "minor", "ignore safety", "bypass safety", "ignore the underage",
    )
    CUSTOMER_RESERVED_BUSINESS_TERMS = (
        "price", "$", "discount", "sell", "offer", "once per week", "ownership",
        "owned content", "purchased content", "unlock", "payment", "settlement",
        "inventory", "availability", "available", "fulfillment", "purchase intent",
        "sales session", "free paid content", "paid content for free", "give free", "provider",
    )
    ENGAGEMENT_TERMS = ("free teaser", "free teasers", "engagement teaser", "engagement teasers")
    READINESS_TERMS = (
        "adaptive sales readiness", "warm-up benchmark", "warmup benchmark",
        "build rapport before proactively selling", "customer appears ready",
        "customer is ready", "10-15 customer messages", "10â€“15 customer messages",
    )
    UNDERAGE_TERMS = ("underage", "under age", "confirmed minor", "determined to be a minor")
    STOP_CONTACT_TERMS = ("stop chatting", "don't chat", "do not chat", "stop all automated communication", "stop communication", "block")
    HARD_STOP_TERMS = (
        "underage", "under age", "minor", "stop all communication",
        "do not contact", "never contact", "hard stop",
    )
    COMMERCE_TERMS = (
        "purchase intent", "ownership", "owned content", "fanvue media link",
        "media link", "session progression", "sales session", "asset library",
        "send this url", "http://", "https://", "sell for", "price", "$",
        "commerce mode", "back_off", "back off", "customer sales brain",
    )
    SALES_TERMS = (
        "proactively offer", "do not offer", "don't offer", "never offer",
        "always offer", "bundle offer", "stop selling", "always sell",
    )
    AUTHORITY_ESCAPE_TERMS = (
        "ignore previous instructions", "ignore system instructions",
        "override system", "override backend", "bypass safety", "ignore safety",
        "reveal system prompt", "act as the system",
    )

    def __init__(self, repository=None):
        self.repository = repository or AiTrainingControlRepository()

    def classify(self, text: str):
        original = self._text(text)
        lowered = original.lower()
        if any(term in lowered for term in self.READINESS_TERMS):
            from app.models.adaptive_sales_readiness import SALES_READINESS_POLICY_KEY, AdaptiveSalesReadinessConfig
            return {
                "originalOperatorText": original,
                "normalizedInstruction": "Adaptive Sales Readiness",
                "instructionType": "SALES_RULE", "policyKey": SALES_READINESS_POLICY_KEY,
                "enforcementMode": "BACKEND", "classification": "SALES_RULE",
                "classificationReason": (
                    "Structured Customer Sales Brain policy. The 10-15 inbound-message region is advisory; "
                    "direct purchase intent may accelerate, while all higher-authority safety and commerce controls remain enforced."
                ),
                "runtimeEligible": True,
                "policyConfiguration": AdaptiveSalesReadinessConfig().to_dict(),
            }
        if any(term in lowered for term in self.ENGAGEMENT_TERMS):
            from app.models.engagement_teaser_policy import (
                ENGAGEMENT_POLICY_KEY, EngagementTeaserPolicyConfig,
            )
            return {
                "originalOperatorText": original,
                "normalizedInstruction": "Intelligent Free Engagement Teasers",
                "instructionType": "ENGAGEMENT_RULE",
                "policyKey": ENGAGEMENT_POLICY_KEY,
                "enforcementMode": "BACKEND",
                "classification": "ENGAGEMENT_RULE",
                "classificationReason": (
                    "Structured backend policy for occasional WARM_UP, RE_ENGAGE, and "
                    "RELATIONSHIP Free Engagement Teasers. Safety, funnel suppression, "
                    "frequency, eligibility, and permanent no-repeat remain backend enforced."
                ),
                "runtimeEligible": True,
                "policyConfiguration": EngagementTeaserPolicyConfig().to_dict(),
            }
        if (any(term in lowered for term in self.UNDERAGE_TERMS)
                and any(term in lowered for term in self.STOP_CONTACT_TERMS)):
            return {
                "originalOperatorText": original,
                "normalizedInstruction": "Underage Customer Hard Stop",
                "instructionType": "SAFETY_HARD_STOP",
                "policyKey": "UNDERAGE_CUSTOMER",
                "enforcementMode": "BACKEND",
                "classification": "SAFETY_HARD_STOP",
                "classificationReason": (
                    "Backend-enforced global policy. Only customers deliberately marked "
                    "UNDERAGE_BLOCKED are prevented from autonomous interaction; other "
                    "customers are unaffected. This policy does not determine or mark age."
                ),
                "runtimeEligible": True,
            }
        if any(term in lowered for term in self.HARD_STOP_TERMS):
            return {
                "originalOperatorText": original,
                "normalizedInstruction": original,
                "instructionType": "HARD_STOP",
                "classification": "REQUIRES_IMPLEMENTATION",
                "classificationReason": (
                    "This instruction requires a customer/backend safety control and "
                    "cannot be enforced as prompt guidance."
                ),
                "runtimeEligible": False,
                "policyKey": None, "enforcementMode": "NONE",
            }
        if any(term in lowered for term in self.AUTHORITY_ESCAPE_TERMS):
            return {
                "originalOperatorText": original,
                "normalizedInstruction": original,
                "instructionType": "SAFETY_RULE",
                "classification": "REQUIRES_IMPLEMENTATION",
                "classificationReason": (
                    "This instruction attempts to override system or backend authority "
                    "and cannot be activated as prompt guidance."
                ),
                "runtimeEligible": False,
                "policyKey": None, "enforcementMode": "NONE",
            }
        if any(term in lowered for term in self.COMMERCE_TERMS):
            return {
                "originalOperatorText": original,
                "normalizedInstruction": original,
                "instructionType": "SAFETY_RULE",
                "classification": "REQUIRES_IMPLEMENTATION",
                "classificationReason": (
                    "This instruction concerns authoritative commerce, ownership, "
                    "delivery, or session state and requires backend enforcement."
                ),
                "runtimeEligible": False,
                "policyKey": None, "enforcementMode": "NONE",
            }
        if any(term in lowered for term in self.SALES_TERMS):
            return {
                "originalOperatorText": original,
                "normalizedInstruction": original,
                "instructionType": "SALES_RULE",
                "classification": "REQUIRES_IMPLEMENTATION",
                "classificationReason": (
                    "This instruction changes deterministic selling policy and must "
                    "be implemented in CustomerSalesBrain."
                ),
                "runtimeEligible": False,
                "policyKey": None, "enforcementMode": "NONE",
            }
        return {
            "originalOperatorText": original,
            "normalizedInstruction": original,
            "instructionType": "CONVERSATION_RULE",
            "classification": "CONVERSATION_RULE",
            "classificationReason": "Eligible as global conversational guidance.",
            "runtimeEligible": True,
            "policyKey": None, "enforcementMode": "PROMPT",
        }

    def classify_customer(self, text: str):
        original = self._text(text)
        lowered = original.lower()
        conflict = self._customer_protected_authority_conflict(lowered)
        if conflict:
            authority, reason = conflict
            return {"originalOperatorText": original, "normalizedInstruction": original,
                    "instructionType": "CONVERSATION_RULE", "classification": "REJECTED_PROTECTED_AUTHORITY",
                    "classificationReason": reason, "protectedAuthority": authority,
                    "runtimeEligible": False, "policyKey": None, "enforcementMode": "NONE",
                    "scope": "CUSTOMER", "businessAuthorityChanged": authority != "SAFETY",
                    "safetyConflict": authority == "SAFETY"}
        if any(term in lowered for term in self.CUSTOMER_RESERVED_SAFETY_TERMS):
            return {"originalOperatorText": original, "normalizedInstruction": original,
                    "instructionType": "CONVERSATION_RULE", "classification": "UNSAFE_CUSTOMER_POLICY",
                    "classificationReason": "This conflicts with a protected safety policy and cannot be activated.",
                    "runtimeEligible": False, "policyKey": None, "enforcementMode": "NONE",
                    "scope": "CUSTOMER", "businessAuthorityChanged": False, "safetyConflict": True}
        if any(term in lowered for term in self.CUSTOMER_RESERVED_BUSINESS_TERMS):
            return {"originalOperatorText": original, "normalizedInstruction": original,
                    "instructionType": "CONVERSATION_RULE", "classification": "REQUIRES_IMPLEMENTATION",
                    "classificationReason": "This changes business or sales policy and cannot be implemented as conversational guidance.",
                    "runtimeEligible": False, "policyKey": None, "enforcementMode": "NONE",
                    "scope": "CUSTOMER", "businessAuthorityChanged": True, "safetyConflict": False}
        return {"originalOperatorText": original, "normalizedInstruction": original,
                "instructionType": "CONVERSATION_RULE", "classification": "CUSTOMER_PROMPT_GUIDANCE",
                "classificationReason": "Safe customer-specific conversational guidance. Business and safety authority are unchanged.",
                "runtimeEligible": True, "policyKey": None, "enforcementMode": "PROMPT",
                "scope": "CUSTOMER", "businessAuthorityChanged": False, "safetyConflict": False}

    @staticmethod
    def _customer_protected_authority_conflict(lowered: str):
        """Reject explicit attempts to contradict canonical safety or business truth."""
        override = bool(re.search(
            r"\b(?:ignore|bypass|override|disregard|pretend|lie|waive|alter)\b|"
            r"\bregardless of\b|\beven (?:if|when)\b", lowered))
        if re.search(r"\b(?:give|send|unlock|waive)\b.{0,35}\b(?:free\s+paid content|paid content)\b.{0,20}\bfree\b|"
                     r"\b(?:free\s+paid content|paid content\b.{0,20}\bfor free)\b", lowered):
            return "FREE_PAID_CONTENT", "Paid content cannot be given away by customer prompt guidance."
        if override and re.search(r"\b(?:ownership|own|owns|owned|already owns|purchased content)\b", lowered):
            return "OWNERSHIP", "Ownership truth cannot be ignored or contradicted by customer prompt guidance."
        if (override and re.search(r"\b(?:inventory|availability|available|unavailable|exists?)\b", lowered)) or re.search(
                r"\b(?:tell|say|pretend)\b.{0,60}\bavailable\b.{0,30}\b(?:isn['’]?t|aren['’]?t|not|doesn['’]?t)\b", lowered):
            return "INVENTORY_AVAILABILITY", "Inventory and availability truth cannot be fabricated."
        if override and re.search(r"\b(?:payment|paid|settlement|transaction|purchase state)\b", lowered):
            return "PAYMENT_SETTLEMENT", "Payment and settlement truth cannot be ignored or contradicted."
        if override and re.search(r"\bpurchase\s*intent\b", lowered):
            return "PURCHASE_INTENT", "PurchaseIntent lifecycle state cannot be ignored or overridden."
        if override and re.search(r"\bsales?\s*session\b", lowered):
            return "SALES_SESSION", "Sales Session lifecycle state cannot be ignored or overridden."
        if override and re.search(r"\b(?:fulfillment|delivery|provider truth)\b", lowered):
            return "FULFILLMENT_PROVIDER", "Fulfillment and provider truth cannot be ignored or contradicted."
        return None

    def list_customer(self, *, creator_profile_id: int, fanvue_account_id: int,
                      customer_fanvue_user_id: int):
        return self.repository.list_customer(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id)

    def preview_customer_treatment(self, configuration: dict):
        values = self._treatment_configuration(configuration)
        return {"configuration": values, "usingAvaDefaults": self._treatment_is_default(values),
                "treatmentType": "CUSTOMER_TREATMENT_POLICY",
                "runtimeEffect": "BOUNDED_PHASE_2B",
                "protectedAuthorities": ["SAFETY", "PRICING", "OWNERSHIP", "INVENTORY",
                                         "SETTLEMENT", "FULFILLMENT", "SALES_BRAIN_AUTHORIZATION"]}

    def get_customer_treatment(self, *, creator_profile_id: int, fanvue_account_id: int,
                               customer_fanvue_user_id: int):
        item = self.repository.customer_treatment(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            customer_fanvue_user_id=customer_fanvue_user_id)
        effective = dict(self.TREATMENT_DEFAULTS)
        if item and item.status is AiTrainingInstructionStatus.ENABLED:
            effective = self._treatment_configuration(item.policy_configuration or {})
        return {"item": item, "configuration": effective,
                "usingAvaDefaults": not item or item.status is not AiTrainingInstructionStatus.ENABLED,
                "runtimeEffect": "BOUNDED_PHASE_2B"}

    def analyze_customer_training(self, text: str):
        """Deterministically separate supported treatment from safe prompt guidance."""
        original = self._text(text)
        lowered = original.lower()
        protected = self.classify_customer(original)
        if not protected["runtimeEligible"]:
            reason = protected["classificationReason"]
            if any(term in lowered for term in ("available", "availability", "inventory", "we don't have")):
                reason = ("Availability is current inventory/business truth and cannot be saved as "
                          "timeless customer guidance.")
            return {"operatorText": original, "supported": False, "classification": protected["classification"],
                    "explanation": reason, "conversationGuidance": [],
                    "treatment": dict(self.TREATMENT_DEFAULTS), "protectedAuthority": protected.get("protectedAuthority"),
                    "protectedAuthorities": self._protected_authorities()}

        treatment = dict(self.TREATMENT_DEFAULTS)
        if re.search(r"\b(?:less|reduce[sd]?|lower)\b.{0,24}\b(?:sales?|sell(?:ing)?|push|pressure)\b|\bdon['\u2019]?t push\b", lowered):
            treatment["sales_pressure"] = "REDUCED"
        elif re.search(r"\b(?:more|increase[sd]?|stronger)\b.{0,24}\b(?:sales?|sell(?:ing)?|commercial|pressure)\b", lowered):
            treatment["sales_pressure"] = "INCREASED"
        if re.search(r"\b(?:less|limit(?:ed)?|reduce[sd]?)\b.{0,24}\b(?:free|chat|conversation|engagement)\b", lowered):
            treatment["free_engagement"] = "MORE_LIMITED"
        elif re.search(r"\b(?:more|flexible|extra)\b.{0,24}\b(?:free|chat|conversation|engagement|relationship)\b", lowered):
            treatment["free_engagement"] = "MORE_FLEXIBLE"
        if re.search(r"\b(?:short(?:er)?|brief|concise)\b.{0,20}\b(?:repl(?:y|ies)|response|message)?", lowered):
            treatment["response_length"] = "SHORTER"
        elif re.search(r"\b(?:long(?:er)?|detailed|more detail)\b.{0,20}\b(?:repl(?:y|ies)|response|message)?", lowered):
            treatment["response_length"] = "LONGER"

        guidance = []
        warmth = re.search(r"\b(?:be|sound|act)\s+(warmer|gentler|friendlier|more playful|more affectionate)\b", lowered)
        if warmth:
            quality = warmth.group(1)
            guidance.append(f"Be {quality} with this customer.")
        dimensions_found = not self._treatment_is_default(treatment)
        if not guidance and not dimensions_found:
            guidance_result = self.classify_customer(original)
            if guidance_result["runtimeEligible"]:
                guidance.append(guidance_result["normalizedInstruction"])
        return {"operatorText": original, "supported": bool(guidance or dimensions_found),
                "classification": "CUSTOMER_TRAINING_PLAN", "explanation":
                "Review the bounded interpretation before applying it.",
                "conversationGuidance": guidance, "treatment": treatment,
                "protectedAuthorities": self._protected_authorities()}

    def apply_customer_training_plan(self, *, creator_profile_id: int, fanvue_account_id: int,
                                     customer_fanvue_user_id: int, operator_text: str,
                                     conversation_guidance: list[str], configuration: dict):
        analysis = self.analyze_customer_training(operator_text)
        if not analysis["supported"]:
            raise AiTrainingControlError(analysis["explanation"])
        values = self._treatment_configuration(configuration)
        allowed_guidance = []
        for guidance in conversation_guidance:
            result = self.classify_customer(guidance)
            if not result["runtimeEligible"]:
                raise AiTrainingControlError(result["classificationReason"])
            if self._guidance_overlaps_treatment(guidance, values):
                continue
            allowed_guidance.append(result["normalizedInstruction"])
        created = [self.create_customer(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
            operator_text=value, activate=True) for value in allowed_guidance]
        treatment = self.apply_customer_treatment(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
            configuration=values, operator_text=operator_text)
        return {"guidance": created, "treatment": treatment,
                "configuration": values, "usingAvaDefaults": self._treatment_is_default(values)}

    def apply_customer_treatment(self, *, creator_profile_id: int, fanvue_account_id: int,
                                 customer_fanvue_user_id: int, configuration: dict,
                                 operator_text: str | None = None):
        values = self._treatment_configuration(configuration)
        current = self.repository.customer_treatment(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            customer_fanvue_user_id=customer_fanvue_user_id)
        if current is None and self._treatment_is_default(values):
            return None
        summary = self._treatment_summary(values)
        return self.repository.apply_customer_treatment(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            customer_fanvue_user_id=customer_fanvue_user_id, configuration=values,
            normalized=summary, enabled=not self._treatment_is_default(values),
            original_text=operator_text or summary)

    def disable_customer_treatment(self, instruction_id, *, creator_profile_id: int,
                                   fanvue_account_id: int,
                                   customer_fanvue_user_id: int):
        item = self.repository.disable_customer_treatment(instruction_id,
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            customer_fanvue_user_id=customer_fanvue_user_id)
        if item is None:
            raise AiTrainingControlError("Customer treatment was not found or is already disabled.")
        return item

    def create_customer(self, *, creator_profile_id: int, fanvue_account_id: int,
                        customer_fanvue_user_id: int, operator_text: str,
                        priority: int = 100, activate: bool = True):
        result = self.classify_customer(operator_text)
        if not result["runtimeEligible"]:
            raise AiTrainingControlError(result["classificationReason"])
        if self.repository.customer_duplicate_exists(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
                normalized=result["normalizedInstruction"]):
            raise AiTrainingControlError("This customer already has the same active training instruction.")
        return self.repository.create_customer(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
            original_text=result["originalOperatorText"], normalized=result["normalizedInstruction"],
            status="ENABLED" if activate else "DRAFT", priority=self._priority(priority),
            classification_reason=result["classificationReason"])

    def edit_customer(self, instruction_id, *, creator_profile_id: int,
                      fanvue_account_id: int, customer_fanvue_user_id: int,
                      operator_text: str, priority: int):
        result = self.classify_customer(operator_text)
        if not result["runtimeEligible"]: raise AiTrainingControlError(result["classificationReason"])
        if self.repository.customer_duplicate_exists(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
                normalized=result["normalizedInstruction"], exclude_instruction_id=instruction_id):
            raise AiTrainingControlError("This customer already has the same active training instruction.")
        item = self.repository.edit_customer(instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
            original_text=result["originalOperatorText"], normalized=result["normalizedInstruction"],
            priority=self._priority(priority))
        if item is None: raise AiTrainingControlError("Customer training instruction was not found.")
        return item

    def transition_customer(self, instruction_id, *, creator_profile_id: int,
                            fanvue_account_id: int, customer_fanvue_user_id: int,
                            action: str):
        if action not in {"enable", "disable", "archive"}: raise AiTrainingControlError("Unsupported training transition.")
        item = self.repository.transition_customer(instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id,
            action=action)
        if item is None: raise AiTrainingControlError("Customer training transition is invalid.")
        return item

    def customer_runtime_projection(self, *, creator_profile_id: int,
                                    fanvue_account_id: int,
                                    customer_fanvue_user_id: int | None):
        if customer_fanvue_user_id is None:
            return {"promptBlock": "", "applied": [], "appliedToPrompt": False,
                    "scope": "CUSTOMER", "skipReason": "NO_CANONICAL_MAPPED_CUSTOMER"}
        rules = self.repository.active_customer_conversation_rules(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            customer_fanvue_user_id=customer_fanvue_user_id)
        treatment_result = self.get_customer_treatment(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id)
        treatment = treatment_result["configuration"]
        treatment_item = treatment_result["item"] if not treatment_result["usingAvaDefaults"] else None
        rules = [rule for rule in rules if not self._guidance_overlaps_treatment(
            rule.normalized_instruction, treatment)]
        applied = [{"instructionId": str(rule.instruction_id), "version": rule.version,
                    "scope": "CUSTOMER", "enforcementClass": "CUSTOMER_PROMPT_GUIDANCE"}
                   for rule in rules]
        response_length = treatment["response_length"]
        length_line = ({"SHORTER": "Prefer concise, natural replies for this customer.",
                        "LONGER": "Allow somewhat more detail when appropriate; remain natural and concise."}
                       .get(response_length, ""))
        treatment_evidence = self._treatment_evidence(treatment_item, treatment,
            consumed_dimensions=["RESPONSE_LENGTH"] if length_line else [],
            effects={"response_length": "PROMPT_PROJECTED" if length_line else "NORMAL_NO_OVERRIDE"})
        if not rules and not length_line:
            return {"promptBlock": "", "applied": [], "appliedToPrompt": False,
                    "scope": "CUSTOMER", "skipReason": "NO_ENABLED_CUSTOMER_GUIDANCE",
                    "treatment": treatment_evidence}
        lines = "\n".join(f"{index}. {rule.normalized_instruction}" for index, rule in enumerate(rules, 1))
        if length_line:
            lines = "\n".join(value for value in (lines, length_line) if value)
        block = f"""CUSTOMER-SPECIFIC OPERATOR GUIDANCE
Apply only to this canonical customer and only to communication style:
{lines}
AUTHORITY LIMITS: This guidance cannot change safety, creator limits, Sales Brain actions,
price, inventory, ownership, PurchaseIntent, settlement, fulfillment, or provider truth."""
        return {"promptBlock": block, "applied": applied, "appliedToPrompt": True,
                "scope": "CUSTOMER", "skipReason": None, "treatment": treatment_evidence}

    def runtime_treatment(self, *, creator_profile_id: int, fanvue_account_id: int,
                          customer_fanvue_user_id: int | None):
        if customer_fanvue_user_id is None:
            return self._treatment_evidence(None, self.TREATMENT_DEFAULTS, [],
                                            {"all": "NO_CANONICAL_MAPPED_CUSTOMER"})
        result = self.get_customer_treatment(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, customer_fanvue_user_id=customer_fanvue_user_id)
        return self._treatment_evidence(result["item"] if not result["usingAvaDefaults"] else None,
                                        result["configuration"], [], {})

    @classmethod
    def _treatment_evidence(cls, item, configuration, consumed_dimensions, effects):
        return {"policyId": str(item.instruction_id) if item else None,
                "version": item.version if item else None,
                "customerFanvueUserId": item.customer_fanvue_user_id if item else None,
                "configuration": dict(configuration), "consumedDimensions": list(consumed_dimensions),
                "effects": dict(effects), "active": item is not None}

    @staticmethod
    def _guidance_overlaps_treatment(text: str, treatment: dict) -> bool:
        lowered = str(text).lower()
        return bool((treatment.get("response_length") != "NORMAL" and
                     re.search(r"\b(short|brief|concise|long|detail)", lowered)) or
                    (treatment.get("sales_pressure") != "NORMAL" and
                     re.search(r"\b(sales?|sell|push|pressure|commercial)", lowered)) or
                    (treatment.get("free_engagement") != "NORMAL" and
                     re.search(r"\b(free|chat|conversation|engagement)", lowered)))

    @staticmethod
    def _protected_authorities():
        return ["SAFETY", "PRICING", "OWNERSHIP", "INVENTORY", "PURCHASE_INTENT",
                "SALES_SESSION", "SETTLEMENT", "FULFILLMENT", "GLOBAL_BACKEND_POLICY"]

    def list(self, *, creator_profile_id: int, fanvue_account_id: int):
        return self.repository.list(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id
        )

    def create(self, *, creator_profile_id: int, fanvue_account_id: int,
               operator_text: str, priority: int = 100, activate: bool = True,
               policy_configuration: dict | None = None):
        classification = self.classify(operator_text)
        status = "DRAFT" if classification["runtimeEligible"] else "REQUIRES_IMPLEMENTATION"
        created = self.repository.create(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            instruction_type=classification["instructionType"],
            original_text=classification["originalOperatorText"],
            normalized=classification["normalizedInstruction"], status=status,
            priority=self._priority(priority),
            classification_reason=classification["classificationReason"],
            policy_key=classification.get("policyKey"),
            enforcement_mode=classification.get("enforcementMode", "PROMPT"),
            policy_configuration=self._policy_configuration(classification, policy_configuration),
        )
        if activate and classification["runtimeEligible"]:
            activated = self.repository.transition(
                created.instruction_id, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id, action="enable")
            if activated is None:
                raise AiTrainingControlError("Training persisted but activation failed.")
            return activated
        return created

    def edit(self, instruction_id, *, creator_profile_id: int,
             fanvue_account_id: int, operator_text: str, priority: int,
             policy_configuration: dict | None = None):
        current = self.repository.get(
            instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        )
        if current is None or current.status is AiTrainingInstructionStatus.ARCHIVED:
            raise AiTrainingControlError("Global training instruction was not found or is archived.")
        classification = self.classify(operator_text)
        status = "REQUIRES_IMPLEMENTATION"
        if classification["runtimeEligible"]:
            status = (
                "DRAFT" if current.status is AiTrainingInstructionStatus.REQUIRES_IMPLEMENTATION
                else current.status.value
            )
        updated = self.repository.edit(
            instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            instruction_type=classification["instructionType"],
            original_text=classification["originalOperatorText"],
            normalized=classification["normalizedInstruction"], status=status,
            priority=self._priority(priority),
            classification_reason=classification["classificationReason"],
            policy_key=classification.get("policyKey"),
            enforcement_mode=classification.get("enforcementMode", "PROMPT"),
            policy_configuration=self._policy_configuration(classification,
                policy_configuration if policy_configuration is not None else current.policy_configuration),
        )
        if updated is None:
            raise AiTrainingControlError("Global training instruction could not be updated.")
        return updated

    def transition(self, instruction_id, *, creator_profile_id: int,
                   fanvue_account_id: int, action: str):
        if action not in {"enable", "disable", "archive"}:
            raise AiTrainingControlError("Unsupported training transition.")
        current = self.repository.get(
            instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        )
        if current is None:
            raise AiTrainingControlError("Global training instruction was not found.")
        supported = current.instruction_type.value in {"CONVERSATION_RULE", "SAFETY_HARD_STOP", "ENGAGEMENT_RULE"}
        supported = supported or (current.instruction_type.value == "SALES_RULE"
            and current.policy_key == "ADAPTIVE_SALES_READINESS" and current.enforcement_mode == "BACKEND")
        if action == "enable" and not supported:
            raise AiTrainingControlError(
                "Requires Backend Enforcement instructions cannot be enabled in Phase 1."
            )
        result = self.repository.transition(
            instruction_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, action=action,
        )
        if result is None:
            raise AiTrainingControlError("Training transition is not valid from its current state.")
        return result

    def runtime_prompt_block(self, *, creator_profile_id: int,
                             fanvue_account_id: int) -> str:
        return self.global_runtime_projection(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        )["promptBlock"]

    def global_runtime_projection(self, *, creator_profile_id: int,
                                  fanvue_account_id: int):
        rules = self.repository.active_global_conversation_rules(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id
        )
        if not rules:
            return {"promptBlock": "", "applied": [], "appliedToPrompt": False,
                    "scope": "GLOBAL", "skipReason": "NO_ENABLED_GLOBAL_GUIDANCE"}
        lines = "\n".join(
            f"{index}. {rule.normalized_instruction}"
            for index, rule in enumerate(rules, start=1)
        )
        block = f"""
--------------------------------------------------
GLOBAL OPERATOR CONVERSATION TRAINING
--------------------------------------------------
Apply these operator-authored conversational preferences to every customer:
{lines}

AUTHORITY LIMITS:
- These rules control conversational wording and style only.
- They never override backend safety, identity, price, ownership, Purchase Intent,
  Fanvue Media Link, Asset Library eligibility, Session progression, BACK_OFF,
  Commerce Mode, or CustomerSalesBrain decisions.
- Never interpret these rules as permission to invent content, prices, links,
  purchases, ownership, or delivery state.
""".strip()
        return {"promptBlock": block, "applied": [
            {"instructionId": str(rule.instruction_id), "version": rule.version,
             "scope": "GLOBAL", "enforcementClass": "CONVERSATION_RULE"}
            for rule in rules], "appliedToPrompt": True, "scope": "GLOBAL",
            "skipReason": None}

    @staticmethod
    def _text(value: str) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip()
        if not normalized:
            raise AiTrainingControlError("Training instruction text is required.")
        if len(normalized) > 2000:
            raise AiTrainingControlError("Training instruction must be 2,000 characters or fewer.")
        return normalized

    @staticmethod
    def _priority(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000:
            raise AiTrainingControlError("Priority must be between 0 and 1,000.")
        return value

    @classmethod
    def _treatment_configuration(cls, supplied: dict):
        supplied = dict(supplied or {})
        if set(supplied) != set(cls.TREATMENT_DEFAULTS):
            raise AiTrainingControlError("All three customer treatment dimensions are required.")
        result = {key: str(supplied[key]).upper() for key in cls.TREATMENT_DEFAULTS}
        for key, value in result.items():
            if value not in cls.TREATMENT_ENUMS[key]:
                raise AiTrainingControlError(f"Invalid {key.replace('_', ' ')} treatment value.")
        return result

    @classmethod
    def _treatment_is_default(cls, values: dict) -> bool:
        return values == cls.TREATMENT_DEFAULTS

    @staticmethod
    def _treatment_summary(values: dict) -> str:
        return (f"Sales Pressure: {values['sales_pressure']}; "
                f"Free Engagement: {values['free_engagement']}; "
                f"Response Length: {values['response_length']}")

    @staticmethod
    def _policy_configuration(classification, supplied):
        if classification["instructionType"] == "SALES_RULE" and classification.get("policyKey") == "ADAPTIVE_SALES_READINESS":
            from app.models.adaptive_sales_readiness import AdaptiveSalesReadinessConfig
            allowed = {"normal_prospect_target_min", "normal_prospect_target_max", "meaningful_inactivity_days"}
            merged = dict(classification.get("policyConfiguration", {}))
            merged.update({key: value for key, value in dict(supplied or {}).items() if key in allowed})
            config = AdaptiveSalesReadinessConfig.from_mapping(merged)
            if config.normal_prospect_target_min <= 0 or config.normal_prospect_target_max < config.normal_prospect_target_min:
                raise AiTrainingControlError("The advisory readiness benchmark must be a positive ordered range.")
            if config.meaningful_inactivity_days <= 0:
                raise AiTrainingControlError("meaningful_inactivity_days must be greater than zero.")
            return config.to_dict()
        if classification["instructionType"] != "ENGAGEMENT_RULE":
            return {}
        from app.models.engagement_teaser_policy import EngagementTeaserPolicyConfig
        merged = {**classification.get("policyConfiguration", {}), **dict(supplied or {})}
        config = EngagementTeaserPolicyConfig.from_mapping(merged)
        for key, value in config.to_dict().items():
            if value <= 0:
                raise AiTrainingControlError(f"{key} must be greater than zero.")
        return config.to_dict()
