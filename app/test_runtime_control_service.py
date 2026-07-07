import unittest
from tempfile import TemporaryDirectory

from app.models.runtime_control import RuntimeMode
from app.repositories.runtime_control_repository import RuntimeControlRepository
from app.services.runtime_control_service import RuntimeControlService


class RuntimeControlServiceTests(unittest.TestCase):
    def test_runtime_transitions_work_correctly(self):
        with TemporaryDirectory() as directory:
            service = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )

            live = service.start(creator_profile_id=7)
            observe = service.observe(creator_profile_id=7)
            offline = service.stop(creator_profile_id=7)

            self.assertEqual(live.mode, RuntimeMode.LIVE)
            self.assertEqual(observe.mode, RuntimeMode.OBSERVE)
            self.assertEqual(offline.mode, RuntimeMode.OFFLINE)
            self.assertIsNotNone(live.last_started)
            self.assertIsNotNone(offline.last_stopped)

    def test_runtime_mode_persists_per_creator_profile(self):
        with TemporaryDirectory() as directory:
            repository = RuntimeControlRepository(f"{directory}/runtime.json")
            RuntimeControlService(repository=repository).observe(
                creator_profile_id=42
            )

            recreated = RuntimeControlService(repository=repository)
            snapshot = recreated.build_snapshot(creator_profile_id=42)

            self.assertEqual(snapshot.current_mode, RuntimeMode.OBSERVE)
            self.assertEqual(snapshot.creator_profile_id, "42")

    def test_observe_records_recommendations_but_sends_nothing(self):
        with TemporaryDirectory() as directory:
            service = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            service.observe(creator_profile_id=7)

            observation = service.record_observation(
                creator_profile_id=7,
                customer_id="customer-1",
                conversation_id="conv-1",
                message_text="hello",
                suggested_reply="Suggested reply",
                suggested_offer={"product_id": "product-1"},
                suggested_delivery={"delivery_type": "FREE"},
                suggested_follow_up={"next": "follow_up"},
            )
            snapshot = service.build_snapshot(creator_profile_id=7)

            self.assertEqual(observation.suggested_reply, "Suggested reply")
            self.assertFalse(observation.metadata["sent_to_customer"])
            self.assertFalse(observation.metadata["executed_delivery"])
            self.assertEqual(snapshot.pending_offers, 1)
            self.assertEqual(snapshot.pending_deliveries, 1)
            self.assertEqual(len(snapshot.observed_recommendations), 1)


if __name__ == "__main__":
    unittest.main()
