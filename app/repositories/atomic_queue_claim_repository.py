"""Shared PostgreSQL lease mechanics for persisted work queues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.database import get_db_connection


@dataclass(frozen=True)
class AtomicQueueClaimRepository:
    table: str
    status_column: str
    pending_status: str
    completed_status: str
    eligible_predicate: str
    order_by: str
    claim_assignments: str = ""
    stale_scope_predicate: str = "TRUE"
    connection_factory: Callable = get_db_connection

    def claim_due_items(
        self,
        *,
        worker_instance_id: str,
        lease_seconds: int,
        limit: int,
        predicate_params: Sequence[Any] = (),
        stale_scope_params: Sequence[Any] = (),
    ) -> list[dict]:
        if not str(worker_instance_id or "").strip():
            raise ValueError("worker_instance_id is required")
        sql = f"""
            WITH candidates AS (
                SELECT id
                FROM {self.table}
                WHERE ({self.eligible_predicate})
                   OR ({self.status_column} = 'processing' AND lease_expires_at < NOW()
                       AND ({self.stale_scope_predicate}))
                ORDER BY {self.order_by}
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE {self.table} AS queue
            SET {self.status_column} = 'processing',
                worker_instance_id = %s,
                claimed_at = NOW(),
                lease_expires_at = NOW() + (%s * INTERVAL '1 second')
                {self.claim_assignments}
            FROM candidates
            WHERE queue.id = candidates.id
            RETURNING queue.*
        """
        params = (*predicate_params, *stale_scope_params, max(1, int(limit)),
                  worker_instance_id, max(1, int(lease_seconds)))
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            conn.commit()
        return [dict(row) for row in rows]

    def renew_claim(self, item_id: int, *, worker_instance_id: str, lease_seconds: int) -> dict:
        return self._owned_update(
            item_id,
            worker_instance_id=worker_instance_id,
            assignments="lease_expires_at = NOW() + (%s * INTERVAL '1 second')",
            params=(max(1, int(lease_seconds)),),
        )

    def release_claim(self, item_id: int, *, worker_instance_id: str) -> dict:
        return self._owned_update(
            item_id,
            worker_instance_id=worker_instance_id,
            assignments=(f"{self.status_column} = %s, worker_instance_id = NULL, "
                         "claimed_at = NULL, lease_expires_at = NULL"),
            params=(self.pending_status,),
        )

    def complete_claim(self, item_id: int, *, worker_instance_id: str, assignments: str = "", params: Sequence[Any] = ()) -> dict:
        suffix = f", {assignments}" if assignments else ""
        return self._owned_update(
            item_id,
            worker_instance_id=worker_instance_id,
            assignments=(f"{self.status_column} = %s, worker_instance_id = NULL, "
                         f"claimed_at = NULL, lease_expires_at = NULL{suffix}"),
            params=(self.completed_status, *params),
        )

    def fail_claim(self, item_id: int, *, worker_instance_id: str, assignments: str, params: Sequence[Any]) -> dict:
        return self._owned_update(
            item_id,
            worker_instance_id=worker_instance_id,
            assignments=(f"{assignments}, worker_instance_id = NULL, claimed_at = NULL, "
                         "lease_expires_at = NULL"),
            params=tuple(params),
        )

    def recover_stale_claims(self, *, limit: int = 100) -> list[dict]:
        sql = f"""
            WITH stale AS (
                SELECT id FROM {self.table}
                WHERE {self.status_column} = 'processing'
                  AND lease_expires_at < NOW()
                ORDER BY lease_expires_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE {self.table} AS queue
            SET {self.status_column} = %s,
                worker_instance_id = NULL,
                claimed_at = NULL,
                lease_expires_at = NULL
            FROM stale
            WHERE queue.id = stale.id
            RETURNING queue.*
        """
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (max(1, int(limit)), self.pending_status))
                rows = cursor.fetchall()
            conn.commit()
        return [dict(row) for row in rows]

    def _owned_update(
        self,
        item_id: int,
        *,
        worker_instance_id: str,
        assignments: str,
        params: Sequence[Any],
    ) -> dict:
        sql = f"""
            UPDATE {self.table}
            SET {assignments}
            WHERE id = %s
              AND {self.status_column} = 'processing'
              AND worker_instance_id = %s
              AND lease_expires_at >= NOW()
            RETURNING *
        """
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (*params, item_id, worker_instance_id))
                row = cursor.fetchone()
            conn.commit()
        return dict(row) if row else {}
