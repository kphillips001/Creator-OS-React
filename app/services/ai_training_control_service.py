"""Classification and runtime projection for operator-authored AI training."""
import re

from app.models.ai_training_control import AiTrainingInstructionStatus
from app.repositories.ai_training_control_repository import AiTrainingControlRepository


class AiTrainingControlError(ValueError):
    pass


class AiTrainingControlService:
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
        rules = self.repository.active_global_conversation_rules(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id
        )
        if not rules:
            return ""
        lines = "\n".join(
            f"{index}. {rule.normalized_instruction}"
            for index, rule in enumerate(rules, start=1)
        )
        return f"""
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
