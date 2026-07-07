"""Provider-neutral runtime decision contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_value(values: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = values.get(name)
        if value is not None:
            return value
    return None


@dataclass(frozen=True)
class RuntimeDecision:
    """Canonical provider-neutral runtime decision from DecisionEngine."""

    response_text: str | None = None
    delivery_action: str | None = None
    delivery_type: str | None = None
    product_reference: str | None = None
    experience_reference: str | None = None
    offer_decision: dict[str, Any] = field(default_factory=dict)
    call_to_action: dict[str, Any] = field(default_factory=dict)
    publishing_reference: dict[str, Any] = field(default_factory=dict)
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    customer_context: dict[str, Any] = field(default_factory=dict)
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    block_reason: str | None = None
    raw_decision: dict[str, Any] = field(default_factory=dict)
    compatibility_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, decision: Mapping[str, Any] | None) -> "RuntimeDecision":
        values = dict(decision or {})
        offer = _mapping(values.get("offer"))
        offer_content = _mapping(offer.get("content"))

        product_reference = _first_value(
            values,
            "product_reference",
            "product_id",
            "current_product_id",
        )
        if product_reference is None:
            product_reference = _first_value(
                offer_content,
                "product_reference",
                "product_id",
                "current_product_id",
            )

        experience_reference = _first_value(
            values,
            "experience_reference",
            "experience_id",
            "current_experience_id",
        )
        progression = _mapping(values.get("experience_progression"))
        if experience_reference is None:
            experience_reference = _first_value(
                progression,
                "experience_reference",
                "experience_id",
                "current_experience_id",
            )

        publishing_reference = {
            key: value
            for key, value in {
                "media_link": _first_value(
                    values,
                    "media_link",
                    "paid_media_link",
                    "provider_output_url",
                    "fanvue_link",
                    "checkout_url",
                )
                or _first_value(
                    offer_content,
                    "media_link",
                    "paid_media_link",
                    "provider_output_url",
                    "fanvue_link",
                    "checkout_url",
                ),
                "asset_reference": _first_value(
                    values,
                    "asset_reference",
                    "asset_id",
                    "content_item_id",
                    "current_asset_id",
                )
                or _first_value(
                    offer_content,
                    "asset_reference",
                    "asset_id",
                    "content_item_id",
                    "current_asset_id",
                ),
            }.items()
            if value is not None
        }

        delivery_type = _first_value(values, "delivery_type")
        if delivery_type is None:
            delivery_type = _first_value(offer_content, "delivery_type")

        delivery_permission_mode = _first_value(
            values,
            "delivery_permission_mode",
            "delivery_mode",
        )
        if delivery_permission_mode is None:
            delivery_permission_mode = _first_value(
                offer_content,
                "delivery_permission_mode",
                "delivery_mode",
            )

        delivery_requires_payment = _first_value(
            values,
            "delivery_requires_payment",
            "requires_payment",
        )
        if delivery_requires_payment is None:
            delivery_requires_payment = _first_value(
                offer_content,
                "delivery_requires_payment",
                "requires_payment",
            )

        execution_metadata = {}
        if delivery_permission_mode is not None:
            execution_metadata["delivery_permission_mode"] = delivery_permission_mode
        if delivery_requires_payment is not None:
            execution_metadata["delivery_requires_payment"] = (
                delivery_requires_payment
            )

        return cls(
            response_text=_text(
                _first_value(values, "response_text", "response", "message_text")
            ),
            delivery_action=_text(
                _first_value(
                    values,
                    "delivery_action",
                    "commerce_action",
                    "next_suggested_action",
                )
            ),
            delivery_type=_text(delivery_type),
            product_reference=_text(product_reference),
            experience_reference=_text(experience_reference),
            offer_decision=offer,
            call_to_action={
                key: values[key]
                for key in (
                    "send_offer",
                    "send_nudge",
                    "nudge_type",
                    "soft_transition",
                    "next_suggested_action",
                )
                if key in values
            },
            publishing_reference=publishing_reference,
            execution_metadata=execution_metadata,
            customer_context=_mapping(
                _first_value(values, "customer_context", "customer_intelligence")
            ),
            runtime_metadata=_mapping(
                _first_value(values, "runtime_metadata", "metadata")
            ),
            blocked=values.get("blocked") is True,
            block_reason=_text(
                _first_value(
                    values,
                    "block_reason",
                    "blocking_reason",
                    "delivery_reason",
                    "error",
                )
            )
            if values.get("blocked") is True
            else None,
            raw_decision=values,
            compatibility_metadata={
                "source": "decision_engine_runtime_contract",
                "raw_dictionary_compatibility": True,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the legacy runtime shape while preserving typed fields."""

        if self.raw_decision:
            return dict(self.raw_decision)

        values = dict(self.raw_decision)
        if self.response_text is not None:
            values.setdefault("response", self.response_text)
            values.setdefault("response_text", self.response_text)
        if self.delivery_action is not None:
            values.setdefault("delivery_action", self.delivery_action)
        if self.delivery_type is not None:
            values.setdefault("delivery_type", self.delivery_type)
        if self.product_reference is not None:
            values.setdefault("product_reference", self.product_reference)
        if self.experience_reference is not None:
            values.setdefault("experience_reference", self.experience_reference)
        values.setdefault("blocked", self.blocked)
        if self.block_reason is not None:
            values.setdefault("block_reason", self.block_reason)
        return values


@dataclass(frozen=True, eq=False)
class DecisionEngineResult(Mapping[str, Any]):
    """Stable result wrapper for DecisionEngine runtime decisions."""

    runtime_decision: RuntimeDecision
    source: str = "DecisionEngine"
    compatibility_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        decision: Mapping[str, Any] | None,
        *,
        source: str = "DecisionEngine",
    ) -> "DecisionEngineResult":
        return cls(
            runtime_decision=RuntimeDecision.from_mapping(decision),
            source=source,
            compatibility_metadata={
                "provider_neutral": True,
                "legacy_mapping_supported": True,
                "contract": "RuntimeDecision",
            },
        )

    @classmethod
    def from_value(
        cls,
        value: "DecisionEngineResult | RuntimeDecision | Mapping[str, Any] | None",
    ) -> "DecisionEngineResult | None":
        if value is None:
            return None
        if isinstance(value, DecisionEngineResult):
            return value
        if isinstance(value, RuntimeDecision):
            return cls(runtime_decision=value)
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return None

    def to_dict(self) -> dict[str, Any]:
        return self.runtime_decision.to_dict()

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, DecisionEngineResult):
            return self.to_dict() == other.to_dict()
        if isinstance(other, Mapping):
            return self.to_dict() == dict(other)
        return False
