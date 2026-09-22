"""Operation-scoped upper-bound authority for historical corrective execution."""
from __future__ import annotations

class RecoveryExecutionConstraintService:
    CONVERSATION_ONLY_TEXT = "CONVERSATION_ONLY_TEXT"
    REASON = "OPERATOR_RECOVERY_CONVERSATION_ONLY"
    POLICY_CAPABILITY_VERSION = "CONVERSATION_ONLY_TEXT_SALES_BRAIN_PRECEDENCE_V2"
    COMMERCIAL_ACTIONS = frozenset({
        "PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "CONTENT_ALTERNATIVE",
    })
    COMMERCIAL_KEYS = frozenset({
        "asset_path", "commercial_asset", "commercial_offering_id", "delivery_url",
        "media_link", "offering_id", "private_chat_unlock_button", "product_reference",
        "publication_id", "purchase_intent_id", "safe_teaser_asset_id", "unlock_url",
    })

    @classmethod
    def authority(cls) -> dict:
        return {
            "constraint": cls.CONVERSATION_ONLY_TEXT,
            "authority": "OPERATOR_APPROVED_RECOVERY_PLAN",
            "commercialActionAuthorization": "DENIED_BY_OPERATOR_RECOVERY_CONSTRAINT",
            "commercialProgressionAllowed": False,
            "purchaseIntentAllowed": False,
            "mediaAllowed": False,
            "textOnly": True,
            "reason": cls.REASON,
        }

    @classmethod
    def current_policy_capability(cls) -> dict:
        """Deterministic code capability used by bounded follow-up eligibility."""
        return {
            "version": cls.POLICY_CAPABILITY_VERSION,
            "constraint": cls.CONVERSATION_ONLY_TEXT,
            "salesBrainCommercialActionBlocked": True,
            "commercialContextCleared": True,
            "purchaseIntentProhibited": True,
            "mediaProhibited": True,
            "deliveryTypeRequired": "MESSAGE_TEXT",
        }

    @classmethod
    def supports_repaired_conversation_only_policy(cls) -> bool:
        capability = cls.current_policy_capability()
        return bool(
            capability["salesBrainCommercialActionBlocked"]
            and capability["commercialContextCleared"]
            and capability["purchaseIntentProhibited"]
            and capability["mediaProhibited"]
            and capability["deliveryTypeRequired"] == "MESSAGE_TEXT"
        )

    @classmethod
    def from_operation(cls, operation) -> dict:
        payload = dict(getattr(operation, "delivery_payload", None) or {})
        value = dict(payload.get("recoveryExecutionConstraint") or {})
        return value if value.get("constraint") == cls.CONVERSATION_ONLY_TEXT else {}

    @classmethod
    def constrained(cls, operation) -> bool:
        return bool(cls.from_operation(operation))

    @classmethod
    def validate_result(cls, operation, result) -> tuple[bool, str | None]:
        if not cls.constrained(operation):
            return True, None
        delivery = dict(getattr(result, "delivery_payload", None) or {})
        diagnostics = dict(getattr(result, "diagnostic_metadata", None) or {})
        actions = {
            str(value).upper() for key, value in cls._walk(diagnostics)
            if key.lower() in {"action", "recommended_action", "commercial_action"}
        }
        keys = {key.lower() for key, value in cls._walk(delivery) if value not in (None, "", False, [], {})}
        from app.models.telegram_inbound import canonical_text_delivery_type
        # Every declared type must agree; an outer TEXT alias cannot hide media.
        delivery_types = [canonical_text_delivery_type(value) for value in (
            getattr(result, "delivery_type", ""), delivery.get("type"), delivery.get("delivery_type"))
            if value not in (None, "")]
        invalid_type = any(value != "MESSAGE_TEXT" for value in delivery_types)
        delivery_mode = str(getattr(result, "delivery_mode", "") or "").lower()
        violation = bool(
            getattr(result, "offer_authorized", False)
            or getattr(result, "delivery_requires_payment", False)
            or actions.intersection(cls.COMMERCIAL_ACTIONS)
            or keys.intersection(cls.COMMERCIAL_KEYS)
            or invalid_type
            or delivery_mode in {"private_ppv_media", "unlock_gateway", "commercial"}
        )
        return (False, cls.REASON) if violation else (True, None)

    @classmethod
    def validate_persisted_delivery(cls, operation) -> tuple[bool, str | None]:
        if not cls.constrained(operation):
            return True, None
        payload = dict(getattr(operation, "response_payload", None) or {})
        result = type("PersistedResult", (), {
            "delivery_payload": dict(getattr(operation, "delivery_payload", None) or {}),
            "diagnostic_metadata": dict(payload.get("diagnostic_metadata") or {}),
            "offer_authorized": payload.get("offer_authorized", False),
            "delivery_requires_payment": payload.get("delivery_requires_payment", False),
            "delivery_type": payload.get("delivery_type", ""),
            "delivery_mode": payload.get("delivery_mode", ""),
        })()
        # Ignore the authority marker itself while validating customer payload.
        result.delivery_payload.pop("recoveryExecutionConstraint", None)
        result.delivery_payload.pop("approvedHistoricalCorrection", None)
        result.delivery_payload.pop("canonicalNotDeliveredCorrection", None)
        return cls.validate_result(operation, result)

    @classmethod
    def apply_generation_context(cls, context: dict) -> dict:
        return {**dict(context or {}), "recoveryExecutionConstraint": cls.authority()}

    @classmethod
    def _walk(cls, value, prefix=""):
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key), item
                yield from cls._walk(item, f"{prefix}.{key}")
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from cls._walk(item, prefix)
