"""Standard machine-actionable diagnostic contract."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ExplainableDiagnostic:
    status: str
    summary: str
    classification: str
    root_cause: str
    evidence: list[dict[str, Any]]
    confidence: float
    automatic_resolution: bool
    resolution_reason: str
    recommended_action: str
    affected_components: list[str]
    last_updated: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
