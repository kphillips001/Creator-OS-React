import os

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class AutomatedReactionGlobalSafetyService:
    """
    3D.18.7 — Global Automation Safety Integration

    Centralized global protection layer for automated
    monetization reactions.

    This service enforces:
    - global automation disable
    - realtime monetization toggle
    - post-purchase automation toggle
    - Fanvue outbound toggle
    - runtime suppression
    - maintenance protection

    This is the FINAL global safety wall before any
    outbound reaction can ever occur.
    """

    REQUIRED_ENV_FLAGS = [
        "ENABLE_REALTIME_MONETIZATION_REACTIONS",
        "ENABLE_POST_PURCHASE_AUTOMATION",
        "ENABLE_REALTIME_FANVUE_SEND",
    ]

    def __init__(self):
        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    def validate_global_safety(
        self,
        runtime_state: dict | None = None,
    ):
        runtime_state = runtime_state or {}

        global_result = (
            self.global_safety_service
            .can_send_post_purchase_reaction()
        )

        if global_result.get("blocked"):
            return self._blocked(
                global_result.get("reason")
                or "global_automation_disabled",
                {
                    "global_result": global_result,
                },
            )

        env_validation = (
            self._validate_required_flags()
        )

        if env_validation.get("blocked"):
            return env_validation

        runtime_validation = (
            self._validate_runtime_state(
                runtime_state
            )
        )

        if runtime_validation.get("blocked"):
            return runtime_validation

        return {
            "success": True,
            "blocked": False,
            "global_safe": True,
            "validated_flags": (
                self.REQUIRED_ENV_FLAGS
            ),
            "runtime_state_checked": True,
            "reason": "global_safety_valid",
        }

    def _validate_required_flags(self):
        missing_flags = []

        for env_name in self.REQUIRED_ENV_FLAGS:
            if not self._env_enabled(env_name):
                missing_flags.append(env_name)

        if missing_flags:
            return self._blocked(
                "required_automation_flags_disabled",
                {
                    "missing_flags": missing_flags,
                },
            )

        return {
            "success": True,
            "blocked": False,
        }

    def _validate_runtime_state(
        self,
        runtime_state: dict,
    ):
        if runtime_state.get(
            "automation_runtime_suppressed"
        ):
            return self._blocked(
                "runtime_automation_suppressed"
            )

        if runtime_state.get(
            "maintenance_mode"
        ):
            return self._blocked(
                "maintenance_mode_enabled"
            )

        if runtime_state.get(
            "safe_mode_enabled"
        ):
            return self._blocked(
                "safe_mode_enabled"
            )

        return {
            "success": True,
            "blocked": False,
        }

    def _env_enabled(
        self,
        env_name: str,
    ) -> bool:
        return (
            os.getenv(env_name, "false")
            .lower()
            .strip()
            == "true"
        )

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "global_safe": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result