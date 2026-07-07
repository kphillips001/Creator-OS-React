from app.services.fanvue_relationship_sync_orchestrator import FanvueRelationshipSyncOrchestrator


def run_test():
    print("\n=== 14N-3A RELATIONSHIP SYNC ORCHESTRATOR TEST ===\n")

    orchestrator = FanvueRelationshipSyncOrchestrator(
        fanvue_account_id=1  # Amanda
    )

    result = orchestrator.sync_current_relationships()

    print("\n========== RESULT ==========")
    print(result)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()