import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
)
from app.models.system_health import HealthCheck, HealthSection, HealthStatus, SystemHealthReport
from app.services.system_health_service import DependencySpec, SystemHealthService


class SystemHealthTests(unittest.TestCase):
    def make_root(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        for path in (
            root / "data" / "generation_library",
            root / "data" / "content_archive",
            root / "data" / "social_publishing",
            root / "data" / "photoshoot_queue",
            root / "data" / "generation_engine",
            root / "logs",
            root / "migrations" / "forward",
        ):
            path.mkdir(parents=True, exist_ok=True)
        (root / "migrations" / "forward" / "001.sql").write_text("select 1;", encoding="utf-8")
        (root / "backup.dump").write_text("backup", encoding="utf-8")
        (root / "data" / "social_publishing" / "social_queue.json").write_text("[{}, {}]", encoding="utf-8")
        (root / "data" / "generation_engine" / "generation_jobs.json").write_text("[{}]", encoding="utf-8")
        return root

    def healthy_env(self):
        return {
            "DATABASE_URL": "postgresql://health.test/db",
            "OPENAI_API_KEY": "configured",
            "GROK_API_KEY": "configured",
            "TELEGRAM_BOT_TOKEN_AVA": "configured",
            "TELEGRAM_CHAT_ID_AVA": "configured",
            "X_CONSUMER_KEY": "configured",
            "X_CONSUMER_SECRET": "configured",
            "X_ACCESS_TOKEN": "configured",
            "X_ACCESS_TOKEN_SECRET": "configured",
            "FANVUE_API_KEY": "configured",
            "WAVESPEED_API_KEY": "configured",
        }

    def test_runtime_detection_uses_current_interpreter(self):
        service = SystemHealthService(project_root=self.make_root(), environ=self.healthy_env())

        runtime = service.runtime_section()

        self.assertEqual(runtime.checks[0].value, sys.executable)
        self.assertEqual(runtime.checks[0].status, HealthStatus.HEALTHY.value)

    def test_backend_dependencies_exclude_superseded_streamlit_ui(self):
        dependency_names = {spec.label for spec in SystemHealthService.DEPENDENCIES}

        self.assertNotIn("Streamlit", dependency_names)
        self.assertIn("OpenAI", dependency_names)

    def test_dependency_detection_reports_missing_and_guidance(self):
        service = SystemHealthService(project_root=self.make_root(), environ=self.healthy_env())

        with patch("app.services.system_health_service.importlib.import_module", side_effect=ModuleNotFoundError("missing")):
            check = service._dependency_check(DependencySpec("Tweepy", "tweepy", "tweepy", "tweepy==4.15.0"))

        self.assertEqual(check.status, HealthStatus.CRITICAL.value)
        self.assertIn("tweepy==4.15.0", check.guidance)
        self.assertIn(sys.executable, check.guidance)

    def test_configuration_validation_and_provider_aggregation(self):
        root = self.make_root()
        service = SystemHealthService(project_root=root, environ=self.healthy_env())

        configuration = service.configuration_section()
        providers = service.provider_section()

        self.assertTrue(all(check.status == HealthStatus.HEALTHY.value for check in configuration.checks))
        self.assertTrue(any(check.name == "X Provider" for check in providers.checks))

    def test_storage_database_and_queue_validation(self):
        root = self.make_root()
        service = SystemHealthService(
            project_root=root,
            environ=self.healthy_env(),
            db_connect=lambda: SimpleNamespace(close=lambda: None),
        )

        storage = service.storage_section()
        database = service.database_section()
        queues = service.queue_health()

        self.assertFalse((root / "data" / "reference_library").exists())
        self.assertNotIn("Reference Library", {check.name for check in storage.checks})
        self.assertTrue(all(check.status == HealthStatus.HEALTHY.value for check in storage.checks))
        self.assertTrue(any(check.name == "Generation Library" for check in storage.checks))
        self.assertTrue(any(check.name == "Database Connection" and check.status == HealthStatus.HEALTHY.value for check in database.checks))
        self.assertEqual(next(queue.count for queue in queues if queue.name == "Publishing Queue"), 2)
        self.assertEqual(next(queue.count for queue in queues if queue.name == "Generation Queue"), 1)

    def test_dashboard_models_and_report_warnings(self):
        report = SystemHealthReport(
            overall_status=HealthStatus.WARNING.value,
            score=91,
            headline="1 Warning",
            sections=(
                HealthSection(
                    "Dependencies",
                    (HealthCheck("Tweepy", HealthStatus.WARNING.value, "Missing"),),
                ),
            ),
            warnings=(HealthCheck("Tweepy", HealthStatus.WARNING.value, "Missing"),),
        )

        self.assertEqual(report.section("Dependencies").status, HealthStatus.WARNING.value)
        self.assertEqual(report.score, 91)

    def test_navigation_page_and_hq_integration_are_registered(self):
        admin = next(group for group in DASHBOARD_NAVIGATION_GROUPS if group.label == "Administration")
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")
        hq_source = Path("app/dashboard/pages/creator_workspace.py").read_text(encoding="utf-8")
        page_source = Path("app/dashboard/pages/system_health.py").read_text(encoding="utf-8")

        self.assertIn("System Health", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("Administration: System Health", DASHBOARD_PAGE_LABELS.values())
        self.assertIn("System Health", [item.label for item in admin.items])
        self.assertIn("render_system_health", source)
        self.assertIn("_render_system_health_widget", hq_source)
        self.assertIn("Quick Tests", page_source)
        self.assertIn("Provider Connectivity", page_source)


if __name__ == "__main__":
    unittest.main()
