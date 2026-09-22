"""Canonical read model and fail-closed transition coordinator for AVA BOT."""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any, Callable

from app.dashboard.config import load_dashboard_config, save_behavior_config
from app.models.commerce_mode import CommerceMode
from app.models.runtime_control import RuntimeMode
from app.services.commerce_mode_service import CommerceModeService
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
from app.services.global_selling_permissions_service import GlobalSellingPermissionsService
from app.services.runtime_control_service import RuntimeControlService


logger = logging.getLogger("ava-bot-control")
_TRANSITION_LOCK = Lock()


class AvaBotControlService:
    """Coordinate existing authorities without introducing another master flag."""

    def __init__(self, *, runtime_service: Any | None = None,
                 commerce_mode_service: Any | None = None,
                 controlled_autonomy_service: Any | None = None,
                 config_loader: Callable = load_dashboard_config,
                 config_saver: Callable = save_behavior_config,
                 worker_readiness: Callable[[str | int], dict[str, Any]] | None = None,
                 display_worker_readiness: Callable[[str | int], dict[str, Any]] | None = None,
                 transport_readiness: Callable[[], dict[str, Any]] | None = None) -> None:
        self.runtime = runtime_service or RuntimeControlService()
        self.commerce = commerce_mode_service or CommerceModeService(
            config_loader=config_loader, config_saver=config_saver)
        self.controlled = controlled_autonomy_service or ControlledAutonomyTestService()
        self.config_loader = config_loader
        self.config_saver = config_saver
        self.worker_readiness = worker_readiness or self._default_worker_readiness
        self.display_worker_readiness = (
            display_worker_readiness or self._default_display_worker_readiness
        )
        self.transport_readiness = transport_readiness or self._default_transport_readiness
        self.selling = GlobalSellingPermissionsService(
            config_loader=config_loader, config_saver=config_saver)

    def read(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        config, _ = self.config_loader()
        desired = bool(config.get("global_automation_enabled", False))
        diagnostics = self._prerequisites(creator_profile_id, config=config)
        failures = [item for item in diagnostics if not item["ready"]]
        effective = "OFF" if not desired else "ATTENTION" if failures else "ON"
        reason = (
            "Ava Bot is off."
            if not desired else failures[0]["operatorReason"] if failures else None
        )
        return {
            "avaBot": {
                "desired": "ON" if desired else "OFF",
                "effective": effective,
                "reason": reason,
                "diagnostics": diagnostics,
            },
            **self.selling.read(),
            "compatibility": {
                "mainChatEnabled": bool((config.get("modules") or {}).get("main_chat_enabled", False)),
                "ppvOffersEnabled": bool((config.get("modules") or {}).get("ppv_offers_enabled", False)),
                "role": "compatibility_prerequisites_not_effective_authorities",
            },
        }

    def read_display(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        """Return a non-authoritative badge projection without singleton enumeration."""
        config, _ = self.config_loader()
        desired = bool(config.get("global_automation_enabled", False))
        diagnostics = self._prerequisites(
            creator_profile_id, config=config,
            worker_reader=self.display_worker_readiness,
        )
        failures = [item for item in diagnostics if not item["ready"]]
        effective = "OFF" if not desired else "ATTENTION" if failures else "ON"
        return {
            "avaBot": {
                "desired": "ON" if desired else "OFF",
                "effective": effective,
                "reason": (
                    "Ava Bot is off." if not desired
                    else failures[0]["operatorReason"] if failures else None
                ),
                "diagnostics": diagnostics,
                "displayOnly": True,
            },
            **self.selling.read(),
            "displayAuthority": "NON_AUTHORIZING_FRESH_RUNTIME_EVIDENCE",
        }

    def turn_on(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        if not _TRANSITION_LOCK.acquire(blocking=False):
            raise RuntimeError("ava_bot_transition_in_progress")
        previous = self.read(creator_profile_id=creator_profile_id)
        automation_enabled = False
        try:
            config, _ = self.config_loader()
            blockers = self._hard_preparation_blockers(creator_profile_id, config)
            if blockers:
                return self._transition_result("TURN_ON", previous, self.read(
                    creator_profile_id=creator_profile_id), False, blockers[0]["code"])

            # Compatibility preparation is intentionally performed while the
            # canonical automation authority is still false.
            config["global_automation_enabled"] = False
            modules = config.setdefault("modules", {})
            modules["main_chat_enabled"] = True
            modules["ppv_offers_enabled"] = True
            self.config_saver(config)
            self.commerce.set_mode(CommerceMode.LIVE)
            self.runtime.start(creator_profile_id=creator_profile_id)

            config, _ = self.config_loader()
            before_enable = self._prerequisites(
                creator_profile_id, config=config, ignore_automation=True)
            failures = [item for item in before_enable if not item["ready"]]
            if failures:
                return self._transition_result("TURN_ON", previous, self.read(
                    creator_profile_id=creator_profile_id), False, failures[0]["code"])

            config["global_automation_enabled"] = True
            self.config_saver(config)
            automation_enabled = True
            current = self.read(creator_profile_id=creator_profile_id)
            if current["avaBot"]["effective"] != "ON":
                config, _ = self.config_loader()
                config["global_automation_enabled"] = False
                self.config_saver(config)
                automation_enabled = False
                return self._transition_result(
                    "TURN_ON", previous, self.read(creator_profile_id=creator_profile_id),
                    False, "final_verification_disagreement")
            return self._transition_result("TURN_ON", previous, current, True, None)
        except Exception as error:
            if automation_enabled:
                config, _ = self.config_loader()
                config["global_automation_enabled"] = False
                self.config_saver(config)
            logger.exception("event=ava_bot_turn_on_failed")
            return self._transition_result("TURN_ON", previous, self.read(
                creator_profile_id=creator_profile_id), False, type(error).__name__)
        finally:
            _TRANSITION_LOCK.release()

    def turn_off(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        if not _TRANSITION_LOCK.acquire(blocking=False):
            raise RuntimeError("ava_bot_transition_in_progress")
        try:
            previous = self.read(creator_profile_id=creator_profile_id)
            config, _ = self.config_loader()
            config["global_automation_enabled"] = False
            self.config_saver(config)
            current = self.read(creator_profile_id=creator_profile_id)
            success = current["avaBot"]["desired"] == "OFF"
            return self._transition_result("TURN_OFF", previous, current, success,
                                           None if success else "automation_still_enabled")
        finally:
            _TRANSITION_LOCK.release()

    def set_content_selling(self, value: bool, *, creator_profile_id: str | int) -> dict[str, Any]:
        previous = self.read(creator_profile_id=creator_profile_id)
        self.selling.set_content(value)
        return self._transition_result("SET_CONTENT_SELLING", previous,
            self.read(creator_profile_id=creator_profile_id), True, None)

    def set_session_selling(self, value: bool, *, creator_profile_id: str | int) -> dict[str, Any]:
        previous = self.read(creator_profile_id=creator_profile_id)
        self.selling.set_session(value)
        return self._transition_result("SET_SESSION_SELLING", previous,
            self.read(creator_profile_id=creator_profile_id), True, None)

    def _hard_preparation_blockers(self, creator_profile_id, config):
        checks = self._prerequisites(creator_profile_id, config=config,
                                     ignore_automation=True,
                                     ignore_runtime=True, ignore_commerce=True,
                                     ignore_compatibility=True)
        return [item for item in checks if not item["ready"]]

    def _prerequisites(self, creator_profile_id, *, config,
                       ignore_automation=False, ignore_runtime=False,
                       ignore_commerce=False, ignore_compatibility=False,
                       worker_reader=None):
        runtime = self.runtime.get_state(creator_profile_id=creator_profile_id)
        controlled_enabled = self.controlled.configured_identity() is not None
        worker = (worker_reader or self.worker_readiness)(creator_profile_id)
        transport = self.transport_readiness()
        modules = config.get("modules") or {}
        values = [
            ("global_automation_disabled", bool(config.get("global_automation_enabled", False)) or ignore_automation,
             "Global Automation is off."),
            ("global_sends_disabled", bool(config.get("global_sends_enabled", False)), "Global Sends is off."),
            ("manual_pause_enabled", not bool(config.get("manual_pause_enabled", False)), "Manual Emergency Pause is active."),
            ("runtime_not_live", runtime.mode == RuntimeMode.LIVE or ignore_runtime, "Runtime is not LIVE."),
            ("telegram_worker_unhealthy", bool(worker.get("ready")), worker.get("reason") or "Telegram worker is unavailable."),
            ("telegram_transport_unavailable", bool(transport.get("ready")), transport.get("reason") or "Telegram transport is not ready."),
            ("telegram_replies_disabled", _enabled(os.getenv("TELEGRAM_REPLIES_ENABLED")), "Telegram Replies deployment permit is disabled."),
            ("commerce_mode_not_live", self.commerce.get_mode() == CommerceMode.LIVE or ignore_commerce, "Commerce Mode is not LIVE."),
            ("controlled_autonomy_test_enabled", not controlled_enabled, "Controlled-autonomy test mode must be disabled."),
            ("main_chat_compatibility_disabled", bool(modules.get("main_chat_enabled", False)) or ignore_compatibility, "Main Chat compatibility authority is off."),
            ("ppv_compatibility_disabled", bool(modules.get("ppv_offers_enabled", False)) or ignore_compatibility, "PPV compatibility authority is off."),
        ]
        return [{"code": code, "ready": ready, "operatorReason": reason}
                for code, ready, reason in values]

    @staticmethod
    def _default_worker_readiness(creator_profile_id):
        from app.services.telegram_worker_readiness_service import TelegramWorkerReadinessService
        try:
            return TelegramWorkerReadinessService().read(
                creator_profile_id=creator_profile_id)
        except Exception as error:
            logger.warning(
                "event=ava_bot_worker_readiness_unavailable error=%s",
                type(error).__name__,
            )
            return {
                "ready": False,
                "reason": "Worker readiness could not be verified.",
            }

    @staticmethod
    def _default_display_worker_readiness(creator_profile_id):
        from app.services.telegram_worker_readiness_service import TelegramWorkerReadinessService
        try:
            return TelegramWorkerReadinessService().read_display(
                creator_profile_id=creator_profile_id,
            )
        except Exception as error:
            logger.warning(
                "event=ava_bot_display_readiness_unavailable error=%s",
                type(error).__name__,
            )
            return {
                "ready": False,
                "reason": "Worker display status could not be verified.",
            }

    @staticmethod
    def _default_transport_readiness():
        required = ("TG_API_ID", "TG_API_HASH")
        missing = [name for name in required if not str(os.getenv(name) or "").strip()]
        return {"ready": not missing, "reason": None if not missing else
                "Required Telegram transport configuration is unavailable."}

    @staticmethod
    def _transition_result(action, previous, current, success, reason):
        result = {"action": action, "success": success, "reason": reason,
                  "previous": previous, "state": current}
        logger.info("event=global_control_changed action=%s success=%s reason=%s previous=%s current=%s",
                    action, success, reason, previous, current)
        return result


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
