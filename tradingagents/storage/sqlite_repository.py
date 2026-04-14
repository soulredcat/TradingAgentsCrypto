from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
        self.db_path = resolve_db_path(db_path=db_path, config=config)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
