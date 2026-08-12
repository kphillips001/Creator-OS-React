from types import SimpleNamespace

from app.services.explicit_inspiration_background_executor import ExplicitInspirationBackgroundExecutor


class FakeRepository:
    def __init__(self):
        self.transitions = []
        self.leases = []

    def transition(self, operation_id, status, **values):
        self.transitions.append((operation_id, status, values))
        return SimpleNamespace(status=status, **values)

    def renew_lease(self, operation_id, worker_id, **values):
        self.leases.append((operation_id, worker_id, values))
        return True


class FakeOperations:
    def __init__(self):
        self.repository = FakeRepository()
        self.progress_updates = []

    def progress(self, operation_id, **values):
        self.progress_updates.append((operation_id, values))


def operation(**metadata):
    return SimpleNamespace(operation_id="inspiration-1", account_id=7, metadata=metadata)


def test_durable_explicit_inspiration_persists_ordered_both_results_and_waits_for_selection():
    prompts = []
    def generate(prompt):
        prompts.append(prompt)
        count = 3 if "SOFTCORE REQUIREMENTS" in prompt else 2
        tier = "softcore" if "SOFTCORE REQUIREMENTS" in prompt else "hardcore"
        return "\n".join(f"{tier} concept {index}" for index in range(1, count + 1))
    inspiration = SimpleNamespace(
        profile_loader=lambda _: {"id": 42},
        _generate_tier=lambda **values: tuple(
            line for line in generate(("SOFTCORE REQUIREMENTS" if values["tier"] == "softcore" else "HARDCORE REQUIREMENTS")).splitlines()
        ),
    )
    operations = FakeOperations()

    ExplicitInspirationBackgroundExecutor(inspiration=inspiration).execute(
        operation(phase="QUEUED", tierMode="both", requestedCount=5,
                  softcoreCount=3, hardcoreCount=2, requestLabel="Generating 5 ideas"),
        operations, worker_id="worker-1",
    )

    _, status, values = operations.repository.transitions[-1]
    assert status == "WAITING_EXTERNAL"
    assert values["stage"] == "WAITING_SELECTION"
    assert values["metadata"]["phase"] == "WAITING_SELECTION"
    assert values["metadata"]["hardcore"] == ["hardcore concept 1", "hardcore concept 2"]
    assert values["metadata"]["softcore"] == ["softcore concept 1", "softcore concept 2", "softcore concept 3"]
    assert [item["tier"] for item in values["metadata"]["concepts"]] == ["hardcore", "hardcore", "softcore", "softcore", "softcore"]
    assert operations.repository.leases[-1][2]["lease_seconds"] == 86400


def test_durable_explicit_inspiration_preserves_successful_tier_on_partial_failure():
    def generate(**values):
        if values["tier"] == "hardcore":
            raise RuntimeError("Hardcore provider failure")
        return ("softcore one", "softcore two", "softcore three")
    inspiration = SimpleNamespace(profile_loader=lambda _: {"id": 42}, _generate_tier=generate)
    operations = FakeOperations()

    ExplicitInspirationBackgroundExecutor(inspiration=inspiration).execute(
        operation(phase="QUEUED", tierMode="both", requestedCount=5,
                  softcoreCount=3, hardcoreCount=2, requestLabel="Generating 5 ideas"),
        operations, worker_id="worker-1",
    )

    metadata = operations.repository.transitions[-1][2]["metadata"]
    assert metadata["conceptGenerationStatus"] == "PARTIAL"
    assert metadata["softcore"] == ["softcore one", "softcore two", "softcore three"]
    assert metadata["hardcore"] == []
    assert metadata["tierErrors"] == {"hardcore": "Hardcore provider failure"}
