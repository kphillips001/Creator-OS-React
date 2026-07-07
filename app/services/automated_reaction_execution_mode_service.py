import os


class AutomatedReactionExecutionModeService:
    """
    3D.18.8 — Fanvue Send Toggle / Dry-Run Mode

    Determines whether automated monetization reactions should:

    - remain blocked
    - operate in dry-run mode
    - operate in future live-send mode

    IMPORTANT:
    This service does NOT send outbound messages.
    It only determines execution mode safely.
    """

    def determine_execution_mode(
        self,
        runtime_state: dict | None = None,
    ):
        runtime_state = runtime_state or {}

        if runtime_state.get(
            "force_dry_run_mode"
        ):
            return self._dry_run(
                "runtime_forced_dry_run"
            )

        if runtime_state.get(
            "disable_all_reactions"
        ):
            return self._blocked(
                "runtime_reactions_disabled"
            )

        monetization_enabled = (
            self._env_enabled(
                "ENABLE_REALTIME_MONETIZATION_REACTIONS"
            )
        )

        post_purchase_enabled = (
            self._env_enabled(
                "ENABLE_POST_PURCHASE_AUTOMATION"
            )
        )

        realtime_send_enabled = (
            self._env_enabled(
                "ENABLE_REALTIME_FANVUE_SEND"
            )
        )

        if not monetization_enabled:
            return self._blocked(
                "monetization_reactions_disabled"
            )

        if not post_purchase_enabled:
            return self._blocked(
                "post_purchase_automation_disabled"
            )

        if not realtime_send_enabled:
            return self._dry_run(
                "fanvue_live_send_disabled"
            )

        return {
            "success": True,
            "blocked": False,
            "dry_run": False,
            "live_send_allowed": True,
            "execution_mode": "live_send",
            "reason": "live_send_enabled",
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

    def _dry_run(
        self,
        reason: str,
    ):
        return {
            "success": True,
            "blocked": False,
            "dry_run": True,
            "live_send_allowed": False,
            "execution_mode": "dry_run",
            "reason": reason,
        }

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "dry_run": False,
            "live_send_allowed": False,
            "execution_mode": "blocked",
            "reason": reason,
        }