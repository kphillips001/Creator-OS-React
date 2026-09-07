"""Read-only diagnostic: is the low-cost nurture daily throttle actually live?

The daily budget in CustomerValueAttentionService only engages if the runtime
writes lowCostNurtureActive to this exact JSON path on sent replies:

    response_payload -> diagnostic_metadata -> customer_value_attention
                     -> lowCostNurtureActive

If that path is absent, nurture_response_count_rolling_day is always 0, the
throttle never fires in production, and every unit test still passes because
the tests inject the count directly.

Run from the repo root:   python tools/verify_nurture_throttle.py

Makes no writes. Safe to run against the live database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NURTURE_PATH = "{diagnostic_metadata,customer_value_attention,lowCostNurtureActive}"
SUPPRESSION_PATH = "{diagnostic_metadata,outbound_suppression,reason}"
TIER_PATH = "{diagnostic_metadata,customer_value_attention,attentionTier}"


def fail(message: str) -> None:
    print(f"\n  ERROR: {message}")
    sys.exit(1)


def main() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        fail("python-dotenv not installed. Activate the project venv first.")

    try:
        import psycopg
    except ImportError:
        fail("psycopg not installed. Activate the project venv first.")

    load_dotenv(dotenv_path=REPO_ROOT / ".env", override=True, encoding="utf-8-sig")
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        fail("DATABASE_URL is empty. Check .env at the repo root.")

    print("=" * 68)
    print("  LOW-COST NURTURE THROTTLE - RUNTIME VERIFICATION")
    print("=" * 68)

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.ordinary_chat_reply_operations')"
            )
            if (cursor.fetchone() or [None])[0] is None:
                fail(
                    "Table ordinary_chat_reply_operations does not exist. "
                    "Migrations may not be applied to this database."
                )

            # --- 1. Does the JSON path the counter reads actually exist? ---
            cursor.execute(
                """
                SELECT
                    COUNT(*)                                          AS total_sent,
                    COUNT(*) FILTER (
                        WHERE response_payload #>> %s IS NOT NULL
                    )                                                 AS path_present,
                    COUNT(*) FILTER (
                        WHERE response_payload #>> %s = 'true'
                    )                                                 AS nurture_active,
                    COUNT(*) FILTER (
                        WHERE response_payload #>> %s IS NOT NULL
                          AND sent_confirmed_at >= NOW() - INTERVAL '24 hours'
                    )                                                 AS path_present_24h
                FROM ordinary_chat_reply_operations
                WHERE state = 'SENT_CONFIRMED'
                """,
                (NURTURE_PATH, NURTURE_PATH, NURTURE_PATH),
            )
            total, present, active, present_24h = cursor.fetchone()

            print("\n  [1] JSON path the daily counter reads")
            print(f"      confirmed sends total ......... {total}")
            print(f"      rows carrying the path ........ {present}")
            print(f"      rows with nurture ACTIVE ...... {active}")
            print(f"      rows carrying path (last 24h) . {present_24h}")

            if total == 0:
                verdict_path = "NO DATA - no confirmed sends recorded yet"
            elif present == 0:
                verdict_path = (
                    "BROKEN - path never written. Throttle is DEAD in production "
                    "regardless of green unit tests."
                )
            elif present < total:
                verdict_path = (
                    f"PARTIAL - {total - present} of {total} confirmed sends are "
                    "missing the path. Counter will undercount."
                )
            else:
                verdict_path = "OK - path present on every confirmed send"
            print(f"      => {verdict_path}")

            # --- 2. What does the payload actually look like? ---
            cursor.execute(
                """
                SELECT jsonb_typeof(response_payload #> %s) AS value_type,
                       COUNT(*) AS rows
                FROM ordinary_chat_reply_operations
                WHERE state = 'SENT_CONFIRMED'
                  AND response_payload #> %s IS NOT NULL
                GROUP BY 1
                ORDER BY 2 DESC
                """,
                (NURTURE_PATH, NURTURE_PATH),
            )
            rows = cursor.fetchall()
            print("\n  [2] Stored type of lowCostNurtureActive")
            if not rows:
                print("      (no rows carry the key)")
            for value_type, count in rows:
                flag = "" if value_type == "boolean" else "   <-- NOT a JSON boolean"
                print(f"      {str(value_type):<10} {count:>8} rows{flag}")

            # --- 3. Where does customer_value_attention actually live? ---
            cursor.execute(
                """
                SELECT key, COUNT(*) AS rows
                FROM ordinary_chat_reply_operations,
                     LATERAL jsonb_object_keys(
                         COALESCE(response_payload -> 'diagnostic_metadata', '{}'::jsonb)
                     ) AS key
                WHERE state = 'SENT_CONFIRMED'
                GROUP BY key
                ORDER BY rows DESC
                LIMIT 25
                """
            )
            rows = cursor.fetchall()
            print("\n  [3] Keys actually present under diagnostic_metadata")
            if not rows:
                print("      (diagnostic_metadata is empty or absent on all rows)")
            for key, count in rows:
                marker = "  <-- counter depends on this" if key == "customer_value_attention" else ""
                print(f"      {key:<45} {count:>8}{marker}")

            # --- 4. Has suppression ever actually fired? ---
            cursor.execute(
                """
                SELECT COALESCE(response_payload #>> %s, '(none)') AS reason,
                       COUNT(*) AS rows
                FROM ordinary_chat_reply_operations
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 15
                """,
                (SUPPRESSION_PATH,),
            )
            print("\n  [4] Recorded outbound suppression reasons")
            for reason, count in cursor.fetchall():
                print(f"      {reason:<45} {count:>8}")

            # --- 5. Attention tier distribution ---
            cursor.execute(
                """
                SELECT COALESCE(response_payload #>> %s, '(none)') AS tier,
                       COUNT(*) AS rows
                FROM ordinary_chat_reply_operations
                WHERE state = 'SENT_CONFIRMED'
                GROUP BY 1
                ORDER BY 2 DESC
                """,
                (TIER_PATH,),
            )
            print("\n  [5] Attention tier on confirmed sends")
            for tier, count in cursor.fetchall():
                print(f"      {tier:<45} {count:>8}")

            # --- 6. Live replay of the counter's own query ---
            cursor.execute(
                """
                SELECT telegram_chat_id,
                       inbound_sender_telegram_user_id AS sender,
                       COUNT(*) FILTER (
                           WHERE state = 'SENT_CONFIRMED'
                             AND sent_confirmed_at >= NOW() - INTERVAL '24 hours'
                             AND COALESCE(response_payload #>> %s, 'false') = 'true'
                       ) AS nurture_rolling_day,
                       MAX(sent_confirmed_at) FILTER (
                           WHERE state = 'SENT_CONFIRMED'
                             AND COALESCE(response_payload #>> %s, 'false') = 'true'
                       ) AS last_nurture_at,
                       COUNT(*) AS all_operations
                FROM ordinary_chat_reply_operations
                GROUP BY 1, 2
                ORDER BY all_operations DESC
                LIMIT 10
                """,
                (NURTURE_PATH, NURTURE_PATH),
            )
            print("\n  [6] Counter replayed per conversation (top 10 by volume)")
            print(
                f"      {'chat_id':<16}{'sender':<14}{'nurture/24h':<14}"
                f"{'ops':<7}last_nurture_at"
            )
            for chat_id, sender, rolling, last_at, ops in cursor.fetchall():
                stamp = last_at.isoformat(timespec="seconds") if last_at else "-"
                print(
                    f"      {str(chat_id):<16}{str(sender):<14}"
                    f"{str(rolling):<14}{str(ops):<7}{stamp}"
                )

    print("\n" + "=" * 68)
    print(f"  VERDICT: {verdict_path}")
    print("=" * 68)
    print(
        "\n  Reference: the counter lives in\n"
        "  app/repositories/ordinary_chat_reply_repository.py"
        " -> customer_behavior_evidence\n"
    )


if __name__ == "__main__":
    main()
