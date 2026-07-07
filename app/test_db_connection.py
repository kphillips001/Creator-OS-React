from app.database import get_db_connection

def test_connection():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            result = cur.fetchone()
            print("Connected successfully!")
            print(result)

if __name__ == "__main__":
    test_connection()