"""Application boundary for creator-owned Commercial Roles."""

from __future__ import annotations

from collections.abc import Mapping

from app.models.commercial_role import (
    CommercialRole,
    CommercialRoleActorType,
    CommercialRoleOrigin,
    CommercialRoleState,
)
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_role_repository import CommercialRoleRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository


class CommercialRoleError(ValueError):
    pass


class CommercialRoleService:
    TRANSITIONS = {
        "approve": (CommercialRoleState.SUGGESTED, CommercialRoleState.APPROVED),
        "reject": (CommercialRoleState.SUGGESTED, CommercialRoleState.REJECTED),
        "deactivate": (CommercialRoleState.APPROVED, CommercialRoleState.INACTIVE),
        "reactivate": (CommercialRoleState.INACTIVE, CommercialRoleState.APPROVED),
    }

    def __init__(self, *, repository=None, asset_repository=None) -> None:
        self.repository = repository or CommercialRoleRepository()
        self.assets = asset_repository or AssetRepository()

    @staticmethod
    def vocabulary() -> tuple[CommercialRole, ...]:
        return tuple(CommercialRole)

    def list_for_asset(self, *, asset_id: int, creator_profile_id: int):
        self._asset(asset_id, creator_profile_id)
        return self.repository.list_for_asset(
            asset_id=asset_id, creator_profile_id=creator_profile_id
        )

    def effective_roles(self, *, asset_id: int, creator_profile_id: int):
        self._asset(asset_id, creator_profile_id)
        return self.repository.list_for_asset(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            states=(CommercialRoleState.APPROVED,),
        )

    def history(self, *, asset_id: int, creator_profile_id: int):
        self._asset(asset_id, creator_profile_id)
        return self.repository.list_history(
            asset_id=asset_id, creator_profile_id=creator_profile_id
        )

    def assign(
        self, *, asset_id: int, creator_profile_id: int, role,
        actor_type, actor_identifier: str | None, rationale: str | None = None,
    ):
        self._asset(asset_id, creator_profile_id)
        normalized_role = self._role(role)
        actor = self._human_actor(actor_type)
        existing = self.repository.get(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            role=normalized_role,
        )
        if existing is None:
            return self.repository.create(
                asset_id=asset_id, creator_profile_id=creator_profile_id,
                role=normalized_role, state=CommercialRoleState.APPROVED,
                origin=self._origin(actor), rationale=self._text(rationale),
                suggestion_confidence=None, evidence={},
                actor_type=actor, actor_identifier=self._text(actor_identifier),
                event_type="ASSIGNED",
            )
        if existing.state is CommercialRoleState.APPROVED:
            return existing
        if existing.state is CommercialRoleState.RETIRED:
            raise CommercialRoleError("Retired Commercial Roles cannot be reassigned.")
        if existing.state is CommercialRoleState.INACTIVE:
            return self._transition(
                existing, action="reactivate", actor=actor,
                actor_identifier=actor_identifier, reason=rationale,
            )
        if existing.state in {
            CommercialRoleState.SUGGESTED, CommercialRoleState.REJECTED,
        }:
            updated = self.repository.transition(
                assignment_id=existing.assignment_id,
                creator_profile_id=creator_profile_id,
                expected_state=existing.state,
                new_state=CommercialRoleState.APPROVED,
                actor_type=actor, actor_identifier=self._text(actor_identifier),
                event_type=(
                    "APPROVED" if existing.state is CommercialRoleState.SUGGESTED
                    else "RECONSIDERED_AND_ASSIGNED"
                ),
                reason=self._text(rationale),
                origin=(
                    None
                    if existing.state is CommercialRoleState.SUGGESTED
                    else self._origin(actor)
                ),
            )
            if updated is None:
                raise CommercialRoleError("Commercial Role changed during assignment.")
            return updated
        raise CommercialRoleError("Commercial Role cannot be assigned.")

    def approve(self, **values):
        return self._act("approve", **values)

    def reject(self, **values):
        return self._act("reject", **values)

    def deactivate(self, **values):
        return self._act("deactivate", **values)

    def reactivate(self, **values):
        return self._act("reactivate", **values)

    def retire(
        self, *, asset_id: int, creator_profile_id: int, role,
        actor_type, actor_identifier: str | None, reason: str | None = None,
    ):
        self._asset(asset_id, creator_profile_id)
        actor = self._human_actor(actor_type)
        assignment = self._existing(asset_id, creator_profile_id, role)
        if assignment.state is CommercialRoleState.RETIRED:
            return assignment
        if assignment.state not in {
            CommercialRoleState.APPROVED, CommercialRoleState.INACTIVE,
        }:
            raise CommercialRoleError(
                "Only approved or inactive Commercial Roles can be retired."
            )
        updated = self.repository.transition(
            assignment_id=assignment.assignment_id,
            creator_profile_id=creator_profile_id,
            expected_state=assignment.state,
            new_state=CommercialRoleState.RETIRED,
            actor_type=actor, actor_identifier=self._text(actor_identifier),
            event_type="RETIRED", reason=self._text(reason),
        )
        if updated is None:
            raise CommercialRoleError("Commercial Role changed during retirement.")
        return updated

    def _act(
        self, action: str, *, asset_id: int, creator_profile_id: int, role,
        actor_type, actor_identifier: str | None, reason: str | None = None,
    ):
        self._asset(asset_id, creator_profile_id)
        actor = self._human_actor(actor_type)
        assignment = self._existing(asset_id, creator_profile_id, role)
        return self._transition(
            assignment, action=action, actor=actor,
            actor_identifier=actor_identifier, reason=reason,
        )

    def _transition(
        self, assignment, *, action: str, actor,
        actor_identifier: str | None, reason: str | None,
    ):
        expected, target = self.TRANSITIONS[action]
        if assignment.state is target:
            return assignment
        if assignment.state is not expected:
            raise CommercialRoleError(
                f"Commercial Role cannot {action} from {assignment.state.value}."
            )
        updated = self.repository.transition(
            assignment_id=assignment.assignment_id,
            creator_profile_id=assignment.creator_profile_id,
            expected_state=expected, new_state=target, actor_type=actor,
            actor_identifier=self._text(actor_identifier),
            event_type=action.upper(), reason=self._text(reason),
        )
        if updated is None:
            raise CommercialRoleError(
                f"Commercial Role changed during {action}."
            )
        return updated

    def _existing(self, asset_id: int, creator_profile_id: int, role):
        assignment = self.repository.get(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            role=self._role(role),
        )
        if assignment is None:
            raise CommercialRoleError("Commercial Role assignment not found.")
        return assignment

    def _asset(self, asset_id: int, creator_profile_id: int):
        asset = self.assets.get_by_id(int(asset_id))
        if (
            asset is None
            or int(getattr(asset, "creator_profile_id", 0) or 0)
            != int(creator_profile_id)
        ):
            raise KeyError("Canonical Media Asset not found.")
        return asset

    @staticmethod
    def _role(value) -> CommercialRole:
        try:
            return value if isinstance(value, CommercialRole) else CommercialRole(
                str(value).strip().upper()
            )
        except ValueError as error:
            raise CommercialRoleError(f"Unsupported Commercial Role: {value}") from error

    @staticmethod
    def _human_actor(value) -> CommercialRoleActorType:
        try:
            actor = (
                value if isinstance(value, CommercialRoleActorType)
                else CommercialRoleActorType(str(value).strip().upper())
            )
        except ValueError as error:
            raise CommercialRoleError("Actor must be CREATOR or OPERATOR.") from error
        if actor is CommercialRoleActorType.AI:
            raise CommercialRoleError("AI cannot approve or assign Commercial Roles.")
        return actor

    @staticmethod
    def _origin(actor: CommercialRoleActorType) -> CommercialRoleOrigin:
        return (
            CommercialRoleOrigin.CREATOR_ASSIGNED
            if actor is CommercialRoleActorType.CREATOR
            else CommercialRoleOrigin.OPERATOR_ASSIGNED
        )

    @staticmethod
    def _text(value) -> str | None:
        text = str(value or "").strip()
        return text or None


class CommercialRoleSuggestionService:
    def __init__(
        self, *, role_service=None, intelligence_repository=None,
        photoshoot_repository=None,
    ) -> None:
        self.roles = role_service or CommercialRoleService()
        self.intelligence = (
            intelligence_repository or AssetIntelligenceRepository()
        )
        self.photoshoots = (
            photoshoot_repository or PhotoshootCommerceRepository()
        )

    def suggest(self, *, asset_id: int, creator_profile_id: int):
        self.roles._asset(asset_id, creator_profile_id)
        profile = self.intelligence.get_profile(int(asset_id))
        if (
            profile is None
            or int(profile.creator_profile_id) != int(creator_profile_id)
        ):
            return ()
        context = self.photoshoots.commercial_role_context_for_asset(
            int(asset_id), int(creator_profile_id)
        )
        suggestions = self._suggestions(profile, context or {})
        created = []
        for role, confidence, rationale, evidence in suggestions:
            existing = self.roles.repository.get(
                asset_id=asset_id, creator_profile_id=creator_profile_id,
                role=role,
            )
            if existing is not None:
                continue
            created.append(self.roles.repository.create(
                asset_id=asset_id, creator_profile_id=creator_profile_id,
                role=role, state=CommercialRoleState.SUGGESTED,
                origin=CommercialRoleOrigin.AI_SUGGESTED,
                rationale=rationale, suggestion_confidence=confidence,
                evidence=evidence, actor_type=CommercialRoleActorType.AI,
                actor_identifier="asset-intelligence-v1",
                event_type="SUGGESTED",
            ))
        return tuple(created)

    @classmethod
    def _suggestions(cls, profile, context: Mapping):
        confidence = cls._confidence(profile.overall_confidence)
        uses = " ".join(profile.suggested_use_cases).lower()
        preview = str(profile.preview_suitability or "").lower()
        values: list[tuple] = []

        def add(role, score, rationale, signals):
            if role not in {item[0] for item in values}:
                values.append((
                    role, round(max(0.0, min(1.0, score)), 3), rationale,
                    {"signals": tuple(signals), "source": "asset_intelligence"},
                ))

        if context.get("is_hero") or any(
            word in preview for word in ("high", "strong", "excellent")
        ):
            add(
                CommercialRole.HERO, max(confidence, 0.75),
                "The Asset is a strong leading visual candidate.",
                ("photoshoot_hero" if context.get("is_hero") else "preview_suitability",),
            )
        if any(word in uses for word in ("preview", "teaser", "discovery", "promo")):
            add(
                CommercialRole.DISCOVERY, confidence,
                "Asset Intelligence identifies discovery or preview suitability.",
                ("suggested_use_cases",),
            )
        if profile.quality_score is not None and profile.quality_score >= 0.65:
            add(
                CommercialRole.CORE, max(confidence, profile.quality_score),
                "The Asset has sufficient quality to carry primary commercial value.",
                ("quality_score",),
            )
        if context and not context.get("is_hero"):
            add(
                CommercialRole.PROGRESSION, confidence,
                "The Asset advances an ordered Photoshoot sequence.",
                ("photoshoot_membership", "shot_order"),
            )
        if (
            any(word in uses for word in ("premium", "exclusive", "vip"))
            or (
                profile.content_uniqueness is not None
                and profile.content_uniqueness >= 0.75
            )
        ):
            add(
                CommercialRole.PREMIUM,
                max(confidence, float(profile.content_uniqueness or 0.0)),
                "The Asset has premium or distinctive commercial positioning.",
                ("suggested_use_cases", "content_uniqueness"),
            )
        if context.get("is_last"):
            add(
                CommercialRole.FINALE, max(confidence, 0.7),
                "The Asset is the closing approved shot in its Photoshoot.",
                ("photoshoot_membership", "final_shot"),
            )
        if any(word in uses for word in ("bonus", "alternate", "extra", "behind")):
            add(
                CommercialRole.BONUS, confidence,
                "Asset Intelligence identifies supplemental commercial value.",
                ("suggested_use_cases",),
            )
        return tuple(values)

    @staticmethod
    def _confidence(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.6
