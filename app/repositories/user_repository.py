from app.database import get_db_connection


def get_user_by_account_and_fanvue_uuid(fanvue_account_id: int, fanvue_user_uuid: str):
    query = """
        SELECT *
        FROM fanvue_users
        WHERE fanvue_account_id = %s
          AND fanvue_user_uuid = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, fanvue_user_uuid))
            return cur.fetchone()


def create_user(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
    username: str = None,
    display_name: str = None,
    relationship_status: str = "unknown",
    is_subscriber: bool = False,
    is_follower: bool = False,
    source: str = "system",
):
    query = """
        INSERT INTO fanvue_users (
            fanvue_account_id,
            fanvue_user_uuid,
            username,
            display_name,
            relationship_status,
            is_subscriber,
            is_follower,
            source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    fanvue_user_uuid,
                    username,
                    display_name,
                    relationship_status,
                    is_subscriber,
                    is_follower,
                    source,
                ),
            )
            return cur.fetchone()


def create_user_memory(fanvue_account_id: int, fanvue_user_id: int):
    query = """
        INSERT INTO user_memory (
            fanvue_account_id,
            fanvue_user_id
        )
        VALUES (%s, %s)
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, fanvue_user_id))
            return cur.fetchone()


def get_user_memory(fanvue_account_id: int, fanvue_user_id: int):
    query = """
        SELECT *
        FROM user_memory
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    str(fanvue_user_id),
                ),
            )
            return cur.fetchone()

def get_user_by_id(fanvue_user_id: int):
    query = """
        SELECT *
        FROM fanvue_users
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_user_id,))
            return cur.fetchone()

def get_or_create_user_with_memory(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
    username: str = None,
    display_name: str = None,
    relationship_status: str = "unknown",
    is_subscriber: bool = False,
    is_follower: bool = False,
    source: str = "system",
):
    user = get_user_by_account_and_fanvue_uuid(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_uuid=fanvue_user_uuid,
    )

    if not user:
        user = create_user(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_uuid=fanvue_user_uuid,
            username=username,
            display_name=display_name,
            relationship_status=relationship_status,
            is_subscriber=is_subscriber,
            is_follower=is_follower,
            source=source,
        )
        memory = create_user_memory(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=user["id"],
        )
    else:
        memory = get_user_memory(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=user["id"],
        )
        if not memory:
            memory = create_user_memory(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=user["id"],
            )

    return {
        "user": user,
        "memory": memory,
    }

def get_outreach_candidate_rows(
    fanvue_account_id: int,
    limit: int = 100,
):
    query = """
        SELECT
            u.id AS fanvue_user_id,
            u.fanvue_user_uuid,
            u.username,
            u.display_name,
            u.relationship_status,
            u.is_subscriber,
            u.is_follower,

            m.*

        FROM fanvue_users u
        INNER JOIN user_memory m
            ON u.id::text = m.fanvue_user_id
           AND u.fanvue_account_id = m.fanvue_account_id

        WHERE u.fanvue_account_id = %s
          AND u.id = 4
        ORDER BY m.updated_at ASC NULLS FIRST
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, limit))
            return cur.fetchall()

def upsert_fan_relationship(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
    username: str = None,
    display_name: str = None,
    relationship_status: str = "unknown",
    is_subscriber: bool = False,
    is_follower: bool = False,
    source: str = "fanvue_api_sync",
):
    query = """
        INSERT INTO fanvue_users (
            fanvue_account_id,
            fanvue_user_uuid,
            username,
            display_name,
            relationship_status,
            is_subscriber,
            is_follower,
            source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fanvue_account_id, fanvue_user_uuid)
        DO UPDATE SET
            username = EXCLUDED.username,
            display_name = EXCLUDED.display_name,
            relationship_status = EXCLUDED.relationship_status,
            is_subscriber = EXCLUDED.is_subscriber,
            is_follower = EXCLUDED.is_follower,
            source = EXCLUDED.source
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    fanvue_user_uuid,
                    username,
                    display_name,
                    relationship_status,
                    is_subscriber,
                    is_follower,
                    source,
                ),
            )
            return cur.fetchone()

def get_user_by_account_and_id(fanvue_account_id: int, fanvue_user_id: int):
    query = """
        SELECT *
        FROM fanvue_users
        WHERE fanvue_account_id = %s
          AND id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, fanvue_user_id))
            return cur.fetchone()