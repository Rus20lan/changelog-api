from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import requests

from .config import settings
from .logic import serialize_record


SNAPSHOT_COLUMNS = [
    "project_name",
    "snapshot_version",
    "status_date",
    "uid",
    "id",
    "wbs",
    "name",
    "level",
    "outline",
    "parent_uid",
    "summary",
    "milestone",
    "start",
    "finish",
    "baseline_start",
    "baseline_finish",
    "duration",
    "pct_complete",
    "actual_start",
    "actual_finish",
    "cost",
    "baseline_cost",
    "work",
    "baseline_work",
    "predecessors",
    "resources",
    "notes",
]

CHANGELOG_COLUMNS = [
    "project_name",
    "log_id",
    "snapshot_from",
    "snapshot_to",
    "date",
    "uid",
    "wbs",
    "name",
    "level",
    "change_type",
    "delta_start_days",
    "delta_finish_days",
    "delta_baseline_days",
    "category_code",
    "technical_summary",
    "impact_type",
    "confidence",
    "warnings",
    "escalation_required",
    "expert_comment",
    "status",
]

STRATEGIC_COLUMNS = [
    "project_name",
    "uid",
    "wbs",
    "name",
    "summary",
    "baseline_finish",
    "current_finish",
    "delta_baseline_days",
    "escalation",
    "ai_strategic_analysis",
    "snapshot_version",
]

PROJECT_META_COLUMNS = [
    "project_name",
    "ms_project_name",
    "status_date",
    "project_start",
    "project_finish",
    "last_version",
    "total_tasks",
    "summary_tasks",
    "milestones",
    "leaf_tasks",
    "with_baseline",
    "total_resources",
]


class ClickHouseError(RuntimeError):
    """Raised when ClickHouse returns an error."""


def escape_sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return f"'{value.isoformat()}'"
    return f"'{escape_sql_string(str(value))}'"


class ClickHouseRepository:
    def __init__(self) -> None:
        self._endpoint = (
            f"http://{settings.clickhouse_host}:{settings.clickhouse_port}/?"
            + urlencode(
                {
                    "user": settings.clickhouse_user,
                    "password": settings.clickhouse_password,
                    "database": settings.clickhouse_db,
                }
            )
        )
        self._timeout = settings.clickhouse_timeout

    def execute(self, sql: str) -> str:
        try:
            response = requests.post(
                self._endpoint,
                data=sql.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise ClickHouseError(f"ClickHouse error: {exc}") from exc

        if response.status_code >= 400:
            raise ClickHouseError(f"ClickHouse error: {response.text.strip()}")
        return response.text

    def query_rows(self, sql: str) -> list[dict[str, Any]]:
        payload = self.execute(f"{sql.rstrip()} FORMAT JSONEachRow")
        rows: list[dict[str, Any]] = []
        for line in payload.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def query_row(self, sql: str) -> dict[str, Any] | None:
        rows = self.query_rows(sql)
        return rows[0] if rows else None

    def query_scalar(self, sql: str, key: str = "value") -> Any:
        row = self.query_row(sql)
        if row is None:
            return None
        return row.get(key)

    def list_tables(self) -> list[str]:
        rows = self.query_rows(
            f"SELECT name FROM system.tables WHERE database = '{escape_sql_string(settings.clickhouse_db)}'"
        )
        return [row["name"] for row in rows]

    def get_latest_snapshot_version(self, project_name: str) -> int:
        value = self.query_scalar(
            "SELECT max(snapshot_version) AS value "
            "FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}'"
        )
        return int(value or 0)

    def insert_snapshot_rows(self, rows: list[dict[str, Any]], batch_size: int = 100) -> None:
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset : offset + batch_size]
            values = []
            for row in batch:
                values.append(
                    "(" + ", ".join(sql_value(row.get(column)) for column in SNAPSHOT_COLUMNS) + ")"
                )
            sql = (
                "INSERT INTO snapshots ("
                + ", ".join(SNAPSHOT_COLUMNS)
                + ") VALUES "
                + ", ".join(values)
            )
            self.execute(sql)

    def upsert_project_meta(self, meta: dict[str, Any]) -> None:
        sql = (
            "INSERT INTO project_meta ("
            + ", ".join(PROJECT_META_COLUMNS)
            + ") VALUES ("
            + ", ".join(sql_value(meta.get(column)) for column in PROJECT_META_COLUMNS)
            + ")"
        )
        self.execute(sql)

    def get_project_meta(self, project_name: str) -> dict[str, Any] | None:
        row = self.query_row(
            "SELECT project_name, ms_project_name, status_date, project_start, project_finish, "
            "last_parsed_at, last_version, total_tasks, summary_tasks, milestones, leaf_tasks, "
            "with_baseline, total_resources, updated_at "
            "FROM project_meta FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}'"
        )
        return serialize_record(row) if row else None

    def get_snapshot_rows(
        self, project_name: str, version: int, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit_clause = f" LIMIT {limit}" if limit else ""
        rows = self.query_rows(
            "SELECT project_name, snapshot_version, status_date, uid, id, wbs, name, level, outline, "
            "parent_uid, summary, milestone, start, finish, baseline_start, baseline_finish, duration, "
            "pct_complete, actual_start, actual_finish, cost, baseline_cost, work, baseline_work, "
            "predecessors, resources, notes "
            "FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND snapshot_version = {version} "
            "ORDER BY uid"
            + limit_clause
        )
        return [serialize_record(row) for row in rows]

    def get_snapshot_total_count(self, project_name: str, version: int) -> int:
        value = self.query_scalar(
            "SELECT count() AS value FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND snapshot_version = {version}"
        )
        return int(value or 0)

    def get_snapshot_status_date(self, project_name: str, version: int) -> str | None:
        value = self.query_scalar(
            "SELECT any(status_date) AS value FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND snapshot_version = {version}"
        )
        return value

    def insert_changelog_entries(self, entries: list[dict[str, Any]]) -> None:
        values = []
        for entry in entries:
            values.append(
                "(" + ", ".join(sql_value(entry.get(column)) for column in CHANGELOG_COLUMNS) + ")"
            )
        sql = (
            "INSERT INTO change_log ("
            + ", ".join(CHANGELOG_COLUMNS)
            + ") VALUES "
            + ", ".join(values)
        )
        self.execute(sql)

    def get_changelog_entry(self, project_name: str, log_id: str) -> dict[str, Any] | None:
        row = self.query_row(
            "SELECT project_name, log_id, snapshot_from, snapshot_to, date, uid, wbs, name, level, "
            "change_type, delta_start_days, delta_finish_days, delta_baseline_days, category_code, "
            "technical_summary, impact_type, confidence, warnings, escalation_required, expert_comment, "
            "status, updated_at "
            "FROM change_log FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND log_id = '{escape_sql_string(log_id)}'"
        )
        return serialize_record(row) if row else None

    def list_changelog(
        self,
        project_name: str,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = [f"project_name = '{escape_sql_string(project_name)}'"]
        if snapshot_from is not None:
            filters.append(f"snapshot_from = {snapshot_from}")
        if snapshot_to is not None:
            filters.append(f"snapshot_to = {snapshot_to}")
        if status_filter is not None:
            filters.append(f"status = '{escape_sql_string(status_filter)}'")

        sql = (
            "SELECT project_name, log_id, snapshot_from, snapshot_to, date, uid, wbs, name, level, "
            "change_type, delta_start_days, delta_finish_days, delta_baseline_days, category_code, "
            "technical_summary, impact_type, confidence, warnings, escalation_required, expert_comment, "
            "status, updated_at "
            "FROM change_log FINAL "
            f"WHERE {' AND '.join(filters)} "
            "ORDER BY date DESC, log_id ASC"
        )
        rows = self.query_rows(sql)
        return [serialize_record(row) for row in rows]

    def insert_strategic_entries(self, entries: list[dict[str, Any]]) -> None:
        values = []
        for entry in entries:
            values.append(
                "(" + ", ".join(sql_value(entry.get(column)) for column in STRATEGIC_COLUMNS) + ")"
            )
        sql = (
            "INSERT INTO strategic_control ("
            + ", ".join(STRATEGIC_COLUMNS)
            + ") VALUES "
            + ", ".join(values)
        )
        self.execute(sql)

    def list_strategic(self, project_name: str) -> list[dict[str, Any]]:
        latest_version = self.query_scalar(
            "SELECT max(snapshot_version) AS value FROM strategic_control FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}'"
        )
        if latest_version in (None, 0):
            return []
        rows = self.query_rows(
            "SELECT project_name, uid, wbs, name, summary, baseline_finish, current_finish, "
            "delta_baseline_days, escalation, ai_strategic_analysis, snapshot_version, updated_at "
            "FROM strategic_control FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND snapshot_version = {int(latest_version)} "
            "ORDER BY abs(delta_baseline_days) DESC, uid ASC"
        )
        return [serialize_record(row) for row in rows]

    def list_classifier_codes(self) -> list[dict[str, Any]]:
        rows = self.query_rows(
            "SELECT code, category, group_name, description, impact "
            "FROM classifier ORDER BY code"
        )
        return [serialize_record(row) for row in rows]


_repository: ClickHouseRepository | None = None


def get_repository() -> ClickHouseRepository:
    global _repository
    if _repository is None:
        _repository = ClickHouseRepository()
    return _repository
