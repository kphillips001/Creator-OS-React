"""Provider-neutral health checks for Creator OS."""

from __future__ import annotations

import importlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterable

from dotenv import load_dotenv

from app.config import BASE_DIR, ENV_PATH, GROK_VISION_MODEL, settings
from app.models.system_health import (
    HealthCheck,
    HealthSection,
    HealthStatus,
    QueueHealth,
    SystemHealthReport,
)
from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.providers.social.x_provider import XPublishingProvider


@dataclass(frozen=True)
class DependencySpec:
    label: str
    module_name: str
    package_name: str
    install_name: str | None = None


class SystemHealthService:
    """Builds read-only health reports without mutating application state."""

    DEPENDENCIES = (
        DependencySpec("OpenAI", "openai", "openai"),
        DependencySpec("Tweepy", "tweepy", "tweepy", "tweepy==4.15.0"),
        DependencySpec("Pillow", "PIL", "Pillow"),
        DependencySpec("Requests", "requests", "requests"),
        DependencySpec("SQLAlchemy", "sqlalchemy", "SQLAlchemy"),
    )

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        environ: dict[str, str] | None = None,
        db_connect: Callable[[], object] | None = None,
    ):
        self.project_root = Path(project_root or BASE_DIR)
        self.environ = environ if environ is not None else os.environ
        self.db_connect = db_connect
        load_dotenv(dotenv_path=ENV_PATH, override=False)

    def build_report(self) -> SystemHealthReport:
        sections = (
            self.runtime_section(),
            self.dependencies_section(),
            self.configuration_section(),
            self.provider_section(),
            self.ai_models_section(),
            self.storage_section(),
            self.database_section(),
        )
        queues = self.queue_health()
        queue_section = HealthSection(
            "Queues",
            tuple(
                HealthCheck(
                    name=item.name,
                    status=item.status,
                    summary=f"{item.count} item(s)",
                    detail=item.detail,
                    value=str(item.count),
                )
                for item in queues
            ),
        )
        sections = (*sections, queue_section)
        warnings = tuple(
            check
            for section in sections
            for check in section.checks
            if check.status in {HealthStatus.WARNING.value, HealthStatus.CRITICAL.value}
        )
        critical_count = sum(1 for check in warnings if check.status == HealthStatus.CRITICAL.value)
        warning_count = sum(1 for check in warnings if check.status == HealthStatus.WARNING.value)
        score = max(0, min(100, 100 - critical_count * 12 - warning_count * 3))
        if critical_count:
            status = HealthStatus.CRITICAL.value
            headline = "Critical Issues Detected"
        elif warning_count:
            status = HealthStatus.WARNING.value
            headline = f"{warning_count} Warning(s)"
        else:
            status = HealthStatus.HEALTHY.value
            headline = "Everything Ready"
        return SystemHealthReport(
            overall_status=status,
            score=score,
            headline=headline,
            sections=sections,
            queues=queues,
            warnings=warnings,
        )

    def runtime_section(self) -> HealthSection:
        return HealthSection(
            "Runtime",
            (
                HealthCheck("Active Python Runtime", HealthStatus.HEALTHY.value, "Detected", value=sys.executable),
                HealthCheck("Python Version", HealthStatus.HEALTHY.value, "Detected", value=platform.python_version()),
                HealthCheck("Operating System", HealthStatus.HEALTHY.value, "Detected", value=platform.platform()),
                HealthCheck(
                    "Creator OS Version",
                    HealthStatus.HEALTHY.value,
                    "Detected",
                    value=self.environ.get("CREATOR_OS_VERSION", "local"),
                ),
                HealthCheck(
                    "Current Runtime Mode",
                    HealthStatus.HEALTHY.value,
                    "Detected",
                    value=self.environ.get("CREATOR_OS_RUNTIME_MODE", "local"),
                ),
            ),
        )

    def dependencies_section(self) -> HealthSection:
        return HealthSection("Dependencies", tuple(self._dependency_check(spec) for spec in self.DEPENDENCIES))

    def configuration_section(self) -> HealthSection:
        checks = (
            self._config_check("OpenAI API", ("OPENAI_API_KEY",)),
            self._config_check("Grok API", ("GROK_API_KEY",)),
            self._config_check("Telegram", ("TELEGRAM_BOT_TOKEN_AVA", "TELEGRAM_CHAT_ID_AVA")),
            self._config_check(
                "X",
                (
                    "X_CONSUMER_KEY",
                    "X_CONSUMER_SECRET",
                    "X_ACCESS_TOKEN",
                    "X_ACCESS_TOKEN_SECRET",
                ),
            ),
            self._config_check("Fanvue", ("FANVUE_API_KEY", "FANVUE_CLIENT_ID", "FANVUE_WEB_COOKIE"), any_one=True),
        )
        return HealthSection("Configuration", checks)

    def provider_section(self) -> HealthSection:
        x_diag = XPublishingProvider.runtime_dependency_diagnostic()
        x_credentials = self._required_present(
            ("X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
        )
        telegram_diag = TelegramPublishingProvider.runtime_dependency_diagnostic(
            {
                "bot_token": self.environ.get("TELEGRAM_BOT_TOKEN_AVA", ""),
                "main_chat_id": self.environ.get("TELEGRAM_CHAT_ID_AVA", "") or self.environ.get("TELEGRAM_CHANNEL_ID", ""),
            }
        )
        return HealthSection(
            "Provider Connectivity",
            (
                HealthCheck(
                    "X Provider",
                    HealthStatus.HEALTHY.value if x_diag.tweepy_installed and x_credentials else HealthStatus.WARNING.value,
                    "Ready" if x_diag.tweepy_installed and x_credentials else "Authentication Required",
                    detail="Dependency installed; credential presence checked locally." if x_diag.tweepy_installed else "tweepy missing.",
                ),
                HealthCheck(
                    "Telegram Provider",
                    HealthStatus.HEALTHY.value if telegram_diag.configured else HealthStatus.WARNING.value,
                    telegram_diag.status,
                    detail=", ".join(telegram_diag.missing),
                ),
                HealthCheck(
                    "Grok",
                    HealthStatus.HEALTHY.value if self._required_present(("GROK_API_KEY",)) else HealthStatus.WARNING.value,
                    "Ready" if self._required_present(("GROK_API_KEY",)) else "Authentication Required",
                ),
                HealthCheck(
                    "Wavespeed",
                    HealthStatus.HEALTHY.value if self._required_present(("WAVESPEED_API_KEY",)) else HealthStatus.WARNING.value,
                    "Ready" if self._required_present(("WAVESPEED_API_KEY",)) else "Authentication Required",
                ),
                HealthCheck(
                    "Fanvue",
                    HealthStatus.HEALTHY.value if self._any_present(("FANVUE_API_KEY", "FANVUE_CLIENT_ID", "FANVUE_WEB_COOKIE")) else HealthStatus.WARNING.value,
                    "Ready" if self._any_present(("FANVUE_API_KEY", "FANVUE_CLIENT_ID", "FANVUE_WEB_COOKIE")) else "Authentication Required",
                ),
            ),
        )

    def ai_models_section(self) -> HealthSection:
        return HealthSection(
            "AI Models",
            (
                HealthCheck("Grok Vision", HealthStatus.HEALTHY.value, "Configured", value=GROK_VISION_MODEL),
                HealthCheck("Seedream 4.5", HealthStatus.HEALTHY.value, "Configured", value=self.environ.get("SEEDREAM_MODEL", "seedream-4.5")),
                HealthCheck("WAN 2.7", HealthStatus.HEALTHY.value, "Configured", value=self.environ.get("WAN_MODEL", "wan-2.7")),
                HealthCheck("Nano Banana", HealthStatus.HEALTHY.value, "Configured", value=self.environ.get("NANO_BANANA_MODEL", "nano-banana")),
            ),
        )

    def storage_section(self) -> HealthSection:
        paths = (
            ("Generation Library", self.project_root / "data" / "generation_library"),
            ("Archive", self.project_root / "data" / "content_archive"),
            ("Logs", self.project_root / "logs"),
            ("Content", Path(getattr(settings, "CONTENT_ROOT", self.project_root / "Content"))),
            ("Database", self.project_root / "data"),
        )
        return HealthSection("Storage", tuple(self._path_check(label, path) for label, path in paths))

    def database_section(self) -> HealthSection:
        url = self.environ.get("DATABASE_URL") or getattr(settings, "DATABASE_URL", "")
        checks = [HealthCheck("Database URL", HealthStatus.HEALTHY.value if url else HealthStatus.CRITICAL.value, "Configured" if url else "Missing")]
        checks.append(self._database_connection_check(url))
        checks.append(self._migration_check())
        checks.append(self._backup_check())
        return HealthSection("Database", tuple(checks))

    def queue_health(self) -> tuple[QueueHealth, ...]:
        return (
            QueueHealth("Publishing Queue", self._json_count(self.project_root / "data" / "social_publishing" / "social_queue.json")),
            QueueHealth("Conversation Queue", self._json_count(self.project_root / "data" / "social_publishing" / "social_publish_items.json")),
            QueueHealth("Photoshoot Queue", self._json_count(self.project_root / "data" / "photoshoot_queue" / "photoshoot_requests.json")),
            QueueHealth("Generation Queue", self._json_count(self.project_root / "data" / "generation_engine" / "generation_jobs.json")),
        )

    def run_quick_test(self, test_name: str) -> HealthCheck:
        normalized = str(test_name or "").strip().lower()
        if normalized == "x":
            diag = XPublishingProvider.runtime_dependency_diagnostic()
            if not diag.tweepy_installed:
                return HealthCheck("Test X", HealthStatus.CRITICAL.value, "Dependency missing", guidance="Install tweepy==4.15.0 in the active runtime.")
            if not self._required_present(("X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")):
                return HealthCheck("Test X", HealthStatus.WARNING.value, "Authentication Required")
            return HealthCheck("Test X", HealthStatus.HEALTHY.value, "Ready")
        if normalized == "telegram":
            return self._quick_config_test("Test Telegram", ("TELEGRAM_BOT_TOKEN_AVA", "TELEGRAM_CHAT_ID_AVA"))
        if normalized == "grok":
            return self._quick_config_test("Test Grok", ("GROK_API_KEY",))
        if normalized == "openai":
            return self._quick_config_test("Test OpenAI", ("OPENAI_API_KEY",))
        if normalized == "database":
            return self._database_connection_check(self.environ.get("DATABASE_URL") or getattr(settings, "DATABASE_URL", ""))
        if normalized == "storage":
            missing = [check for check in self.storage_section().checks if check.status != HealthStatus.HEALTHY.value]
            return HealthCheck("Test Storage", HealthStatus.HEALTHY.value if not missing else HealthStatus.WARNING.value, "Ready" if not missing else f"{len(missing)} path warning(s)")
        return HealthCheck("Quick Test", HealthStatus.UNKNOWN.value, f"Unknown test: {test_name}")

    def _dependency_check(self, spec: DependencySpec) -> HealthCheck:
        try:
            module = importlib.import_module(spec.module_name)
        except Exception:
            install_name = spec.install_name or spec.package_name
            return HealthCheck(
                spec.label,
                HealthStatus.CRITICAL.value,
                "Missing",
                guidance=f"{sys.executable} -m pip install {install_name}",
            )
        version = getattr(module, "__version__", None)
        if not version:
            try:
                version = metadata.version(spec.package_name)
            except metadata.PackageNotFoundError:
                version = "installed"
        return HealthCheck(spec.label, HealthStatus.HEALTHY.value, "Installed", value=str(version))

    def _config_check(self, label: str, keys: Iterable[str], *, any_one: bool = False) -> HealthCheck:
        present = self._any_present(keys) if any_one else self._required_present(keys)
        status = HealthStatus.HEALTHY.value if present else HealthStatus.WARNING.value
        return HealthCheck(label, status, "Configured" if present else "Missing")

    def _quick_config_test(self, label: str, keys: Iterable[str]) -> HealthCheck:
        present = self._required_present(keys)
        return HealthCheck(label, HealthStatus.HEALTHY.value if present else HealthStatus.WARNING.value, "Configured" if present else "Authentication Required")

    def _required_present(self, keys: Iterable[str]) -> bool:
        return all(str(self.environ.get(key, "")).strip() for key in keys)

    def _any_present(self, keys: Iterable[str]) -> bool:
        return any(str(self.environ.get(key, "")).strip() for key in keys)

    def _path_check(self, label: str, path: Path) -> HealthCheck:
        exists = path.exists()
        return HealthCheck(label, HealthStatus.HEALTHY.value if exists else HealthStatus.WARNING.value, "Available" if exists else "Missing", value=str(path))

    def _database_connection_check(self, database_url: str) -> HealthCheck:
        if not database_url:
            return HealthCheck("Database Connection", HealthStatus.CRITICAL.value, "Missing configuration")
        try:
            if self.db_connect is not None:
                connection = self.db_connect()
                close = getattr(connection, "close", None)
                if callable(close):
                    close()
            else:
                from psycopg import connect

                with connect(database_url, connect_timeout=3) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
            return HealthCheck("Database Connection", HealthStatus.HEALTHY.value, "Connected")
        except Exception as exc:
            return HealthCheck("Database Connection", HealthStatus.CRITICAL.value, "Unavailable", detail=str(exc)[:240])

    def _migration_check(self) -> HealthCheck:
        migrations = self.project_root / "migrations" / "forward"
        count = len(tuple(migrations.glob("*.sql"))) if migrations.exists() else 0
        return HealthCheck("Migration Status", HealthStatus.HEALTHY.value if count else HealthStatus.WARNING.value, f"{count} migration file(s)", value=str(count))

    def _backup_check(self) -> HealthCheck:
        backups = tuple(self.project_root.glob("*.dump"))
        if not backups:
            return HealthCheck("Last Backup", HealthStatus.WARNING.value, "No backup found")
        latest = max(backups, key=lambda path: path.stat().st_mtime)
        return HealthCheck("Last Backup", HealthStatus.HEALTHY.value, "Available", value=latest.name)

    @staticmethod
    def _json_count(path: Path) -> int:
        try:
            if not path.exists():
                return 0
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                return len(data)
        except Exception:
            return 0
        return 0
