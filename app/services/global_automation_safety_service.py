import json
import os
from pathlib import Path


class GlobalAutomationSafetyService:
    """
    3D.15 / 3E — Global Automation Safety Service

    Central safety gate for ALL outbound automation.

    Reads dashboard config first:
    data/config/behavior_config.json

    Falls back to environment variables if dashboard config is missing.
    """

    CONFIG_PATH = Path("data/config/behavior_config.json")

    def __init__(self):
        self.behavior_config = self._load_behavior_config()

    def refresh(self) -> dict:
        """Reload the authoritative behavior configuration for live processes."""
        self.behavior_config = self._load_behavior_config()
        return self.behavior_config

    def _load_behavior_config(self) -> dict:
        try:
            if self.CONFIG_PATH.exists():
                with self.CONFIG_PATH.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    return json.load(file)
        except Exception as error:
            print(
                "[GLOBAL SAFETY CONFIG LOAD FAILED]",
                str(error),
            )

        return {}

    def _env_enabled(
        self,
        key: str,
        default: bool = False,
    ) -> bool:
        value = os.getenv(key)

        if value is None:
            return default

        return str(value).lower() in {
            "true",
            "1",
            "yes",
            "on",
            "enabled",
        }

    def _config_enabled(
        self,
        key: str,
        default: bool = False,
    ) -> bool:
        value = self.behavior_config.get(key)

        if value is None:
            return self._env_enabled(
                key.upper(),
                default,
            )

        return bool(value)

    def _module_enabled(
        self,
        key: str,
        env_key: str,
        default: bool = False,
    ) -> bool:
        modules = self.behavior_config.get("modules", {})
        value = modules.get(key)

        if value is None:
            return self._env_enabled(
                env_key,
                default,
            )

        return bool(value)

    def check_global_safety(self) -> dict:
        # Workers and transport runtimes are long-lived.  The operator's master
        # switch must therefore be observed without recreating this service.
        self.refresh()
        if not self._config_enabled(
            "global_automation_enabled",
            False,
        ):
            from app.services.controlled_autonomy_test_service import (
                ControlledAutonomyTestService,
            )
            controlled = ControlledAutonomyTestService().active_decision()
            if controlled.allowed:
                return controlled.to_dict()
            return self._blocked("global_automation_disabled")

        if not self._config_enabled(
            "global_sends_enabled",
            False,
        ):
            return self._blocked("global_sends_disabled")

        if self._config_enabled(
            "manual_pause_enabled",
            False,
        ):
            return self._blocked("manual_pause_enabled")

        return self._allowed()

    def check_operator_send_safety(self) -> dict:
        """Preserve manual publishing while honoring send/pause safeguards."""
        self.refresh()
        if not self._config_enabled("global_sends_enabled", False):
            return self._blocked("global_sends_disabled")
        if self._config_enabled("manual_pause_enabled", False):
            return self._blocked("manual_pause_enabled")
        return self._allowed()

    def can_send_chat(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "main_chat_enabled",
            "CHAT_AUTOMATION_ENABLED",
            False,
        ):
            return self._blocked("chat_automation_disabled")

        if not self._env_enabled(
            "ENABLE_REALTIME_FANVUE_SEND",
            False,
        ):
            return self._blocked("realtime_fanvue_send_disabled")

        return self._allowed()

    def can_send_monetization(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "ppv_offers_enabled",
            "MONETIZATION_AUTOMATION_ENABLED",
            False,
        ):
            return self._blocked("ppv_offers_disabled")

        return self._allowed()

    def can_send_mass_ppv(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "mass_ppv_enabled",
            "MASS_PPV_AUTOMATION_ENABLED",
            False,
        ):
            return self._blocked("mass_ppv_disabled")

        if not self._env_enabled(
            "ENABLE_MASS_PPV_SENDS",
            False,
        ):
            return self._blocked("mass_ppv_sends_disabled")

        return self._allowed()

    def can_send_post_purchase_reaction(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "post_purchase_reactions_enabled",
            "POST_PURCHASE_REACTIONS_ENABLED",
            False,
        ):
            return self._blocked("post_purchase_reactions_disabled")

        if not self._env_enabled(
            "ENABLE_REALTIME_MONETIZATION_REACTIONS",
            False,
        ):
            return self._blocked(
                "realtime_monetization_reactions_disabled"
            )

        if not self._env_enabled(
            "ENABLE_POST_PURCHASE_AUTOMATION",
            False,
        ):
            return self._blocked("post_purchase_automation_disabled")

        return self._allowed()

    def can_send_delayed_followup(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "delayed_followups_enabled",
            "DELAYED_FOLLOWUPS_ENABLED",
            False,
        ):
            return self._blocked("delayed_followups_disabled")

        return self._allowed()

    def can_send_outreach(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "outreach_enabled",
            "OUTREACH_AUTOMATION_ENABLED",
            False,
        ):
            return self._blocked("outreach_disabled")

        return self._allowed()

    def can_send_reactivation(self) -> dict:
        global_check = self.check_global_safety()

        if not global_check["allowed"]:
            return global_check

        if not self._module_enabled(
            "reactivation_enabled",
            "REACTIVATION_AUTOMATION_ENABLED",
            False,
        ):
            return self._blocked("reactivation_disabled")

        return self._allowed()

    def _allowed(self) -> dict:
        return {
            "allowed": True,
            "blocked": False,
            "reason": None,
            "source": "dashboard_config",
        }

    def _blocked(self, reason: str) -> dict:
        return {
            "allowed": False,
            "blocked": True,
            "reason": reason,
            "source": "dashboard_config",
        }
