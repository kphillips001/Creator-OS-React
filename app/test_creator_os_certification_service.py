import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.models.creator_os_certification import CreatorOSCertificationStatus
from app.repositories.content_opportunity_repository import ContentOpportunityRepository
from app.services.content_opportunity_service import ContentOpportunityService
from app.services.creator_agent_service import CreatorAgentService
from app.services.creator_os_certification_service import CreatorOSCertificationService


class SnapshotService:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or SimpleNamespace(summary={"ok": True})

    def build_snapshot(self, **kwargs):
        return self.snapshot


class BusinessLearningStub:
    def build_learning_snapshot(self, **kwargs):
        return SimpleNamespace(summary={"learning": True})


class CreatorHQStub:
    def build_dashboard(self, **kwargs):
        return SimpleNamespace(
            content_opportunity_card=SimpleNamespace(waiting_customer_count=1)
        )


class PublishingStub:
    def build_publishing_queue_summary(self):
        return SimpleNamespace(waiting_media_link_count=0)


class RuntimeCompatibilityStub:
    def compatibility(self):
        return {
            "runtime_relationship_validation_active": True,
            "decision_owner": "DecisionEngine",
        }


def build_certification_service(content_opportunity_service):
    return CreatorOSCertificationService(
        creator_workflow_service=SnapshotService(),
        product_business_service=SnapshotService(),
        telegram_business_service=SnapshotService(),
        customer_business_service=SnapshotService(),
        content_opportunity_service=content_opportunity_service,
        business_learning_service=BusinessLearningStub(),
        business_optimization_service=SnapshotService(),
        creator_workspace_service=CreatorHQStub(),
        creator_agent_service=CreatorAgentService(
            content_opportunity_service=content_opportunity_service,
            enable_llm=False,
        ),
        publishing_service=PublishingStub(),
        decision_engine_runtime_boundary=RuntimeCompatibilityStub(),
    )


class CreatorOSCertificationServiceTests(unittest.TestCase):
    def test_certification_passes_when_all_read_models_are_available(self):
        with TemporaryDirectory() as directory:
            content = ContentOpportunityService(
                content_opportunity_repository=ContentOpportunityRepository(
                    f"{directory}/content_opportunities.json"
                )
            )
            report = build_certification_service(content).certify()

            self.assertEqual(report.status, CreatorOSCertificationStatus.PASS)
            self.assertEqual(len(report.sections), 11)
            self.assertFalse(report.missing_items)
            self.assertTrue(report.compatibility["read_only"])

    def test_certification_is_partial_when_content_opportunity_is_not_durable(self):
        report = build_certification_service(ContentOpportunityService()).certify()

        self.assertEqual(report.status, CreatorOSCertificationStatus.PARTIAL)
        self.assertIn(
            "Content Opportunity durable persistence is not enabled.",
            report.missing_items,
        )

    def test_certification_fails_when_required_domains_are_missing(self):
        report = CreatorOSCertificationService().certify()

        self.assertEqual(report.status, CreatorOSCertificationStatus.FAIL)
        self.assertTrue(report.missing_items)
        self.assertIn("CreatorWorkflowService is unavailable.", report.missing_items)


if __name__ == "__main__":
    unittest.main()
