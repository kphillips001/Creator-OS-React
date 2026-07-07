from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class GlobalSendExecutionGuardService:
    """
    3E.4 / 3E.5+

    FINAL outbound execution checkpoint.

    PURPOSE:
    Prevent ANY outbound Fanvue execution unless ALL
    global safety systems approve.

    IMPORTANT:
    Dry-run is safe ONLY AFTER dashboard/module/global safety
    checks pass.

    Protects:
    - live sends
    - PPV sends
    - outreach
    - delayed followups
    - reactions
    - reactivation
    """

    def __init__(self):
        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    def validate_execution(
        self,
        execution_type: str,
        safety_result: dict | None = None,
        content_guard_result: dict | None = None,
        buyer_state_result: dict | None = None,
        dry_run: bool = False,
    ) -> dict:

        print("\n[GLOBAL EXECUTION GUARD]")
        print(f"execution_type={execution_type}")
        print(f"dry_run={dry_run}")

        # =====================================
        # GLOBAL AUTOMATION SAFETY
        # =====================================

        global_result = (
            self.global_safety_service
            .check_global_safety()
        )

        if not global_result["allowed"]:
            result = {
                "allowed": False,
                "blocked": True,
                "reason": global_result.get("reason"),
                "source": "global_safety",
                "execution_type": execution_type,
                "dry_run": dry_run,
            }

            print(result)

            return result

        # =====================================
        # MODULE SAFETY
        # =====================================

        if safety_result and not safety_result.get(
            "allowed",
            False,
        ):
            result = {
                "allowed": False,
                "blocked": True,
                "reason": safety_result.get("reason"),
                "source": "module_safety",
                "execution_type": execution_type,
                "dry_run": dry_run,
            }

            print(result)

            return result

        # =====================================
        # CONTENT GUARD
        # =====================================

        if (
            content_guard_result
            and not content_guard_result.get(
                "allowed",
                False,
            )
        ):
            result = {
                "allowed": False,
                "blocked": True,
                "reason": content_guard_result.get("reason"),
                "source": "content_guard",
                "execution_type": execution_type,
                "dry_run": dry_run,
            }

            print(result)

            return result

        # =====================================
        # BUYER STATE
        # =====================================

        if (
            buyer_state_result
            and buyer_state_result.get(
                "blocked",
                False,
            )
        ):
            result = {
                "allowed": False,
                "blocked": True,
                "reason": buyer_state_result.get(
                    "block_reason"
                ),
                "source": "buyer_state",
                "execution_type": execution_type,
                "dry_run": dry_run,
            }

            print(result)

            return result

        # =====================================
        # DRY RUN ALLOWED ONLY AFTER SAFETY PASS
        # =====================================

        if dry_run:
            result = {
                "allowed": True,
                "blocked": False,
                "reason": "dry_run_allowed",
                "source": "dry_run",
                "execution_type": execution_type,
                "dry_run": dry_run,
            }

            print(result)

            return result

        # =====================================
        # FINAL LIVE EXECUTION PASS
        # =====================================

        result = {
            "allowed": True,
            "blocked": False,
            "reason": "live_execution_allowed",
            "source": "execution_guard",
            "execution_type": execution_type,
            "dry_run": dry_run,
        }

        print(result)

        return result