"""Creator-controlled Commerce Destination boundary for Business Assets."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Iterable, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.commerce_destination import (
    COMMERCE_DESTINATION_SCHEMA_VERSION,
    CommerceDestination,
    CommerceDestinationHistoryEntry,
    CommerceDestinationRequest,
    CommerceDestinationResult,
    DestinationRoutingIntent,
    DestinationRoutingOwner,
    DestinationRoutingStatus,
)
from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceDestinationStatus,
    CommerceRegistrationStatus,
)
from app.models.generation_engine import utc_now

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.repositories.commerce_destination_repository import (
        CommerceDestinationRepository,
    )
    from app.repositories.commerce_registration_repository import (
        CommerceRegistrationRepository,
    )


class CommerceDestinationService:
    """Persists creator destination choices without executing downstream routes."""

    def __init__(
        self,
        *,
        registration_repository: "CommerceRegistrationRepository | None" = None,
        destination_repository: "CommerceDestinationRepository | None" = None,
        asset_repository: "AssetRepository | None" = None,
        entry_policy: Any | None = None,
    ) -> None:
        if registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            registration_repository = CommerceRegistrationRepository()
        if destination_repository is None:
            from app.repositories.commerce_destination_repository import (
                CommerceDestinationRepository,
            )

            destination_repository = CommerceDestinationRepository()
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository

            asset_repository = AssetRepository()
        self.registration_repository = registration_repository
        self.destination_repository = destination_repository
        self.asset_repository = asset_repository
        if entry_policy is None:
            from app.services.autonomous_commerce_entry_policy import (
                AutonomousCommerceEntryPolicy,
            )

            entry_policy = AutonomousCommerceEntryPolicy(asset_repository=asset_repository)
        self.entry_policy = entry_policy

    def get_destination(self, asset_id: int) -> BusinessAssetRecord | None:
        return self.registration_repository.get_by_asset_id(int(asset_id))

    def set_destination(
        self,
        request: CommerceDestinationRequest,
    ) -> CommerceDestinationResult:
        return self.change_destination(request)

    def change_destination(
        self,
        request: CommerceDestinationRequest,
    ) -> CommerceDestinationResult:
        destination = self._coerce_destination(request.destination)
        if destination is None:
            return CommerceDestinationResult(
                success=False,
                asset_id=int(request.asset_id),
                errors=("unsupported_commerce_destination",),
                timestamp=utc_now(),
            )

        record = self.registration_repository.get_by_asset_id(request.asset_id)
        validation_error = self._validation_error(record, request)
        if validation_error:
            return CommerceDestinationResult(
                success=False,
                asset_id=int(request.asset_id),
                errors=(validation_error,),
                timestamp=utc_now(),
            )
        assert record is not None

        previous = self._coerce_destination(record.selected_commerce_destination)
        existing_history = (
            self.destination_repository.history_by_idempotency_key(
                request.idempotency_key
            )
            if request.idempotency_key
            else None
        )
        if existing_history is not None and previous == destination:
            return self._result(
                record,
                previous_destination=previous,
                changed=False,
                unchanged=True,
            )

        desired_owners = self._routing_owners_for_destination(destination)
        existing_intents = self.destination_repository.list_routing_intents(
            record.asset_id,
            include_cancelled=True,
        )
        active_by_owner = {
            intent.routing_owner: intent
            for intent in existing_intents
            if intent.routing_status != DestinationRoutingStatus.CANCELLED
        }

        warnings: list[str] = []
        created: list[DestinationRoutingIntent] = []
        for owner in desired_owners:
            existing = active_by_owner.get(owner)
            if existing is not None:
                if existing.selected_destination != destination:
                    self.destination_repository.upsert_routing_intent(
                        replace(
                            existing,
                            selected_destination=destination,
                            source_workflow=request.source_workflow
                            or existing.source_workflow,
                            updated_at=utc_now(),
                        )
                    )
                continue
            intent = self._build_routing_intent(
                record,
                selected_destination=destination,
                owner=owner,
                source_workflow=request.source_workflow,
            )
            created.append(self.destination_repository.upsert_routing_intent(intent))

        removed_owners = set(active_by_owner).difference(desired_owners)
        for owner in removed_owners:
            intent = active_by_owner[owner]
            if intent.routing_status == DestinationRoutingStatus.ROUTED:
                warnings.append(f"completed_route_not_reversed:{owner.value}")
                continue
            cancelled = replace(
                intent,
                routing_status=DestinationRoutingStatus.CANCELLED,
                metadata={
                    **dict(intent.metadata or {}),
                    "cancelled_by_destination_change": True,
                    "cancelled_at": utc_now(),
                    "new_destination": destination.value,
                },
                updated_at=utc_now(),
            )
            self.destination_repository.upsert_routing_intent(cancelled)

        changed = previous != destination
        now = utc_now()
        updated_record = replace(
            record,
            business_lifecycle_state=BusinessAssetLifecycleState.ROUTING_PENDING
            if desired_owners
            else BusinessAssetLifecycleState.DESTINATION_SELECTED,
            commerce_destination_status=CommerceDestinationStatus.ROUTING_PENDING
            if desired_owners
            else CommerceDestinationStatus.DESTINATION_SELECTED,
            selected_commerce_destination=destination.value,
            destination_selected_at=now,
            destination_selected_by_profile_id=request.creator_profile_id,
            destination_source_workflow=request.source_workflow,
            destination_routing_state=(
                CommerceDestinationStatus.ROUTING_PENDING.value
                if desired_owners
                else CommerceDestinationStatus.DESTINATION_SELECTED.value
            ),
            destination_change_note=request.reason,
            destination_revision=int(record.destination_revision or 0)
            + (1 if changed else 0),
            warnings=tuple(dict.fromkeys((*record.warnings, *warnings))),
            updated_at=now,
        )
        updated_record = self.registration_repository.upsert_record(updated_record)

        if changed:
            self.destination_repository.append_history(
                CommerceDestinationHistoryEntry(
                    history_id=self._history_id(
                        updated_record.asset_id,
                        request.idempotency_key,
                        updated_record.destination_revision,
                    ),
                    asset_id=updated_record.asset_id,
                    registration_id=updated_record.registration_id,
                    previous_destination=previous,
                    new_destination=destination,
                    creator_profile_id=request.creator_profile_id,
                    creator_identity=dict(request.creator_identity or {}),
                    source_workflow=request.source_workflow,
                    source_session_id=request.source_session_id,
                    reason=request.reason,
                    idempotency_key=request.idempotency_key,
                    created_at=now,
                    metadata={"schema_version": COMMERCE_DESTINATION_SCHEMA_VERSION},
                )
            )

        intents = self.destination_repository.list_routing_intents(
            updated_record.asset_id,
            include_cancelled=True,
        )
        return CommerceDestinationResult(
            success=True,
            asset_id=updated_record.asset_id,
            selected_destination=destination,
            previous_destination=previous,
            destination_status=updated_record.commerce_destination_status.value,
            routing_intents_created=tuple(created),
            routing_intents=intents,
            changed=changed,
            unchanged=not changed,
            creator_profile_id=request.creator_profile_id,
            timestamp=now,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def get_destination_history(
        self,
        asset_id: int,
        *,
        limit: int = 100,
    ) -> tuple[CommerceDestinationHistoryEntry, ...]:
        return self.destination_repository.list_history(asset_id, limit=limit)

    def list_assets_awaiting_destination(
        self,
        *,
        limit: int = 500,
    ) -> tuple[BusinessAssetRecord, ...]:
        return tuple(self.registration_repository.list_awaiting_destination(limit=limit))

    def list_assets_by_destination(
        self,
        destination: CommerceDestination | str,
        *,
        limit: int = 500,
    ) -> tuple[BusinessAssetRecord, ...]:
        selected = self._coerce_destination(destination)
        if selected is None:
            return ()
        list_by_destination = getattr(
            self.registration_repository,
            "list_by_selected_destination",
            None,
        )
        if callable(list_by_destination):
            return tuple(list_by_destination(selected.value, limit=limit))
        return tuple(
            record
            for record in self.registration_repository.list_registered(limit=limit)
            if record.selected_commerce_destination == selected.value
        )

    def list_pending_routing_intents(
        self,
        *,
        limit: int = 100,
    ) -> tuple[DestinationRoutingIntent, ...]:
        return self.destination_repository.list_pending_routing_intents(limit=limit)

    def refresh_routing_state(self, asset_id: int) -> CommerceDestinationResult:
        record = self.registration_repository.get_by_asset_id(asset_id)
        if record is None:
            return CommerceDestinationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("business_asset_not_found",),
                timestamp=utc_now(),
            )
        intents = self.destination_repository.list_routing_intents(
            asset_id,
            include_cancelled=True,
        )
        active = tuple(
            intent
            for intent in intents
            if intent.routing_status != DestinationRoutingStatus.CANCELLED
        )
        if active and all(
            intent.routing_status == DestinationRoutingStatus.ROUTED
            for intent in active
        ):
            status = CommerceDestinationStatus.ROUTED
            lifecycle = BusinessAssetLifecycleState.ROUTED
        elif any(
            intent.routing_status == DestinationRoutingStatus.ROUTING_FAILED
            for intent in active
        ):
            status = CommerceDestinationStatus.ROUTING_FAILED
            lifecycle = BusinessAssetLifecycleState.ROUTING_FAILED
        elif active:
            status = CommerceDestinationStatus.ROUTING_PENDING
            lifecycle = BusinessAssetLifecycleState.ROUTING_PENDING
        else:
            status = CommerceDestinationStatus.DESTINATION_SELECTED
            lifecycle = BusinessAssetLifecycleState.DESTINATION_SELECTED
        updated = self.registration_repository.upsert_record(
            replace(
                record,
                commerce_destination_status=status,
                business_lifecycle_state=lifecycle,
                destination_routing_state=status.value,
                last_refreshed_at=utc_now(),
            )
        )
        return self._result(updated, routing_intents=intents)

    def per_route_status(
        self,
        asset_id: int,
    ) -> Mapping[str, str]:
        return {
            intent.routing_owner.value: intent.routing_status.value
            for intent in self.destination_repository.list_routing_intents(
                asset_id,
                include_cancelled=True,
            )
        }

    def backfill_legacy_destinations(
        self,
        *,
        limit: int = 500,
    ) -> tuple[CommerceDestinationResult, ...]:
        results: list[CommerceDestinationResult] = []
        for record in self.registration_repository.list_registered(limit=limit):
            if record.selected_commerce_destination:
                continue
            inferred = self.suggest_destination_from_compatibility(
                self._record_compatibility_context(record)
            )
            if inferred is None:
                continue
            results.append(
                self.set_destination(
                    CommerceDestinationRequest(
                        asset_id=record.asset_id,
                        registration_id=record.registration_id,
                        destination=inferred,
                        creator_profile_id=record.creator_profile_id,
                        source_workflow="commerce_destination_backfill",
                        reason="legacy_unambiguous_destination_metadata",
                        idempotency_key=f"commerce-destination-backfill:{record.asset_id}:{inferred.value}",
                    )
                )
            )
        return tuple(results)

    @classmethod
    def suggest_destination_from_compatibility(
        cls,
        metadata: Mapping[str, Any],
    ) -> CommerceDestination | None:
        values = {
            key: str(value or "").strip().lower()
            for key, value in dict(metadata or {}).items()
            if value is not None
        }
        if cls._truthy(values.get("archive_only")):
            return CommerceDestination.ARCHIVE_ONLY
        wall_signals = (
            values.get("upload_intent", "").startswith("wall_")
            or values.get("folder_name") == "wall"
            or values.get("classification", "").startswith("wall_")
        )
        chat_signals = any(
            token in values.get("delivery_type", "")
            for token in ("chat", "conversation", "dm")
        )
        if wall_signals and not chat_signals:
            return CommerceDestination.TELEGRAM_WALL
        if chat_signals and not wall_signals:
            return CommerceDestination.CUSTOMER_CONVERSATIONS
        return None

    def _validation_error(
        self,
        record: BusinessAssetRecord | None,
        request: CommerceDestinationRequest,
    ) -> str | None:
        if record is None:
            return "business_asset_not_found"
        if str(record.registration_id) != str(request.registration_id):
            return "business_registration_mismatch"
        if record.commerce_registration_status != CommerceRegistrationStatus.REGISTERED:
            return "business_asset_not_registered"
        if str(record.approval_status).lower() != "approved":
            return "asset_not_approved"
        if not record.content_intelligence_ready:
            return "content_intelligence_not_ready"
        policy = self.entry_policy.can_select_destination(
            record,
            destination=request.destination,
        )
        if not policy.allowed:
            return policy.reasons[0] if policy.reasons else "commerce_entry_not_allowed"
        return None

    @staticmethod
    def _routing_owners_for_destination(
        destination: CommerceDestination,
    ) -> tuple[DestinationRoutingOwner, ...]:
        if destination == CommerceDestination.TELEGRAM_WALL:
            return (DestinationRoutingOwner.TELEGRAM_WALL,)
        if destination == CommerceDestination.CUSTOMER_CONVERSATIONS:
            return (DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,)
        if destination == CommerceDestination.BOTH:
            return (
                DestinationRoutingOwner.TELEGRAM_WALL,
                DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
            )
        if destination == CommerceDestination.ARCHIVE_ONLY:
            return (DestinationRoutingOwner.ARCHIVE,)
        return ()

    @staticmethod
    def _owner_service(owner: DestinationRoutingOwner) -> str:
        return {
            DestinationRoutingOwner.TELEGRAM_WALL: "CommerceDestination.TelegramWallHandoff",
            DestinationRoutingOwner.CUSTOMER_CONVERSATIONS: "CommerceDestination.CustomerConversationsHandoff",
            DestinationRoutingOwner.ARCHIVE: "CommerceDestination.ArchiveOnlyHandoff",
        }[owner]

    @staticmethod
    def _owner_prerequisites(owner: DestinationRoutingOwner) -> tuple[str, ...]:
        if owner == DestinationRoutingOwner.TELEGRAM_WALL:
            return ("provider_media_ready", "wall_destination_executor_available")
        if owner == DestinationRoutingOwner.CUSTOMER_CONVERSATIONS:
            return ("media_link_ready", "conversation_delivery_executor_available")
        if owner == DestinationRoutingOwner.ARCHIVE:
            return ("canonical_asset_preserved",)
        return ()

    def _build_routing_intent(
        self,
        record: BusinessAssetRecord,
        *,
        selected_destination: CommerceDestination,
        owner: DestinationRoutingOwner,
        source_workflow: str | None,
    ) -> DestinationRoutingIntent:
        return DestinationRoutingIntent(
            routing_intent_id=self._routing_intent_id(record.asset_id, owner),
            asset_id=record.asset_id,
            registration_id=record.registration_id,
            selected_destination=selected_destination,
            routing_owner=owner,
            routing_status=DestinationRoutingStatus.ROUTING_PENDING,
            source_workflow=source_workflow,
            downstream_owner_service=self._owner_service(owner),
            downstream_prerequisites=self._owner_prerequisites(owner),
            metadata={
                "selection_boundary": "CommerceDestinationService",
                "executes_downstream_route": False,
            },
            created_at=utc_now(),
            updated_at=utc_now(),
        )

    @staticmethod
    def _routing_intent_id(asset_id: int, owner: DestinationRoutingOwner) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"creator-os:commerce-destination-route:{int(asset_id)}:{owner.value}",
        )

    @staticmethod
    def _history_id(
        asset_id: int,
        idempotency_key: str | None,
        revision: int,
    ) -> UUID:
        key = idempotency_key or f"revision:{int(revision)}"
        return uuid5(
            NAMESPACE_URL,
            f"creator-os:commerce-destination-history:{int(asset_id)}:{key}",
        )

    @classmethod
    def _coerce_destination(cls, value: Any) -> CommerceDestination | None:
        if isinstance(value, CommerceDestination):
            return value
        if value is None:
            return None
        normalized = str(value).strip().upper()
        if normalized in {"TELEGRAM", "WALL", "TELEGRAM WALL"}:
            normalized = CommerceDestination.TELEGRAM_WALL.value
        if normalized in {"CHAT", "CUSTOMER_CONVERSATION", "CONVERSATIONS"}:
            normalized = CommerceDestination.CUSTOMER_CONVERSATIONS.value
        if normalized in {"ARCHIVE", "ARCHIVE ONLY"}:
            normalized = CommerceDestination.ARCHIVE_ONLY.value
        try:
            return CommerceDestination(normalized)
        except Exception:
            return None

    @staticmethod
    def _truthy(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "y"}

    @staticmethod
    def _record_compatibility_context(record: BusinessAssetRecord) -> Mapping[str, Any]:
        provenance = dict(record.registration_provenance or {})
        creator_intent = provenance.get("creator_intent")
        if not isinstance(creator_intent, Mapping):
            creator_intent = {}
        publishing = dict(record.publishing_readiness or {})
        return {
            "upload_intent": creator_intent.get("legacy_upload_intent")
            or provenance.get("legacy_upload_intent"),
            "delivery_type": record.delivery_type,
            "folder_name": publishing.get("folder_name"),
            "classification": publishing.get("classification"),
            "archive_only": provenance.get("archive_only"),
        }

    def _result(
        self,
        record: BusinessAssetRecord,
        *,
        previous_destination: CommerceDestination | None = None,
        changed: bool = False,
        unchanged: bool = False,
        routing_intents: Iterable[DestinationRoutingIntent] | None = None,
    ) -> CommerceDestinationResult:
        selected = self._coerce_destination(record.selected_commerce_destination)
        if routing_intents is None:
            routing_intents = self.destination_repository.list_routing_intents(
                record.asset_id,
                include_cancelled=True,
            )
        return CommerceDestinationResult(
            success=True,
            asset_id=record.asset_id,
            selected_destination=selected,
            previous_destination=previous_destination,
            destination_status=record.commerce_destination_status.value,
            routing_intents=tuple(routing_intents),
            changed=changed,
            unchanged=unchanged,
            creator_profile_id=record.destination_selected_by_profile_id,
            timestamp=utc_now(),
            warnings=record.warnings,
        )
