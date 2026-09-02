"""Exact, test-database-only checkpoint and recovery for Session 5 scenarios."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from psycopg import sql


class ScenarioRecoveryService:
    def __init__(self, harness):
        self.harness = harness
        self.bootstrap()

    def bootstrap(self):
        with self.harness.connection() as c:
            c.execute("ALTER TABLE certification_scenario_runs ADD COLUMN IF NOT EXISTS scenario_attempt INTEGER NOT NULL DEFAULT 1")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_checkpoints(
              checkpoint_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,scenario_attempt INTEGER NOT NULL,
              logical_turn INTEGER NOT NULL,turn_attempt INTEGER NOT NULL,checkpoint_type TEXT NOT NULL,
              schema_name TEXT NOT NULL UNIQUE,state JSONB NOT NULL,sequences JSONB NOT NULL,
              status TEXT NOT NULL DEFAULT 'VALID',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_turn_attempts(
              attempt_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,scenario_attempt INTEGER NOT NULL,
              logical_turn INTEGER NOT NULL,turn_attempt INTEGER NOT NULL,status TEXT NOT NULL,
              checkpoint_id UUID NOT NULL,inbound TEXT NOT NULL,outbound TEXT NOT NULL,
              full_analysis JSONB NOT NULL,final_state JSONB NOT NULL,reason TEXT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),superseded_at TIMESTAMPTZ NULL,
              UNIQUE(scenario_id,scenario_attempt,logical_turn,turn_attempt))""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_attempts(
              attempt_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,scenario_attempt INTEGER NOT NULL,
              status TEXT NOT NULL,evidence JSONB NOT NULL,reason TEXT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),ended_at TIMESTAMPTZ NOT NULL,
              UNIQUE(scenario_id,scenario_attempt))""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_execution_leases(
              scenario_id TEXT NOT NULL,scenario_attempt INTEGER NOT NULL,
              owner_id UUID NOT NULL,execution_state TEXT NOT NULL,
              requested_start_turn INTEGER NOT NULL,requested_end_turn INTEGER NOT NULL,
              started_at TIMESTAMPTZ NOT NULL,heartbeat_at TIMESTAMPTZ NOT NULL,
              lease_expires_at TIMESTAMPTZ NOT NULL,completed_at TIMESTAMPTZ NULL,
              failure_reason TEXT NULL,
              PRIMARY KEY(scenario_id,scenario_attempt))""")

    def claim_execution(self, scenario_id: str, scenario_attempt: int, *,
                        requested_start_turn: int, requested_end_turn: int,
                        lease_seconds: int = 300) -> str:
        owner_id = uuid4()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=lease_seconds)
        with self.harness.connection() as c:
            row = c.execute("""SELECT * FROM certification_scenario_execution_leases
                WHERE scenario_id=%s AND scenario_attempt=%s FOR UPDATE""",
                (scenario_id, scenario_attempt)).fetchone()
            if row and row["execution_state"] == "ACTIVE":
                stale = row["lease_expires_at"] <= now
                code = "STALE_EXECUTION_REQUIRES_RECOVERY" if stale else "EXECUTION_ALREADY_IN_PROGRESS"
                raise RuntimeError(
                    f"{code}: scenario={scenario_id} attempt={scenario_attempt} "
                    f"owner={row['owner_id']} leaseExpiresAt={row['lease_expires_at']}"
                )
            c.execute("""INSERT INTO certification_scenario_execution_leases(
                scenario_id,scenario_attempt,owner_id,execution_state,
                requested_start_turn,requested_end_turn,started_at,heartbeat_at,
                lease_expires_at,completed_at,failure_reason)
                VALUES (%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,NULL,NULL)
                ON CONFLICT(scenario_id,scenario_attempt) DO UPDATE SET
                owner_id=EXCLUDED.owner_id,execution_state='ACTIVE',
                requested_start_turn=EXCLUDED.requested_start_turn,
                requested_end_turn=EXCLUDED.requested_end_turn,
                started_at=EXCLUDED.started_at,heartbeat_at=EXCLUDED.heartbeat_at,
                lease_expires_at=EXCLUDED.lease_expires_at,
                completed_at=NULL,failure_reason=NULL""", (
                    scenario_id, scenario_attempt, owner_id,
                    requested_start_turn, requested_end_turn, now, now, expires,
                ))
        return str(owner_id)

    def heartbeat_execution(self, scenario_id: str, scenario_attempt: int,
                            owner_id: str, *, lease_seconds: int = 300) -> None:
        now = datetime.now(timezone.utc)
        with self.harness.connection() as c:
            updated = c.execute("""UPDATE certification_scenario_execution_leases
                SET heartbeat_at=%s,lease_expires_at=%s
                WHERE scenario_id=%s AND scenario_attempt=%s AND owner_id=%s
                  AND execution_state='ACTIVE'""", (
                    now, now + timedelta(seconds=lease_seconds), scenario_id,
                    scenario_attempt, owner_id,
                )).rowcount
        if updated != 1:
            raise RuntimeError("SCENARIO_EXECUTION_OWNERSHIP_LOST")

    def release_execution(self, scenario_id: str, scenario_attempt: int,
                          owner_id: str, *, failed: bool = False,
                          reason: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        state = "FAILED" if failed else "COMPLETED"
        with self.harness.connection() as c:
            updated = c.execute("""UPDATE certification_scenario_execution_leases
                SET execution_state=%s,heartbeat_at=%s,lease_expires_at=%s,
                    completed_at=%s,failure_reason=%s
                WHERE scenario_id=%s AND scenario_attempt=%s AND owner_id=%s
                  AND execution_state='ACTIVE'""", (
                    state, now, now, now, reason, scenario_id,
                    scenario_attempt, owner_id,
                )).rowcount
        if updated != 1:
            raise RuntimeError("SCENARIO_EXECUTION_RELEASE_OWNERSHIP_MISMATCH")

    def execution_status(self, scenario_id: str, scenario_attempt: int,
                         canonical_turn_count: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self.harness.connection() as c:
            lease = c.execute("""SELECT * FROM certification_scenario_execution_leases
                WHERE scenario_id=%s AND scenario_attempt=%s""",
                (scenario_id, scenario_attempt)).fetchone()
            completed = c.execute("""SELECT COALESCE(MAX(logical_turn),0) value
                FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s AND status='CURRENT'""",
                (scenario_id, scenario_attempt)).fetchone()["value"]
        completed = int(completed)
        if lease and lease["execution_state"] == "ACTIVE":
            stale = lease["lease_expires_at"] <= now
            state = "FAILED_STALE_OWNER" if stale else "RUNNING_AND_OWNED"
        elif canonical_turn_count and completed >= canonical_turn_count:
            stale = False
            state = "COMPLETED"
        elif lease and lease["execution_state"] == "FAILED":
            stale = False
            state = "FAILED"
        else:
            stale = False
            state = "PARTIAL_BUT_STOPPED"
        return {
            "state": state,
            "scenarioAttempt": scenario_attempt,
            "ownerId": str(lease["owner_id"]) if lease else None,
            "executionState": lease["execution_state"] if lease else None,
            "requestedStartTurn": int(lease["requested_start_turn"]) if lease else None,
            "requestedEndTurn": int(lease["requested_end_turn"]) if lease else None,
            "lastCompletedLogicalTurn": completed,
            "heartbeatAt": lease["heartbeat_at"] if lease else None,
            "leaseExpiresAt": lease["lease_expires_at"] if lease else None,
            "startedAt": lease["started_at"] if lease else None,
            "completedAt": lease["completed_at"] if lease else None,
            "failureReason": lease["failure_reason"] if lease else None,
            "stale": stale,
            "continuationPermitted": state == "PARTIAL_BUT_STOPPED",
        }

    def recover_stale_execution(self, scenario_id: str, scenario_attempt: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self.harness.connection() as c:
            lease = c.execute("""SELECT * FROM certification_scenario_execution_leases
                WHERE scenario_id=%s AND scenario_attempt=%s FOR UPDATE""",
                (scenario_id, scenario_attempt)).fetchone()
            if not lease or lease["execution_state"] != "ACTIVE":
                raise RuntimeError("NO_ACTIVE_EXECUTION_TO_RECOVER")
            if lease["lease_expires_at"] > now:
                raise RuntimeError("EXECUTION_LEASE_NOT_STALE")
            dangling = c.execute("""SELECT checkpoint.* FROM certification_scenario_checkpoints checkpoint
                LEFT JOIN certification_scenario_turn_attempts attempt
                  ON attempt.checkpoint_id=checkpoint.checkpoint_id
                WHERE checkpoint.scenario_id=%s AND checkpoint.scenario_attempt=%s
                  AND attempt.attempt_id IS NULL
                ORDER BY checkpoint.logical_turn DESC LIMIT 1""",
                (scenario_id, scenario_attempt)).fetchone()
        restored_turn = None
        if dangling:
            self.restore(dangling)
            restored_turn = int(dangling["logical_turn"])
        with self.harness.connection() as c:
            c.execute("""UPDATE certification_scenario_execution_leases
                SET execution_state='FAILED',completed_at=%s,heartbeat_at=%s,
                    lease_expires_at=%s,failure_reason='STALE_OWNER_RECOVERED'
                WHERE scenario_id=%s AND scenario_attempt=%s""",
                (now, now, now, scenario_id, scenario_attempt))
        return {"state": "STALE_OWNER_RECOVERED",
                "restoredPreTurn": restored_turn,
                "continuationPermitted": True}

    def scenario_attempt(self, scenario_id: str) -> int:
        with self.harness.connection() as c:
            value = c.execute("SELECT scenario_attempt FROM certification_scenario_runs WHERE scenario_id=%s",
                              (scenario_id,)).fetchone()
        return int(value["scenario_attempt"] if value else 1)

    def start_attempt(self, scenario_id: str) -> int:
        with self.harness.connection() as c:
            value = c.execute("""SELECT GREATEST(
                COALESCE((SELECT MAX(scenario_attempt) FROM certification_scenario_attempts WHERE scenario_id=%s),0),
                COALESCE((SELECT MAX(scenario_attempt) FROM certification_scenario_turn_attempts WHERE scenario_id=%s),0),
                COALESCE((SELECT MAX(scenario_attempt) FROM certification_scenario_execution_leases WHERE scenario_id=%s),0)
            )+1 AS value""", (scenario_id, scenario_id, scenario_id)).fetchone()
            attempt = int(value["value"])
            c.execute("UPDATE certification_scenario_runs SET scenario_attempt=%s WHERE scenario_id=%s",
                      (attempt, scenario_id))
        return attempt

    def next_logical_turn(self, scenario_id: str, scenario_attempt: int) -> int:
        """Allocate from the immutable attempt ledger, never behavior projections."""
        with self.harness.connection() as c:
            row = c.execute("""SELECT COALESCE(MAX(logical_turn),0)+1 AS value
                FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s AND status='CURRENT'""", (
                    scenario_id, scenario_attempt,
                )).fetchone()
        return int(row["value"])

    def current_outbound_transcript(self, scenario_id: str,
                                    scenario_attempt: int) -> list[str]:
        with self.harness.connection() as c:
            rows = c.execute("""SELECT outbound
                FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s AND status='CURRENT'
                ORDER BY logical_turn""", (scenario_id, scenario_attempt)).fetchall()
        return [str(row["outbound"] or "") for row in rows]

    def checkpoint(self, scenario_id: str, scenario_attempt: int,
                   logical_turn: int, turn_attempt: int, state: dict[str, Any]):
        checkpoint_id = uuid4()
        schema_name = f"cert_cp_{checkpoint_id.hex}"
        with self.harness.connection() as c:
            tables = [row["tablename"] for row in c.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            ).fetchall()]
            sequences = {row["sequencename"]: row["last_value"] for row in c.execute(
                "SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public'"
            ).fetchall()}
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
            for table in tables:
                target = sql.Identifier(schema_name, table)
                source = sql.Identifier("public", table)
                c.execute(sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(target, source))
                columns = [row["column_name"] for row in c.execute("""SELECT column_name
                    FROM information_schema.columns WHERE table_schema='public' AND table_name=%s
                    AND is_generated='NEVER' ORDER BY ordinal_position""", (table,)).fetchall()]
                names = sql.SQL(",").join(sql.Identifier(name) for name in columns)
                c.execute(sql.SQL("INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE SELECT {} FROM {}").format(
                    target, names, names, source))
            c.execute("""INSERT INTO certification_scenario_checkpoints(checkpoint_id,scenario_id,
                scenario_attempt,logical_turn,turn_attempt,checkpoint_type,schema_name,state,sequences)
                VALUES (%s,%s,%s,%s,%s,'PRE_TURN',%s,%s::jsonb,%s::jsonb)""", (
                checkpoint_id, scenario_id, scenario_attempt, logical_turn, turn_attempt,
                schema_name, json.dumps(state, default=str), json.dumps(sequences, default=str),
            ))
        return {"checkpointId": str(checkpoint_id), "schemaName": schema_name,
                "scenarioAttempt": scenario_attempt, "logicalTurn": logical_turn,
                "turnAttempt": turn_attempt, "state": state}

    def record_turn(self, checkpoint, inbound, outbound, full_analysis, final_state,
                    status="CURRENT", reason=None):
        attempt_id = uuid4()
        with self.harness.connection() as c:
            c.execute("""INSERT INTO certification_scenario_turn_attempts(attempt_id,scenario_id,
                scenario_attempt,logical_turn,turn_attempt,status,checkpoint_id,inbound,outbound,
                full_analysis,final_state,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""", (
                attempt_id, checkpoint["scenarioId"], checkpoint["scenarioAttempt"],
                checkpoint["logicalTurn"], checkpoint["turnAttempt"], status,
                checkpoint["checkpointId"], inbound, outbound,
                json.dumps(full_analysis, default=str), json.dumps(final_state, default=str), reason,
            ))
        return str(attempt_id)

    def latest_current_turn(self, scenario_id: str, scenario_attempt: int):
        with self.harness.connection() as c:
            return c.execute("""SELECT attempt.*,checkpoint.schema_name,checkpoint.state AS checkpoint_state,
                checkpoint.sequences,checkpoint.checkpoint_type,
                checkpoint.created_at AS checkpoint_created_at FROM certification_scenario_turn_attempts attempt
                JOIN certification_scenario_checkpoints checkpoint USING(checkpoint_id)
                WHERE attempt.scenario_id=%s AND attempt.scenario_attempt=%s AND attempt.status='CURRENT'
                ORDER BY attempt.logical_turn DESC,attempt.turn_attempt DESC LIMIT 1""",
                (scenario_id, scenario_attempt)).fetchone()

    def turn_attempt_rows(self, scenario_id: str, scenario_attempt: int):
        with self.harness.connection() as c:
            return c.execute("""SELECT * FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s
                ORDER BY logical_turn,turn_attempt""", (scenario_id, scenario_attempt)).fetchall()

    def preserve_turn_attempt_rows(self, rows, superseded_attempt_id, reason):
        with self.harness.connection() as c:
            for row in rows:
                status = "SUPERSEDED_BY_RETRY" if row["attempt_id"] == superseded_attempt_id else row["status"]
                superseded_at = datetime.now(timezone.utc) if row["attempt_id"] == superseded_attempt_id else row["superseded_at"]
                c.execute("""INSERT INTO certification_scenario_turn_attempts(attempt_id,scenario_id,
                    scenario_attempt,logical_turn,turn_attempt,status,checkpoint_id,inbound,outbound,
                    full_analysis,final_state,reason,created_at,superseded_at) VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                    ON CONFLICT(attempt_id) DO UPDATE SET status=EXCLUDED.status,
                    reason=EXCLUDED.reason,superseded_at=EXCLUDED.superseded_at""", (
                    row["attempt_id"], row["scenario_id"], row["scenario_attempt"],
                    row["logical_turn"], row["turn_attempt"], status, row["checkpoint_id"],
                    row["inbound"], row["outbound"], json.dumps(row["full_analysis"], default=str),
                    json.dumps(row["final_state"], default=str),
                    reason if row["attempt_id"] == superseded_attempt_id else row["reason"],
                    row["created_at"], superseded_at,
                ))

    def preserve_archived_turn_attempt(self, row, *, status: str, reason: str):
        """Preserve a removed duplicate as immutable recovery evidence."""
        with self.harness.connection() as c:
            c.execute("""INSERT INTO certification_scenario_turn_attempts(attempt_id,scenario_id,
                scenario_attempt,logical_turn,turn_attempt,status,checkpoint_id,inbound,outbound,
                full_analysis,final_state,reason,created_at,superseded_at) VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                ON CONFLICT(attempt_id) DO UPDATE SET status=EXCLUDED.status,
                reason=EXCLUDED.reason,superseded_at=EXCLUDED.superseded_at""", (
                row["attempt_id"], row["scenario_id"], row["scenario_attempt"],
                row["logical_turn"], row["turn_attempt"], status, row["checkpoint_id"],
                row["inbound"], row["outbound"], json.dumps(row["full_analysis"], default=str),
                json.dumps(row["final_state"], default=str), reason, row["created_at"],
                datetime.now(timezone.utc),
            ))

    def retry_boundary(self, scenario_id: str, scenario_attempt: int):
        latest = self.latest_current_turn(scenario_id, scenario_attempt)
        if not latest:
            return False, "NO VALID PRE_TURN CHECKPOINT", None
        with self.harness.connection() as c:
            purchase = c.execute("""SELECT 1 FROM certification_simulated_provider_events
                WHERE scenario_id=%s AND created_at >= %s LIMIT 1""",
                (scenario_id, latest["checkpoint_created_at"])).fetchone()
        if purchase:
            return False, "RETRY BLOCKED - SYNTHETIC PURCHASE BOUNDARY", latest
        return True, None, latest

    def restore(self, checkpoint_row, *,
                preserve_tables=("certification_scenario_execution_leases",)):
        schema_name = checkpoint_row["schema_name"]
        with self.harness.connection() as c:
            tables = [row["tablename"] for row in c.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            ).fetchall()]
            archived_tables = {row["tablename"] for row in c.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema_name,)).fetchall()}
            if set(tables) != archived_tables:
                raise RuntimeError("PRE_TURN checkpoint table set no longer matches the test schema.")
            restore_tables = [table for table in tables if table not in preserve_tables]
            c.execute("SET LOCAL session_replication_role = replica")
            c.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.SQL(",").join(
                sql.Identifier("public", table) for table in restore_tables)))
            for table in restore_tables:
                columns = [row["column_name"] for row in c.execute("""SELECT column_name
                    FROM information_schema.columns WHERE table_schema='public' AND table_name=%s
                    AND is_generated='NEVER' ORDER BY ordinal_position""", (table,)).fetchall()]
                names = sql.SQL(",").join(sql.Identifier(name) for name in columns)
                c.execute(sql.SQL("INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE SELECT {} FROM {}").format(
                    sql.Identifier("public", table), names, names, sql.Identifier(schema_name, table)))
            for name, value in dict(checkpoint_row["sequences"] or {}).items():
                if value is not None:
                    c.execute("SELECT setval(%s,%s,true)", (f"public.{name}", int(value)))
        return True

    def preserve_checkpoint_record(self, row):
        with self.harness.connection() as c:
            c.execute("""INSERT INTO certification_scenario_checkpoints(checkpoint_id,scenario_id,
                scenario_attempt,logical_turn,turn_attempt,checkpoint_type,schema_name,state,sequences,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT(checkpoint_id) DO NOTHING""", (
                row["checkpoint_id"], row["scenario_id"], row["scenario_attempt"],
                row["logical_turn"], row["turn_attempt"], row["checkpoint_type"], row["schema_name"],
                json.dumps(row["checkpoint_state"], default=str), json.dumps(row["sequences"], default=str),
                row["checkpoint_created_at"],
            ))

    def attempt_history(self, scenario_id: str, *, scenario_attempt=None):
        attempt = (
            int(scenario_attempt) if scenario_attempt is not None
            else self.scenario_attempt(scenario_id)
        )
        with self.harness.connection() as c:
            attempts = c.execute("""SELECT scenario_attempt,status,reason,ended_at
                FROM certification_scenario_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s
                ORDER BY scenario_attempt""", (scenario_id, attempt)).fetchall()
            turns = c.execute("""SELECT scenario_attempt,logical_turn,turn_attempt,status,inbound,outbound,reason
                FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s
                ORDER BY logical_turn,turn_attempt""", (scenario_id, attempt)).fetchall()
        return {"scenarioAttempts": [dict(row) for row in attempts],
                "turnAttempts": [dict(row) for row in turns]}

    def historical_attempt_history(self, scenario_id: str, *, exclude_attempt=None):
        params = [scenario_id]
        exclusion = ""
        if exclude_attempt is not None:
            exclusion = " AND scenario_attempt<>%s"
            params.append(int(exclude_attempt))
        with self.harness.connection() as c:
            attempts = c.execute(f"""SELECT scenario_attempt,status,reason,ended_at
                FROM certification_scenario_attempts
                WHERE scenario_id=%s{exclusion} ORDER BY scenario_attempt""",
                params).fetchall()
            turns = c.execute(f"""SELECT scenario_attempt,logical_turn,turn_attempt,
                status,inbound,outbound,reason FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s{exclusion}
                ORDER BY scenario_attempt,logical_turn,turn_attempt""",
                params).fetchall()
        return {"scenarioAttempts": [dict(row) for row in attempts],
                "turnAttempts": [dict(row) for row in turns]}

    def archive_scenario_attempt(self, scenario_id, scenario_attempt, evidence, reason):
        with self.harness.connection() as c:
            existing = c.execute("""SELECT attempt_id FROM certification_scenario_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s
                  AND status='ABORTED_FOR_REPAIR' LIMIT 1""", (
                    scenario_id, scenario_attempt,
                )).fetchone()
            if existing is not None:
                return str(existing["attempt_id"])
            attempt_id = uuid4()
            c.execute("""INSERT INTO certification_scenario_attempts(attempt_id,scenario_id,
                scenario_attempt,status,evidence,reason,ended_at) VALUES
                (%s,%s,%s,'ABORTED_FOR_REPAIR',%s::jsonb,%s,%s)""", (
                attempt_id, scenario_id, scenario_attempt, json.dumps(evidence, default=str),
                reason or "Operator requested a clean scenario restart.", datetime.now(timezone.utc),
            ))
            return str(attempt_id)
