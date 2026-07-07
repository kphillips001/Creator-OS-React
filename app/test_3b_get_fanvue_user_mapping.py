from app.database import get_db_connection


def run_test():
    print("\n===================================")
    print(" FANVUE USER UUID MAPPING TEST ")
    print("===================================\n")

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                fanvue_user_uuid,
                fanvue_account_id
            FROM fanvue_users
            ORDER BY id DESC
            LIMIT 10;
        """)

        rows = cur.fetchall()

        if not rows:
            print("❌ No fanvue_users found.")
            return

        for row in rows:
            print(row)

        cur.close()

    print("\n✅ Mapping test complete")
    print("===================================\n")


if __name__ == "__main__":
    run_test()