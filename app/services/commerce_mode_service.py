"""Persisted CommerceMode configuration and relationship-mode policy."""

from pathlib import Path

from app.dashboard.config import load_dashboard_config, save_behavior_config
from app.models.commerce_mode import CommerceMode


class CommerceModeService:
    CONFIG_PATH = Path("data/config/behavior_config.json")

    def __init__(self, *, config_loader=load_dashboard_config, config_saver=save_behavior_config):
        self.config_loader = config_loader
        self.config_saver = config_saver

    def get_mode(self) -> CommerceMode:
        config, _ = self.config_loader()
        try:
            return CommerceMode(str(config.get("commerce_mode") or "LIVE").upper())
        except ValueError:
            return CommerceMode.LIVE

    def set_mode(self, value) -> CommerceMode:
        try:
            mode = value if isinstance(value, CommerceMode) else CommerceMode(str(value).upper())
        except ValueError as error:
            raise ValueError("Commerce mode must be OFF, RELATIONSHIP, or LIVE.") from error
        config, _ = self.config_loader()
        config["commerce_mode"] = mode.value
        self.config_saver(config)
        return mode

    @staticmethod
    def description(mode: CommerceMode) -> str:
        return {
            CommerceMode.OFF: "Commerce evaluation and execution are disabled.",
            CommerceMode.RELATIONSHIP: "Conversation continues. Commerce disabled.",
            CommerceMode.LIVE: "Commerce evaluation and authorized execution are enabled.",
        }[mode]
