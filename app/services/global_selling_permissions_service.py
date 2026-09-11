"""Canonical global ceilings for Ava's two commercial selling models."""

from __future__ import annotations

from collections.abc import Callable

from app.dashboard.config import load_dashboard_config, save_behavior_config


class GlobalSellingPermissionsService:
    """Read and persist commercial permissions in the existing behavior config."""

    CONTENT_KEY = "content_selling_enabled"
    SESSION_KEY = "session_selling_enabled"

    def __init__(self, *, config_loader: Callable = load_dashboard_config,
                 config_saver: Callable = save_behavior_config) -> None:
        self.config_loader = config_loader
        self.config_saver = config_saver

    def read(self) -> dict[str, bool]:
        config, _ = self.config_loader()
        return {
            "contentSellingEnabled": bool(config.get(self.CONTENT_KEY, False)),
            "sessionSellingEnabled": bool(config.get(self.SESSION_KEY, False)),
        }

    def content_allowed(self) -> bool:
        return self.read()["contentSellingEnabled"]

    def session_allowed(self) -> bool:
        return self.read()["sessionSellingEnabled"]

    def set_content(self, value: bool) -> dict[str, bool]:
        return self._set(self.CONTENT_KEY, value)

    def set_session(self, value: bool) -> dict[str, bool]:
        return self._set(self.SESSION_KEY, value)

    def _set(self, key: str, value: bool) -> dict[str, bool]:
        if not isinstance(value, bool):
            raise ValueError("Global selling permission must be a boolean.")
        config, _ = self.config_loader()
        config[key] = value
        self.config_saver(config)
        return self.read()
