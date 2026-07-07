from app.repositories.user_repository import get_outreach_candidate_rows

from app.repositories.memory_repository import (
    mark_outreach_sent,
    mark_outreach_ignored,
    reset_exhausted_outreach_user,
    update_memory_fields,
)

from app.repositories.outreach_log_repository import log_outreach_attempt

from app.services.outreach_service import OutreachService

from app.services.monetization_priority_service import (
    MonetizationPriorityService,
)

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)

from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


class OutreachRunner:
    def __init__(
        self,
        outreach_service: OutreachService | None = None,
    ):
        self.outreach_service = (
            outreach_service or OutreachService()
        )

        self.priority_service = (
            MonetizationPriorityService()
        )

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

        self.execution_guard_service = (
            GlobalSendExecutionGuardService()
        )

    def _should_skip_for_monetization_guard(
        self,
        user_memory: dict,
    ) -> tuple[bool, str]:
        """
        8F Outreach Monetization Guard.

        Outreach must not interrupt users already controlled by
        higher-priority chat / monetization flows.
        """

        if self.priority_service.has_active_offer_or_nudge(
            user_memory
        ):
            return True, "active_offer_or_nudge"

        is_subscriber = bool(
            user_memory.get("is_subscriber")
        )

        relationship_status = (
            user_memory.get("relationship_status") or ""
        ).lower()

        if (
            is_subscriber
            or relationship_status == "subscriber"
        ):
            return True, "subscriber_detected"

        current_route = (
            user_memory.get("current_route") or ""
        ).lower()

        last_route = (
            user_memory.get("last_route") or ""
        ).lower()

        if current_route == "chat" or last_route == "chat":
            return True, "active_chat"

        if user_memory.get("subscriber_rewarm_required"):
            return True, "subscriber_rewarm_required"

        if (
            user_memory.get("last_content_sent_at")
            or user_memory.get("last_ppv_sent_at")
        ):
            return True, "recent_monetization_detected"

        return False, ""

    def get_eligible_outreach_targets(
        self,
        fanvue_account_id: int,
        limit: int = 100,
    ) -> dict:
        candidate_rows = get_outreach_candidate_rows(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

        print("\n--- DEBUG OUTREACH CANDIDATES ---")

        for user in candidate_rows:
            print(
                f"DEBUG USER: "
                f"fanvue_user_id={user.get('fanvue_user_id')} | "
                f"username={user.get('username')} | "
                f"outreach_status={user.get('outreach_status')} | "
                f"last_outreach_at={user.get('last_outreach_at')}"
            )

        print("--- END DEBUG OUTREACH CANDIDATES ---\n")

        eligible = []
        ineligible = []

        for user_memory in candidate_rows:
            skip_for_guard, guard_reason = (
                self._should_skip_for_monetization_guard(
                    user_memory
                )
            )

            if skip_for_guard:
                print(
                    f"[OUTREACH SKIP] monetization_guard "
                    f"user={user_memory.get('fanvue_user_id')} "
                    f"username={user_memory.get('username')} "
                    f"reason={guard_reason} "
                    f"offer_state={user_memory.get('offer_state')} "
                    f"post_offer_nudge_count="
                    f"{user_memory.get('post_offer_nudge_count')} "
                    f"is_subscriber="
                    f"{user_memory.get('is_subscriber')} "
                    f"relationship_status="
                    f"{user_memory.get('relationship_status')}"
                )

                ineligible.append(
                    {
                        **user_memory,
                        "outreach_preview": {
                            "eligible": False,
                            "reason": guard_reason,
                        },
                        "guard_reason": guard_reason,
                    }
                )

                continue

            # 9B. Subscriber Contextual Outreach
            # Subscribers do NOT receive generic outreach.
            # They can receive subscriber-safe contextual outreach only.
            (
                subscriber_contextual_eligible,
                subscriber_contextual_reason,
            ) = (
                self.outreach_service
                .is_user_eligible_for_subscriber_contextual_outreach(
                    user_memory
                )
            )

            if subscriber_contextual_eligible:
                preview = {
                    "eligible": True,
                    "reason": subscriber_contextual_reason,
                    "outreach_mode": "subscriber_contextual",
                    "suggested_opener": (
                        self.outreach_service
                        .generate_subscriber_contextual_opener(
                            user_memory
                        )
                    ),
                }

                print(
                    "[OUTREACH MODE] subscriber_contextual | "
                    f"fanvue_user_id="
                    f"{user_memory.get('fanvue_user_id')} | "
                    f"username={user_memory.get('username')}"
                )

            else:
                preview = (
                    self.outreach_service
                    .build_outreach_preview(
                        user_memory
                    )
                )

                preview["outreach_mode"] = "standard"

            enriched_user = {
                **user_memory,
                "outreach_preview": preview,
            }

            if preview["eligible"]:
                score, reasons = (
                    self.outreach_service
                    .calculate_outreach_priority_score(
                        user_memory
                    )
                )

                enriched_user["outreach_priority_score"] = score
                enriched_user["outreach_priority_reasons"] = reasons

                print(
                    "[OUTREACH PRIORITY] "
                    f"user={user_memory.get('fanvue_user_id')} "
                    f"username={user_memory.get('username')} "
                    f"score={score} "
                    f"reasons={reasons}"
                )

                print(
                    "[OUTREACH TARGET SELECTED] "
                    f"user={user_memory.get('fanvue_user_id')} "
                    f"username={user_memory.get('username')} "
                    f"mode={preview.get('outreach_mode')} "
                    f"score={score}"
                )

                eligible.append(enriched_user)

            else:
                ineligible.append(enriched_user)

        # 9C. Sort eligible users by priority score highest first
        eligible.sort(
            key=lambda u: u.get(
                "outreach_priority_score",
                0,
            ),
            reverse=True,
        )

        return {
            "fanvue_account_id": fanvue_account_id,
            "candidate_count": len(candidate_rows),
            "eligible_count": len(eligible),
            "ineligible_count": len(ineligible),
            "eligible": eligible,
            "ineligible": ineligible,
            "summary": {
                "total": len(candidate_rows),
                "eligible_count": len(eligible),
                "ineligible_count": len(ineligible),
            },
        }

    def run_outreach_cycle(
        self,
        fanvue_account_id: int,
        limit: int = 100,
        dry_run: bool = True,
    ) -> dict:
        print("\n[3E.5 OUTREACH EXECUTION GUARD]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"limit={limit}")
        print(f"dry_run={dry_run}")

        outreach_safety_result = (
            self.global_safety_service
            .can_send_outreach()
        )

        execution_guard_result = (
            self.execution_guard_service
            .validate_execution(
                execution_type="outreach",
                safety_result=outreach_safety_result,
                dry_run=dry_run,
            )
        )

        print("[3E.5 OUTREACH GUARD RESULT]")
        print(execution_guard_result)

        if not execution_guard_result.get("allowed", False):
            return {
                "success": False,
                "status": "blocked",
                "blocked": True,
                "reason": execution_guard_result.get("reason"),
                "expected_result": "outreach_disabled",
                "dry_run": dry_run,
                "execution_guard_result": execution_guard_result,
                "outreach_safety_result": outreach_safety_result,
                "fanvue_account_id": fanvue_account_id,
                "candidate_count": 0,
                "eligible_count": 0,
                "ineligible_count": 0,
                "processed_count": 0,
                "processed": [],
                "skipped": [],
                "summary": {
                    "total": 0,
                    "eligible_count": 0,
                    "ineligible_count": 0,
                    "processed_count": 0,
                    "dry_run": dry_run,
                    "blocked": True,
                    "reason": execution_guard_result.get("reason"),
                },
            }

        target_results = self.get_eligible_outreach_targets(
            fanvue_account_id=fanvue_account_id,
            limit=limit,
        )

        for user in target_results["ineligible"]:
            if user.get("outreach_status") == "sent":
                fanvue_user_id = user.get("fanvue_user_id")

                if fanvue_user_id is not None:
                    print(
                        "[OUTREACH WORKER] "
                        f"Marking user {fanvue_user_id} as ignored"
                    )

                    mark_outreach_ignored(
                        fanvue_account_id=fanvue_account_id,
                        fanvue_user_id=fanvue_user_id,
                    )

        processed = []
        skipped = target_results["ineligible"]

        for user in skipped:
            fanvue_user_id = user.get("fanvue_user_id")
            preview = user.get("outreach_preview", {})
            reason = (
                preview.get("reason") or ""
            ).lower()

            if (
                fanvue_user_id is not None
                and (
                    "max outreach attempts" in reason
                    or "exhausted" in reason
                )
            ):
                reset_result = reset_exhausted_outreach_user(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=fanvue_user_id,
                )

                if reset_result:
                    print(
                        "[OUTREACH WORKER] "
                        f"Reset exhausted user {fanvue_user_id}"
                    )

                else:
                    print(
                        "[OUTREACH WORKER] "
                        f"Exhausted user {fanvue_user_id} "
                        "not ready for reset yet."
                    )

        for user in target_results["eligible"]:
            fanvue_user_id = user.get("fanvue_user_id")
            preview = user.get("outreach_preview", {})
            suggested_opener = preview.get(
                "suggested_opener"
            )

            processed_user = {
                **user,
                "suggested_opener": suggested_opener,
                "memory_updated": False,
                "log_created": False,
                "dry_run": dry_run,
                "execution_guard_result": execution_guard_result,
                "outreach_safety_result": outreach_safety_result,
            }

            if (
                fanvue_user_id is not None
                and suggested_opener
            ):
                log_outreach_attempt(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=fanvue_user_id,
                    opener_text=suggested_opener,
                    campaign_type=preview.get(
                        "outreach_mode",
                        "outreach",
                    ),
                    dry_run=dry_run,
                )

                processed_user["log_created"] = True

            if fanvue_user_id is not None:
                new_value_tier, upgrade_reasons = (
                    self.outreach_service
                    .evaluate_user_value_upgrade(
                        user
                    )
                )

                if new_value_tier:
                    print(
                        "[VALUE TIER UPGRADE] "
                        f"user={fanvue_user_id} "
                        f"username={user.get('username')} "
                        f"old_tier={user.get('user_value_tier')} "
                        f"new_tier={new_value_tier} "
                        f"reasons={upgrade_reasons}"
                    )

                    processed_user["value_tier_upgrade"] = {
                        "old_tier": user.get("user_value_tier"),
                        "new_tier": new_value_tier,
                        "reasons": upgrade_reasons,
                    }

                    if not dry_run:
                        update_memory_fields(
                            fanvue_account_id=fanvue_account_id,
                            fanvue_user_id=fanvue_user_id,
                            fields={
                                "user_value_tier": new_value_tier,
                            },
                        )

            if (
                not dry_run
                and fanvue_user_id is not None
            ):
                mark_outreach_sent(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=fanvue_user_id,
                )

                processed_user["memory_updated"] = True

            processed.append(processed_user)

        return {
            "success": True,
            "status": "complete",
            "blocked": False,
            "reason": execution_guard_result.get("reason"),
            "expected_result": (
                "dry_run_allowed"
                if dry_run
                else "outreach_execution_allowed"
            ),
            "execution_guard_result": execution_guard_result,
            "outreach_safety_result": outreach_safety_result,
            "fanvue_account_id": fanvue_account_id,
            "dry_run": dry_run,
            "candidate_count": target_results["candidate_count"],
            "eligible_count": target_results["eligible_count"],
            "ineligible_count": target_results["ineligible_count"],
            "processed_count": len(processed),
            "processed": processed,
            "skipped": skipped,
            "summary": {
                "total": target_results["candidate_count"],
                "eligible_count": target_results["eligible_count"],
                "ineligible_count": target_results["ineligible_count"],
                "processed_count": len(processed),
                "dry_run": dry_run,
                "blocked": False,
                "reason": execution_guard_result.get("reason"),
            },
        }