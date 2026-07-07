from app.database import get_db_connection


def run_test():
    print("\n==============================")
    print("GET CONTENT ITEM IDS")
    print("==============================\n")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, upload_intent, status, file_path, created_at
                FROM content_items
                ORDER BY id DESC
                LIMIT 10;
                """
            )

            rows = cur.fetchall()

            for row in rows:
                print(dict(row))
                print("----------------------")

    print("\nDONE\n")


if __name__ == "__main__":
    run_test()