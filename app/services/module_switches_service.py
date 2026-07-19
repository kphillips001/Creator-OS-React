"""Operational projection and mutation boundary for existing module switches."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from app.dashboard.config import load_dashboard_config, save_behavior_config
from app.models.runtime_control import RuntimeMode
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.operations_workspace_service import OperationsWorkspaceService
from app.services.runtime_control_service import RuntimeControlService


class ModuleSwitchesService:
    CONFIG_PATH = Path("data/config/behavior_config.json")
    MODULES = {
        "telegram_replies": ("Messaging", "Telegram Replies", "main_chat_enabled"),
        "telegram_outreach": ("Messaging", "Telegram Outreach", "outreach_enabled"),
        "delayed_messages": ("Messaging", "Delayed Messages", "delayed_followups_enabled"),
        "reactivation": ("Messaging", "Reactivation", "reactivation_enabled"),
        "mass_ppv": ("Sales", "Mass PPV", "mass_ppv_enabled"),
        "purchase_reactions": ("Sales", "Purchase Reactions", "post_purchase_reactions_enabled"),
    }
    INFORMATIONAL = (
        ("automated_reactions", "Sales", "Automated Reactions", "Not Implemented", False),
        ("telegram_wall", "Publishing", "Telegram Wall", "Not Implemented", False),
        ("telegram_chat_delivery", "Publishing", "Telegram Chat Delivery", "Not Implemented", False),
        ("fanvue_publishing", "Publishing", "Fanvue Publishing", "Not Implemented", False),
        ("sales_agent", "AI", "Sales Agent", "Always enabled internally", True),
        ("recommendations", "AI", "Recommendations", "Always enabled internally", True),
        ("learning", "AI", "Learning", "Always enabled internally", True),
        ("pricing_intelligence", "AI", "Pricing Intelligence", "Always enabled internally", True),
    )

    def __init__(self, *, runtime_service: Any | None = None, safety_factory: Callable[[], Any] | None = None,
                 config_loader: Callable = load_dashboard_config, config_saver: Callable = save_behavior_config,
                 operations_service: Any | None = None) -> None:
        self.runtime_service = runtime_service or RuntimeControlService()
        self.safety_factory = safety_factory or GlobalAutomationSafetyService
        self.config_loader = config_loader
        self.config_saver = config_saver
        self.operations_service = operations_service or OperationsWorkspaceService()

    def read(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        config, _ = self.config_loader()
        safety = self.safety_factory()
        runtime = self.runtime_service.get_state(creator_profile_id=creator_profile_id)
        decision = self.runtime_service.evaluate_runtime(creator_profile_id=creator_profile_id)
        workers = self.operations_service.workers(account_id=int(creator_profile_id))
        cards: dict[str, list[dict[str, Any]]] = {name: [] for name in ("Messaging", "Sales", "Publishing", "AI")}
        modules = dict(config.get("modules") or {})
        global_check = safety.check_global_safety()
        for key, (card, label, config_key) in self.MODULES.items():
            configured = bool(modules.get(config_key, False))
            cards[card].append(self._switch(key, label, configured, global_check))
        global_automation = bool(config.get("global_automation_enabled", False))
        for key, card, label, reason, enabled in self.INFORMATIONAL:
            autonomous_surface = key in {"automated_reactions", "telegram_wall", "telegram_chat_delivery", "fanvue_publishing"}
            effective = "ACTIVE" if enabled else "NOT_IMPLEMENTED"
            effective_reason = reason
            if autonomous_surface and not global_automation:
                effective = "BLOCKED"
                effective_reason = "Autonomous Sales & Messaging is OFF"
            cards[card].append({"key": key, "label": label, "configured": enabled, "effective": effective,
                                "reason": effective_reason, "editable": False, "implemented": enabled})
        return {
            "scope": {"creatorProfileId": str(creator_profile_id), "moduleConfiguration": "global_existing_behavior_config"},
            "globalStatus": {
                "globalAutomation": bool(config.get("global_automation_enabled", False)),
                "globalSends": bool(config.get("global_sends_enabled", False)),
                "manualPause": bool(config.get("manual_pause_enabled", False)),
                "runtimeMode": runtime.mode.value,
                "heartbeatSummary": workers["summary"],
                "workerHealthSummary": workers["summary"],
                "effectiveSafety": "ACTIVE" if global_check.get("allowed") else "BLOCKED",
                "reason": global_check.get("reason"),
            },
            "masterControl": {
                "key": "global_automation",
                "label": "Autonomous Sales & Messaging",
                "configured": bool(config.get("global_automation_enabled", False)),
                "effective": "ACTIVE" if global_check.get("allowed") else "BLOCKED",
                "reason": self._global_reason(global_check.get("reason")),
                "lastChanged": self._config_last_changed(),
                "editable": True,
            },
            "runtime": {
                "configuredMode": runtime.mode.value, "effectiveMode": decision.mode.value,
                "status": runtime.status.value, "lastChanged": runtime.updated_at,
                "reason": decision.reason, "editable": True,
            },
            "cards": cards,
            "deploymentReadiness": self._deployment_readiness(),
        }

    def update(self, module: str, value: Any, *, creator_profile_id: str | int) -> dict[str, Any]:
        if module == "global_automation":
            if not isinstance(value, bool):
                raise ValueError("Global automation value must be a boolean.")
            config, _ = self.config_loader()
            config["global_automation_enabled"] = value
            self.config_saver(config)
            return self.read(creator_profile_id=creator_profile_id)
        if module == "runtime":
            try: mode = RuntimeMode(str(value).upper())
            except ValueError: raise ValueError("Runtime mode must be OFFLINE, OBSERVE, or LIVE.") from None
            if mode == RuntimeMode.OFFLINE: self.runtime_service.stop(creator_profile_id=creator_profile_id)
            elif mode == RuntimeMode.OBSERVE: self.runtime_service.observe(creator_profile_id=creator_profile_id)
            else: self.runtime_service.start(creator_profile_id=creator_profile_id)
            return self.read(creator_profile_id=creator_profile_id)
        definition = self.MODULES.get(module)
        if definition is None:
            if any(item[0] == module for item in self.INFORMATIONAL):
                raise ValueError(f"{module} is informational and cannot be changed.")
            raise ValueError(f"Unknown module switch: {module}")
        if not isinstance(value, bool): raise ValueError("Module switch value must be a boolean.")
        config, _ = self.config_loader()
        modules = config.setdefault("modules", {})
        modules[definition[2]] = value
        self.config_saver(config)
        return self.read(creator_profile_id=creator_profile_id)

    @staticmethod
    def _switch(key: str, label: str, configured: bool, result: Mapping[str, Any]) -> dict[str, Any]:
        if result.get("reason") == "global_automation_disabled":
            effective, reason = "BLOCKED", "Autonomous Sales & Messaging is OFF"
        elif not configured:
            effective, reason = "OFF", "configured_off"
        elif result.get("allowed"):
            effective, reason = "ACTIVE", None
        else:
            effective = "BLOCKED"
            reason = ("Autonomous Sales & Messaging is OFF"
                      if result.get("reason") == "global_automation_disabled"
                      else result.get("reason") or "safety_blocked")
        return {"key": key, "label": label, "configured": configured, "effective": effective,
                "reason": reason, "editable": True, "implemented": True}

    @staticmethod
    def _global_reason(reason: Any) -> str | None:
        if reason == "global_automation_disabled":
            return "Autonomous Sales & Messaging is OFF"
        return str(reason) if reason else None

    def _config_last_changed(self) -> str | None:
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(self.CONFIG_PATH.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            return None

    @classmethod
    def _deployment_readiness(cls) -> list[dict[str, Any]]:
        return [
            cls._environment_permit("fanvue_live_replies", "Fanvue Live Replies",
                                    "ENABLE_REALTIME_FANVUE_SEND",
                                    "Final deployment permit for live Fanvue chat sends."),
            cls._environment_permit("mass_ppv_live_transport", "Mass PPV Live Transport",
                                    "ENABLE_MASS_PPV_SENDS",
                                    "Final deployment permit for live Mass PPV transport."),
            cls._environment_permit("reaction_live_execution", "Reaction Live Execution",
                                    "ENABLE_REALTIME_MONETIZATION_REACTIONS",
                                    "Final deployment permit for live monetization reactions."),
            cls._environment_permit("telegram_runtime_readiness", "Telegram Runtime Readiness",
                                    "TELEGRAM_REPLIES_ENABLED",
                                    "Deployment readiness for Telegram reply processing."),
            cls._environment_permit("webhook_processing", "Webhook Processing",
                                    "FANVUE_WEBHOOK_SIGNING_SECRET",
                                    "Fanvue webhook signature verification is configured.", secret=True),
        ]

    @staticmethod
    def _environment_permit(key: str, label: str, variable: str, description: str,
                            *, secret: bool = False) -> dict[str, Any]:
        raw = os.getenv(variable)
        ready = bool(raw) if secret else str(raw or "").strip().lower() in {"1", "true", "yes", "on"}
        current_value = "Configured" if secret and ready else "Missing" if secret else "Enabled" if ready else "Disabled"
        return {"key": key, "label": label, "status": "READY" if ready else "BLOCKED",
                "environmentVariable": variable, "currentValue": current_value, "source": "Environment",
                "restartRequired": True, "description": description, "editable": False}

    @classmethod
    def plain(cls, value: Any) -> Any:
        if is_dataclass(value): return {key: cls.plain(item) for key, item in asdict(value).items()}
        if isinstance(value, Enum): return value.value
        if isinstance(value, Mapping): return {str(key): cls.plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)): return [cls.plain(item) for item in value]
        return value
