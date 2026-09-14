from uuid import uuid4

from app.database import get_db_connection
from app.models.ava_availability_session import AvaAvailabilitySession, AvaAvailabilityState


class AvaAvailabilitySessionRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def current_or_transition(self, *, account_scope, now, initial_state,
                              next_state, duration, daypart):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                           ("ava-availability:" + account_scope,))
            cursor.execute("""SELECT * FROM ava_availability_sessions
                WHERE account_scope=%s AND ended_at IS NULL FOR UPDATE""",
                (account_scope,))
            row = cursor.fetchone()
            if row is not None and row["transition_at"] > now:
                return self._model(row)
            previous = None
            if row is not None:
                previous = AvaAvailabilityState(row["state"])
                cursor.execute("""UPDATE ava_availability_sessions
                    SET ended_at=%s,updated_at=NOW() WHERE session_id=%s""",
                    (now, row["session_id"]))
            state = initial_state(now) if previous is None else next_state(previous, now)
            transition_at = duration(state, now)
            cursor.execute("""INSERT INTO ava_availability_sessions(
                session_id,account_scope,state,started_at,transition_at,daypart,
                transition_provenance,transition_reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", (
                uuid4(), account_scope, state.value, now, transition_at,
                daypart(now), "AVA_AVAILABILITY_SESSION_POLICY_V1",
                "INITIAL_STATE" if previous is None else "SESSION_EXPIRED",
            ))
            created = self._model(cursor.fetchone())
            connection.commit()
            return created

    @staticmethod
    def _model(row):
        return AvaAvailabilitySession(
            session_id=row["session_id"], account_scope=row["account_scope"],
            state=AvaAvailabilityState(row["state"]), started_at=row["started_at"],
            transition_at=row["transition_at"], daypart=row["daypart"],
            transition_provenance=row["transition_provenance"],
            transition_reason=row["transition_reason"], ended_at=row.get("ended_at"),
        )
