import os
from contextlib import contextmanager

from psycopg import connect
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the .env file.")


@contextmanager
def get_db_connection():
    conn = connect(DATABASE_URL, row_factory=dict_row)
    
    # ✅ Force autocommit OFF (we control commits manually)
    conn.autocommit = False

    try:
        yield conn

        # ✅ Explicit commit (guaranteed after successful execution)
        conn.commit()

    except Exception as e:
        # ❌ Rollback on ANY failure
        conn.rollback()
        print(f"[DB ERROR] Rolling back transaction: {e}")
        raise

    finally:
        conn.close()