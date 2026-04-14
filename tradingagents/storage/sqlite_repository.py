from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

_TRADINGAGENTS_HOME = Path.home() / ".tradingagents"
DEFAULT_DB_FILENAME = "tradingagents.sqlite3"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profiles (
    profile_key TEXT PRIMARY KEY,
    source_path TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    analysis_time TEXT NOT NULL,
    status TEXT NOT NULL,
    results_dir TEXT,
    config_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_run_progress (
    run_id INTEGER PRIMARY KEY,
    selected_analysts_json TEXT NOT NULL,
    agent_status_json TEXT NOT NULL,
    report_sections_json TEXT NOT NULL,
    current_agent TEXT,
    current_report TEXT,
    stats_json TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    display_time TEXT,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    display_time TEXT,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_report_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    section_name TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, section_name),
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS full_state_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER UNIQUE,
    asset_symbol TEXT,
    trade_date TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complete_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER UNIQUE,
    asset_symbol TEXT NOT NULL,
    markdown TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reflection_memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_name TEXT NOT NULL,
    situation TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_loops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    status TEXT NOT NULL,
    selections_json TEXT NOT NULL,
    active_run_id INTEGER,
    last_run_id INTEGER,
    last_run_status TEXT,
    last_error TEXT,
    last_started_at TEXT,
    last_completed_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(active_run_id) REFERENCES analysis_runs(id) ON DELETE SET NULL,
    FOREIGN KEY(last_run_id) REFERENCES analysis_runs(id) ON DELETE SET NULL
);
"""


def resolve_db_path(
    db_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    if config and config.get("storage_db_path"):
        return Path(config["storage_db_path"]).expanduser().resolve()
    env_value = os.getenv("TRADINGAGENTS_DB_PATH")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (_TRADINGAGENTS_HOME / DEFAULT_DB_FILENAME).resolve()


class SQLiteRepository:
    def __init__(
        self,
        db_path: str | Path | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.config = config or {}
        self.db_path = resolve_db_path(db_path=db_path, config=config)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_retention_days = self._normalize_positive_int(
            self.config.get("storage_retention_days"),
            default=7,
            minimum=1,
        )
        self.storage_max_runs_per_asset_timeframe = self._normalize_positive_int(
            self.config.get("storage_max_runs_per_asset_timeframe"),
            default=240,
            minimum=1,
        )
        self.storage_max_reflection_entries_per_memory = self._normalize_positive_int(
            self.config.get("storage_max_reflection_entries_per_memory"),
            default=300,
            minimum=1,
        )
        self._init_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _serialize_json(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _deserialize_json(self, payload: str | None, default: Any) -> Any:
        if payload in (None, ""):
            return default
        return json.loads(payload)

    def _normalize_positive_int(
        self,
        value: Any,
        *,
        default: int,
        minimum: int,
    ) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = default
        return max(minimum, normalized)

    def _delete_runs_by_ids(
        self,
        connection: sqlite3.Connection,
        run_ids: list[int],
    ) -> int:
        if not run_ids:
            return 0
        placeholders = ", ".join("?" for _ in run_ids)
        connection.execute(
            f"DELETE FROM analysis_runs WHERE id IN ({placeholders})",
            tuple(run_ids),
        )
        return len(run_ids)

    def _get_active_run_ids(self, connection: sqlite3.Connection) -> set[int]:
        rows = connection.execute(
            """
            SELECT DISTINCT active_run_id
            FROM monitoring_loops
            WHERE active_run_id IS NOT NULL
            """
        ).fetchall()
        return {int(row["active_run_id"]) for row in rows if row["active_run_id"] is not None}

    def _prune_analysis_runs_by_age(self, connection: sqlite3.Connection) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.storage_retention_days)
        cutoff_iso = cutoff.isoformat()
        active_run_ids = self._get_active_run_ids(connection)
        query = """
            SELECT id
            FROM analysis_runs
            WHERE status != 'running'
              AND COALESCE(completed_at, updated_at, created_at) < ?
        """
        params: list[Any] = [cutoff_iso]
        if active_run_ids:
            placeholders = ", ".join("?" for _ in active_run_ids)
            query += f" AND id NOT IN ({placeholders})"
            params.extend(sorted(active_run_ids))
        rows = connection.execute(query, tuple(params)).fetchall()
        return self._delete_runs_by_ids(
            connection,
            [int(row["id"]) for row in rows],
        )

    def _prune_analysis_runs_by_asset_limit(self, connection: sqlite3.Connection) -> int:
        deleted = 0
        active_run_ids = self._get_active_run_ids(connection)
        groups = connection.execute(
            """
            SELECT DISTINCT asset_symbol, timeframe
            FROM analysis_runs
            """
        ).fetchall()
        for group in groups:
            query = """
                SELECT id
                FROM analysis_runs
                WHERE asset_symbol = ?
                  AND timeframe = ?
                  AND status != 'running'
                ORDER BY COALESCE(completed_at, updated_at, created_at) DESC, id DESC
            """
            params: list[Any] = [group["asset_symbol"], group["timeframe"]]
            if active_run_ids:
                placeholders = ", ".join("?" for _ in active_run_ids)
                query = query.replace(
                    "ORDER BY",
                    f"AND id NOT IN ({placeholders}) ORDER BY",
                    1,
                )
                params.extend(sorted(active_run_ids))
            rows = connection.execute(query, tuple(params)).fetchall()
            stale_ids = [
                int(row["id"])
                for row in rows[self.storage_max_runs_per_asset_timeframe :]
            ]
            deleted += self._delete_runs_by_ids(connection, stale_ids)
        return deleted

    def _prune_reflection_memory(self, connection: sqlite3.Connection) -> int:
        deleted = 0
        memory_names = connection.execute(
            """
            SELECT DISTINCT memory_name
            FROM reflection_memory_entries
            """
        ).fetchall()
        for row in memory_names:
            entry_rows = connection.execute(
                """
                SELECT id
                FROM reflection_memory_entries
                WHERE memory_name = ?
                ORDER BY id DESC
                """,
                (row["memory_name"],),
            ).fetchall()
            stale_ids = [
                int(entry["id"])
                for entry in entry_rows[self.storage_max_reflection_entries_per_memory :]
            ]
            if not stale_ids:
                continue
            placeholders = ", ".join("?" for _ in stale_ids)
            connection.execute(
                f"DELETE FROM reflection_memory_entries WHERE id IN ({placeholders})",
                tuple(stale_ids),
            )
            deleted += len(stale_ids)
        return deleted

    def enforce_retention(self) -> dict[str, int]:
        with self._connect() as connection:
            pruned_runs_by_age = self._prune_analysis_runs_by_age(connection)
            pruned_runs_by_limit = self._prune_analysis_runs_by_asset_limit(connection)
            pruned_memory_entries = self._prune_reflection_memory(connection)
        return {
            "pruned_runs_by_age": pruned_runs_by_age,
            "pruned_runs_by_limit": pruned_runs_by_limit,
            "pruned_memory_entries": pruned_memory_entries,
        }

    def upsert_profile(
        self,
        profile_key: str,
        payload: dict[str, Any],
        source_path: str | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profiles (
                    profile_key,
                    source_path,
                    payload_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_key) DO UPDATE SET
                    source_path = excluded.source_path,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_key,
                    source_path,
                    self._serialize_json(payload),
                    now,
                    now,
                ),
            )

    def get_profile(self, profile_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM profiles WHERE profile_key = ?",
                (profile_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def create_analysis_run(
        self,
        asset_symbol: str,
        timeframe: str,
        analysis_time: str,
        results_dir: str | Path | None = None,
        config: dict[str, Any] | None = None,
        status: str = "running",
    ) -> int:
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO analysis_runs (
                    asset_symbol,
                    timeframe,
                    analysis_time,
                    status,
                    results_dir,
                    config_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_symbol,
                    timeframe,
                    analysis_time,
                    status,
                    str(results_dir) if results_dir else None,
                    self._serialize_json(config or {}),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def update_analysis_run_status(self, run_id: int, status: str) -> None:
        now = self._now()
        completed_at = now if status != "running" else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_runs
                SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE id = ?
                """,
                (status, now, completed_at, run_id),
            )
        if status != "running":
            self.enforce_retention()

    def upsert_analysis_progress(
        self,
        run_id: int,
        selected_analysts: list[str],
        agent_status: dict[str, str],
        report_sections: dict[str, Any],
        current_agent: str | None,
        current_report: str | None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_run_progress (
                    run_id,
                    selected_analysts_json,
                    agent_status_json,
                    report_sections_json,
                    current_agent,
                    current_report,
                    stats_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    selected_analysts_json = excluded.selected_analysts_json,
                    agent_status_json = excluded.agent_status_json,
                    report_sections_json = excluded.report_sections_json,
                    current_agent = excluded.current_agent,
                    current_report = excluded.current_report,
                    stats_json = excluded.stats_json,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    self._serialize_json(selected_analysts),
                    self._serialize_json(agent_status),
                    self._serialize_json(report_sections),
                    current_agent,
                    current_report,
                    self._serialize_json(stats or {}),
                    now,
                ),
            )

    def append_message(
        self,
        run_id: int,
        display_time: str | None,
        message_type: str,
        content: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_messages (
                    run_id,
                    display_time,
                    message_type,
                    content,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, display_time, message_type, content, self._now()),
            )

    def append_tool_call(
        self,
        run_id: int,
        display_time: str | None,
        tool_name: str,
        tool_args: Any,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_tool_calls (
                    run_id,
                    display_time,
                    tool_name,
                    tool_args_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    display_time,
                    tool_name,
                    self._serialize_json(tool_args),
                    self._now(),
                ),
            )

    def upsert_report_section(self, run_id: int, section_name: str, content: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_report_sections (
                    run_id,
                    section_name,
                    content,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, section_name) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (run_id, section_name, content, now),
            )

    def save_full_state_log(
        self,
        trade_date: str,
        payload: dict[str, Any],
        run_id: int | None = None,
        asset_symbol: str | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO full_state_logs (
                    run_id,
                    asset_symbol,
                    trade_date,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    asset_symbol = excluded.asset_symbol,
                    trade_date = excluded.trade_date,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    run_id,
                    asset_symbol,
                    str(trade_date),
                    self._serialize_json(payload),
                    now,
                ),
            )

    def save_complete_report(self, run_id: int, asset_symbol: str, markdown: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO complete_reports (
                    run_id,
                    asset_symbol,
                    markdown,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    asset_symbol = excluded.asset_symbol,
                    markdown = excluded.markdown,
                    updated_at = excluded.updated_at
                """,
                (run_id, asset_symbol, markdown, now, now),
            )

    def add_memory_entries(
        self,
        memory_name: str,
        situations_and_advice: Iterable[tuple[str, str]],
    ) -> None:
        rows = [
            (memory_name, situation, recommendation, self._now())
            for situation, recommendation in situations_and_advice
        ]
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO reflection_memory_entries (
                    memory_name,
                    situation,
                    recommendation,
                    created_at
                ) VALUES (?, ?, ?, ?)
                """,
                rows,
            )
        self.enforce_retention()

    def list_memory_entries(self, memory_name: str) -> list[tuple[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT situation, recommendation
                FROM reflection_memory_entries
                WHERE memory_name = ?
                ORDER BY id ASC
                """,
                (memory_name,),
            ).fetchall()
        return [(row["situation"], row["recommendation"]) for row in rows]

    def create_monitoring_loop(
        self,
        *,
        asset_symbol: str,
        timeframe: str,
        interval_minutes: int,
        selections: dict[str, Any],
        status: str = "active",
        next_run_at: str | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO monitoring_loops (
                    asset_symbol,
                    timeframe,
                    interval_minutes,
                    status,
                    selections_json,
                    next_run_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_symbol,
                    timeframe,
                    interval_minutes,
                    status,
                    self._serialize_json(selections),
                    next_run_at,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def count_monitoring_loops(self, *, status: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM monitoring_loops"
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_monitoring_loops(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                loops.*,
                active.asset_symbol AS active_run_asset_symbol,
                active.status AS active_run_status,
                last_run.asset_symbol AS last_run_asset_symbol,
                last_run.status AS last_run_status_live
            FROM monitoring_loops AS loops
            LEFT JOIN analysis_runs AS active
                ON active.id = loops.active_run_id
            LEFT JOIN analysis_runs AS last_run
                ON last_run.id = loops.last_run_id
        """
        params: list[Any] = []
        if status is not None:
            query += " WHERE loops.status = ?"
            params.append(status)
        query += " ORDER BY loops.id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._hydrate_monitoring_loop_row(row) for row in rows]

    def get_monitoring_loop(self, loop_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    loops.*,
                    active.asset_symbol AS active_run_asset_symbol,
                    active.status AS active_run_status,
                    last_run.asset_symbol AS last_run_asset_symbol,
                    last_run.status AS last_run_status_live
                FROM monitoring_loops AS loops
                LEFT JOIN analysis_runs AS active
                    ON active.id = loops.active_run_id
                LEFT JOIN analysis_runs AS last_run
                    ON last_run.id = loops.last_run_id
                WHERE loops.id = ?
                """,
                (loop_id,),
            ).fetchone()
        if row is None:
            return None
        return self._hydrate_monitoring_loop_row(row)

    def get_due_monitoring_loops(self, *, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM monitoring_loops
                WHERE status = 'active'
                  AND active_run_id IS NULL
                  AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY
                    CASE WHEN next_run_at IS NULL THEN 0 ELSE 1 END,
                    next_run_at ASC,
                    id ASC
                LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
        return [self._hydrate_monitoring_loop_row(row) for row in rows]

    def get_monitoring_loop_rankings(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    loops.id,
                    loops.asset_symbol,
                    loops.timeframe,
                    loops.interval_minutes,
                    loops.status,
                    loops.active_run_id,
                    loops.last_run_id,
                    loops.last_run_status,
                    loops.last_error,
                    loops.last_started_at,
                    loops.last_completed_at,
                    loops.next_run_at,
                    loops.updated_at,
                    active.status AS active_run_status,
                    COUNT(runs.id) AS total_runs,
                    COALESCE(SUM(CASE WHEN runs.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_runs,
                    COALESCE(SUM(CASE WHEN runs.status IN ('failed', 'error') THEN 1 ELSE 0 END), 0) AS failed_runs,
                    MAX(COALESCE(runs.completed_at, runs.updated_at, runs.created_at)) AS last_seen_run_at
                FROM monitoring_loops AS loops
                LEFT JOIN analysis_runs AS active
                    ON active.id = loops.active_run_id
                LEFT JOIN analysis_runs AS runs
                    ON runs.asset_symbol = loops.asset_symbol
                   AND runs.timeframe = loops.timeframe
                GROUP BY
                    loops.id,
                    loops.asset_symbol,
                    loops.timeframe,
                    loops.interval_minutes,
                    loops.status,
                    loops.active_run_id,
                    loops.last_run_id,
                    loops.last_run_status,
                    loops.last_error,
                    loops.last_started_at,
                    loops.last_completed_at,
                    loops.next_run_at,
                    loops.updated_at,
                    active.status
                ORDER BY
                    CASE WHEN loops.status = 'active' THEN 0 ELSE 1 END,
                    CASE WHEN loops.active_run_id IS NOT NULL THEN 0 ELSE 1 END,
                    COALESCE(loops.last_completed_at, loops.updated_at) DESC,
                    total_runs DESC,
                    loops.id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        rankings = []
        for index, row in enumerate(rows, start=1):
            rankings.append(
                {
                    "rank": index,
                    "loop_id": int(row["id"]),
                    "asset_symbol": row["asset_symbol"],
                    "timeframe": row["timeframe"],
                    "interval_minutes": int(row["interval_minutes"]),
                    "status": row["status"],
                    "active_run_id": row["active_run_id"],
                    "active_run_status": row["active_run_status"],
                    "last_run_id": row["last_run_id"],
                    "last_run_status": row["last_run_status"],
                    "last_error": row["last_error"],
                    "last_started_at": row["last_started_at"],
                    "last_completed_at": row["last_completed_at"],
                    "next_run_at": row["next_run_at"],
                    "updated_at": row["updated_at"],
                    "total_runs": int(row["total_runs"] or 0),
                    "completed_runs": int(row["completed_runs"] or 0),
                    "failed_runs": int(row["failed_runs"] or 0),
                    "last_seen_run_at": row["last_seen_run_at"],
                }
            )
        return rankings

    def update_monitoring_loop_status(self, loop_id: int, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitoring_loops
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, self._now(), loop_id),
            )

    def delete_monitoring_loop(self, loop_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM monitoring_loops WHERE id = ?",
                (loop_id,),
            )

    def mark_monitoring_loop_run_started(self, loop_id: int, run_id: int) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitoring_loops
                SET active_run_id = ?,
                    last_run_id = ?,
                    last_started_at = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (run_id, run_id, now, now, loop_id),
            )

    def mark_monitoring_loop_run_finished(
        self,
        loop_id: int,
        *,
        run_status: str,
        next_run_at: str | None,
        error: str | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitoring_loops
                SET active_run_id = NULL,
                    last_run_status = ?,
                    last_error = ?,
                    last_completed_at = ?,
                    next_run_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (run_status, error, now, next_run_at, now, loop_id),
            )

    def update_monitoring_loop_error(self, loop_id: int, error: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitoring_loops
                SET last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error, self._now(), loop_id),
            )

    def set_monitoring_loop_next_run(self, loop_id: int, next_run_at: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitoring_loops
                SET next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_run_at, self._now(), loop_id),
            )

    def get_run_messages(self, run_id: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT display_time, message_type, content
                FROM analysis_messages
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()

    def get_analysis_progress(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    selected_analysts_json,
                    agent_status_json,
                    report_sections_json,
                    current_agent,
                    current_report,
                    stats_json,
                    updated_at
                FROM analysis_run_progress
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "selected_analysts": self._deserialize_json(
                row["selected_analysts_json"], []
            ),
            "agent_status": self._deserialize_json(row["agent_status_json"], {}),
            "report_sections": self._deserialize_json(
                row["report_sections_json"], {}
            ),
            "current_agent": row["current_agent"],
            "current_report": row["current_report"],
            "stats": self._deserialize_json(row["stats_json"], {}),
            "updated_at": row["updated_at"],
        }

    def list_analysis_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    runs.id,
                    runs.asset_symbol,
                    runs.timeframe,
                    runs.analysis_time,
                    runs.status,
                    runs.results_dir,
                    runs.created_at,
                    runs.updated_at,
                    runs.completed_at,
                    progress.selected_analysts_json,
                    progress.agent_status_json,
                    progress.current_agent,
                    progress.current_report,
                    progress.stats_json,
                    progress.updated_at AS progress_updated_at
                FROM analysis_runs AS runs
                LEFT JOIN analysis_run_progress AS progress
                    ON progress.run_id = runs.id
                ORDER BY runs.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._hydrate_run_row(row) for row in rows]

    def get_analysis_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    runs.id,
                    runs.asset_symbol,
                    runs.timeframe,
                    runs.analysis_time,
                    runs.status,
                    runs.results_dir,
                    runs.config_json,
                    runs.created_at,
                    runs.updated_at,
                    runs.completed_at,
                    progress.selected_analysts_json,
                    progress.agent_status_json,
                    progress.current_agent,
                    progress.current_report,
                    progress.stats_json,
                    progress.report_sections_json,
                    progress.updated_at AS progress_updated_at
                FROM analysis_runs AS runs
                LEFT JOIN analysis_run_progress AS progress
                    ON progress.run_id = runs.id
                WHERE runs.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._hydrate_run_row(row)

    def get_run_tool_calls(self, run_id: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT display_time, tool_name, tool_args_json
                FROM analysis_tool_calls
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()

    def get_report_sections(self, run_id: int) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT section_name, content
                FROM analysis_report_sections
                WHERE run_id = ?
                ORDER BY section_name ASC
                """,
                (run_id,),
            ).fetchall()
        return {row["section_name"]: row["content"] for row in rows}

    def get_complete_report(self, run_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT markdown FROM complete_reports WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None else str(row["markdown"])

    def get_full_state_log(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM full_state_logs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def _hydrate_run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = {
            "id": int(row["id"]),
            "asset_symbol": row["asset_symbol"],
            "timeframe": row["timeframe"],
            "analysis_time": row["analysis_time"],
            "status": row["status"],
            "results_dir": row["results_dir"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
            "selected_analysts": self._deserialize_json(
                row["selected_analysts_json"]
                if "selected_analysts_json" in row.keys()
                else None,
                [],
            ),
            "agent_status": self._deserialize_json(
                row["agent_status_json"] if "agent_status_json" in row.keys() else None,
                {},
            ),
            "current_agent": row["current_agent"]
            if "current_agent" in row.keys()
            else None,
            "current_report": row["current_report"]
            if "current_report" in row.keys()
            else None,
            "stats": self._deserialize_json(
                row["stats_json"] if "stats_json" in row.keys() else None,
                {},
            ),
            "progress_updated_at": row["progress_updated_at"]
            if "progress_updated_at" in row.keys()
            else None,
        }
        if "config_json" in row.keys():
            data["config"] = self._deserialize_json(row["config_json"], {})
        if "report_sections_json" in row.keys():
            data["report_sections"] = self._deserialize_json(
                row["report_sections_json"], {}
            )
        return data

    def _hydrate_monitoring_loop_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = {
            "id": int(row["id"]),
            "asset_symbol": row["asset_symbol"],
            "timeframe": row["timeframe"],
            "interval_minutes": int(row["interval_minutes"]),
            "status": row["status"],
            "selections": self._deserialize_json(row["selections_json"], {}),
            "active_run_id": row["active_run_id"],
            "last_run_id": row["last_run_id"],
            "last_run_status": row["last_run_status"],
            "last_error": row["last_error"],
            "last_started_at": row["last_started_at"],
            "last_completed_at": row["last_completed_at"],
            "next_run_at": row["next_run_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "active_run_status" in row.keys():
            data["active_run_status"] = row["active_run_status"]
        if "last_run_status_live" in row.keys() and data["last_run_status"] is None:
            data["last_run_status"] = row["last_run_status_live"]
        return data
