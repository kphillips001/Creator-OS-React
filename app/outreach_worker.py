import time

from app.services.outreach_runner import OutreachRunner


def run_outreach_worker():
    runner = OutreachRunner()

    print("[OUTREACH WORKER] Started.")

    while True:
        try:
            print("\n[OUTREACH WORKER] Running outreach cycle...\n")

            results = runner.run_outreach_cycle(
                fanvue_account_id=2,
                limit=10,
                dry_run=False,
            )

            print(
                f"[OUTREACH WORKER] Done. "
                f"Candidates={results['candidate_count']} | "
                f"Eligible={results['eligible_count']} | "
                f"Processed={results['processed_count']}"
            )

        except Exception as e:
            print(f"[OUTREACH WORKER] Error: {e}")

        print("[OUTREACH WORKER] Sleeping for 300 seconds...\n")
        time.sleep(300)


if __name__ == "__main__":
    run_outreach_worker()