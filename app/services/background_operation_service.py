"""Application-wide background operation lifecycle service."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping

from app.repositories.background_operation_repository import BackgroundOperationRepository


class BackgroundOperationService:
    def __init__(self, repository=None) -> None:
        self.repository = repository or BackgroundOperationRepository()

    def create(self, **values):
        return self.repository.create(**values)

    def get(self, operation_id, *, creator_profile_id, account_id=None):
        return self.repository.get(operation_id, creator_profile_id=creator_profile_id, account_id=account_id)

    def list(self, *, creator_profile_id, account_id=None, status="active", workspace=None,
             subject_type=None, subject_id=None):
        if status == "active":
            return self.repository.list_active(
                creator_profile_id=creator_profile_id, account_id=account_id, workspace=workspace,
                subject_type=subject_type, subject_id=subject_id)
        return self.repository.list_recent_terminal(
            creator_profile_id=creator_profile_id, account_id=account_id, workspace=workspace)

    def payload(self, operation) -> dict[str, Any]:
        value = asdict(operation)
        for key, item in tuple(value.items()):
            if isinstance(item, datetime): value[key] = item.isoformat()
        return {self._camel(key): item for key, item in value.items()}

    def progress(self, operation_id, **values):
        return self.repository.update_progress(operation_id, **values)

    def stage(self, operation_id, stage, message=None, metadata=None):
        current = self.repository._one_unscoped(operation_id)
        return self.repository.transition(
            operation_id, current.status, stage=stage, message=message, metadata=metadata)

    def succeed(self, operation_id, *, result_reference=None, metadata=None, partial=False, message=None):
        return self.repository.transition(
            operation_id, "PARTIAL" if partial else "SUCCEEDED", stage="COMPLETE",
            message=message or ("Completed with partial success" if partial else "Completed"),
            result_reference=result_reference, metadata=metadata)

    def fail(self, operation_id, error, *, code="EXECUTION_FAILED", metadata=None):
        return self.repository.transition(
            operation_id, "FAILED", stage="FAILED", message=str(error),
            error_code=code, error_message=str(error), metadata=metadata)

    def cancel(self, operation_id, message="Cancelled"):
        return self.repository.transition(
            operation_id, "CANCELLED", stage="CANCELLED", message=message)

    @staticmethod
    def _camel(value: str) -> str:
        head, *tail = value.split("_")
        return head + "".join(item[:1].upper() + item[1:] for item in tail)
