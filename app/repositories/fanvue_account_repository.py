from app.database import get_db_connection
from psycopg.types.json import Json

def get_all_accounts():
    query = """
        SELECT *
        FROM fanvue_accounts
        ORDER BY id ASC;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
 
def get_account_by_id(account_id: int):
    query = """
        SELECT *
        FROM fanvue_accounts
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id,))
            return cur.fetchone()


def get_account_by_username(username: str):
    query = """
        SELECT *
        FROM fanvue_accounts
        WHERE username = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (username,))
            return cur.fetchone()


def create_account(
    account_name: str,
    username: str,
    display_name: str = None,
):
    query = """
        INSERT INTO fanvue_accounts (
            account_name,
            username,
            display_name
        )
        VALUES (%s, %s, %s)
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_name, username, display_name))
            return cur.fetchone()


def get_or_create_account(username: str, display_name: str = None):
    account = get_account_by_username(username)

    if not account:
        account = create_account(
            account_name=username,
            username=username,
            display_name=display_name,
        )

    return account


def save_oauth_tokens_for_account(
    account_id: int,
    token_data: dict,
    fanvue_identity: dict | None = None,
):
    query = """
        UPDATE fanvue_accounts
        SET
            oauth_access_token = %s,
            oauth_refresh_token = %s,
            oauth_expires_at = %s,
            oauth_scope = %s,
            oauth_token_type = %s,
            fanvue_user_uuid = %s,
            fanvue_identity = %s,
            oauth_connected_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
        RETURNING *;
    """

    fanvue_identity = fanvue_identity or {}

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    token_data.get("access_token"),
                    token_data.get("refresh_token"),
                    token_data.get("expires_at"),
                    token_data.get("scope"),
                    token_data.get("token_type"),
                    fanvue_identity.get("uuid"),
                    Json(fanvue_identity),
                    account_id,
                ),
            )
            return cur.fetchone()


def load_oauth_tokens_for_account(account_id: int):
    print("\n==============================")
    print("[LOAD TOKENS FOR ACCOUNT]")
    print(f"account_id={account_id}")
    print("==============================")

    query = """
        SELECT
            oauth_access_token,
            oauth_refresh_token,
            oauth_expires_at,
            oauth_scope,
            oauth_token_type
        FROM fanvue_accounts
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id,))
            row = cur.fetchone()

    print("[DB TOKEN ROW]")
    print(row)

    if not row:
        print("[NO ACCOUNT FOUND]")
        return None

    if not row.get("oauth_access_token"):
        print("[NO ACCESS TOKEN FOUND]")
        return None

    print("[TOKENS LOADED SUCCESSFULLY]")

    return {
        "access_token": row.get("oauth_access_token"),
        "refresh_token": row.get("oauth_refresh_token"),
        "expires_at": row.get("oauth_expires_at"),
        "scope": row.get("oauth_scope"),
        "token_type": row.get("oauth_token_type"),
    }


def update_oauth_tokens_for_account(
    account_id: int,
    token_data: dict,
):
    query = """
        UPDATE fanvue_accounts
        SET
            oauth_access_token = %s,
            oauth_refresh_token = COALESCE(%s, oauth_refresh_token),
            oauth_expires_at = %s,
            oauth_scope = %s,
            oauth_token_type = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    token_data.get("access_token"),
                    token_data.get("refresh_token"),
                    token_data.get("expires_at"),
                    token_data.get("scope"),
                    token_data.get("token_type"),
                    account_id,
                ),
            )
            return cur.fetchone()