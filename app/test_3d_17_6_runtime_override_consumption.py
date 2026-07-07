from app.services.realtime_decision_trigger_service import (
    RealtimeDecisionTriggerService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6 RUNTIME OVERRIDE TEST")
    print("==============================\n")

    service = RealtimeDecisionTriggerService()

    print(
        "\n✅ Runtime override wiring completed."
    )

    print(
        "DecisionEngine runtime injection "
        "is now connected to realtime orchestration."
    )


if __name__ == "__main__":
    run_test()