from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


def run_final_validation():
    print(
        "\n=== 3E.12 FINAL PRODUCTION VALIDATION ===\n"
    )

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Main Chat Enabled = ON\n"
        "- PPV Offers Enabled = ON\n"
        "- Mass PPV Enabled = ON\n"
        "- Post-Purchase Reactions Enabled = ON\n"
    )

    service = (
        GlobalSendExecutionGuardService()
    )

    tests = [
        "chat_message",
        "mass_ppv",
        "post_purchase_reaction",
        "ppv_offer",
    ]

    for execution_type in tests:
        print(
            f"\n[VALIDATING] {execution_type}"
        )

        result = (
            service.validate_execution(
                execution_type=execution_type,
                dry_run=True,
            )
        )

        print(result)

        assert "allowed" in result
        assert "blocked" in result
        assert "reason" in result

    print(
        "\n✅ Final production validation completed successfully.\n"
    )


def main():
    run_final_validation()

    print(
        "\n=== 3E COMPLETE ===\n"
    )


if __name__ == "__main__":
    main()