from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import requests

from .config import settings
from .logic import date_diff, serialize_record


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

BASELINE_COLUMNS = [
    "project_name",
    "uid",
    "wbs",
    "name",
    "baseline_start",
    "baseline_finish",
    "baseline_source",
    "source_snapshot",
    "user_comment",
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

    def _alter_delete(self, table_name: str, where_clause: str) -> None:
        self.execute(f"ALTER TABLE {table_name} DELETE WHERE {where_clause}")

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

    def list_project_versions(self, project_name: str) -> list[dict[str, Any]]:
        rows = self.query_rows(
            "SELECT snapshot_version AS version, any(status_date) AS status_date, "
            "count() AS tasks_count, max(parsed_at) AS parsed_at "
            "FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            "GROUP BY snapshot_version "
            "ORDER BY snapshot_version"
        )
        versions: list[dict[str, Any]] = []
        for row in rows:
            serialized = serialize_record(row)
            version = int(serialized["version"])
            changelog_count = self.query_scalar(
                "SELECT count() AS value FROM change_log FINAL "
                f"WHERE project_name = '{escape_sql_string(project_name)}' "
                f"AND (snapshot_from = {version} OR snapshot_to = {version})"
            )
            serialized["has_changelog"] = int(changelog_count or 0) > 0
            versions.append(serialized)
        return versions

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

    def replace_baseline(
        self,
        project_name: str,
        source_snapshot: int,
        entries: list[dict[str, Any]],
    ) -> int:
        escaped = escape_sql_string(project_name)
        self._alter_delete("strategic_baseline", f"project_name = '{escaped}'")
        if not entries:
            return 0
        return self._insert_baseline_entries(project_name, source_snapshot, entries)

    def _insert_baseline_entries(
        self,
        project_name: str,
        source_snapshot: int,
        entries: list[dict[str, Any]],
    ) -> int:
        values = []
        for entry in entries:
            payload = {
                "project_name": project_name,
                "uid": int(entry["uid"]),
                "wbs": entry.get("wbs", ""),
                "name": entry.get("name", ""),
                "baseline_start": entry.get("baseline_start"),
                "baseline_finish": entry.get("baseline_finish"),
                "baseline_source": entry.get("baseline_source", "manual_form"),
                "source_snapshot": int(entry.get("source_snapshot", source_snapshot) or source_snapshot),
                "user_comment": entry.get("user_comment", ""),
            }
            values.append(
                "(" + ", ".join(sql_value(payload.get(column)) for column in BASELINE_COLUMNS) + ")"
            )
        sql = (
            "INSERT INTO strategic_baseline ("
            + ", ".join(BASELINE_COLUMNS)
            + ") VALUES "
            + ", ".join(values)
        )
        self.execute(sql)
        return len(entries)

    def list_baseline(self, project_name: str) -> list[dict[str, Any]]:
        rows = self.query_rows(
            "SELECT project_name, uid, wbs, name, baseline_start, baseline_finish, "
            "baseline_source, source_snapshot, user_comment, created_at, updated_at "
            "FROM strategic_baseline FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            "ORDER BY uid"
        )
        return [serialize_record(row) for row in rows]

    def get_baseline_entry(self, project_name: str, uid: int) -> dict[str, Any] | None:
        row = self.query_row(
            "SELECT project_name, uid, wbs, name, baseline_start, baseline_finish, "
            "baseline_source, source_snapshot, user_comment, created_at, updated_at "
            "FROM strategic_baseline FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' AND uid = {int(uid)}"
        )
        return serialize_record(row) if row else None

    def patch_baseline(
        self,
        project_name: str,
        source_snapshot: int,
        upsert_entries: list[dict[str, Any]],
        remove_uids: list[int],
    ) -> dict[str, int]:
        escaped = escape_sql_string(project_name)
        upserted_uids = [int(entry["uid"]) for entry in upsert_entries]
        affected_uids = sorted(set(upserted_uids) | set(int(uid) for uid in remove_uids))
        if affected_uids:
            ids_clause = ", ".join(str(uid) for uid in affected_uids)
            self._alter_delete(
                "strategic_baseline",
                f"project_name = '{escaped}' AND uid IN ({ids_clause})",
            )
        added = 0
        if upsert_entries:
            added = self._insert_baseline_entries(project_name, source_snapshot, upsert_entries)
        return {"upserted": added, "removed": len(remove_uids)}

    def delete_baseline(self, project_name: str) -> int:
        escaped = escape_sql_string(project_name)
        count = int(
            self.query_scalar(
                "SELECT count() AS value FROM strategic_baseline FINAL "
                f"WHERE project_name = '{escaped}'"
            )
            or 0
        )
        self._alter_delete("strategic_baseline", f"project_name = '{escaped}'")
        self._alter_delete("strategic_control", f"project_name = '{escaped}'")
        return count

    def recalc_strategic_from_baseline(
        self, project_name: str, snapshot_version: int
    ) -> dict[str, Any]:
        baseline_entries = self.list_baseline(project_name)
        if not baseline_entries:
            return {
                "entries_written": 0,
                "delays": 0,
                "ahead": 0,
                "over_30_days": 0,
                "escalations": 0,
            }

        snapshot_rows = self.get_snapshot_rows(project_name, snapshot_version)
        snapshot_by_uid = {int(row["uid"]): row for row in snapshot_rows}

        escaped = escape_sql_string(project_name)
        self._alter_delete("strategic_control", f"project_name = '{escaped}'")

        entries: list[dict[str, Any]] = []
        delays = 0
        ahead = 0
        over_30 = 0
        escalations = 0
        for baseline in baseline_entries:
            uid = int(baseline["uid"])
            snapshot_row = snapshot_by_uid.get(uid)
            current_finish = snapshot_row.get("finish") if snapshot_row else None
            baseline_finish = baseline.get("baseline_finish")
            delta = date_diff(baseline_finish, current_finish)
            if delta > 0:
                delays += 1
            elif delta < 0:
                ahead += 1
            if abs(delta) > 30:
                over_30 += 1
            escalation = delta > 0
            if escalation:
                escalations += 1
            entries.append(
                {
                    "project_name": project_name,
                    "uid": uid,
                    "wbs": baseline.get("wbs", ""),
                    "name": baseline.get("name", ""),
                    "summary": (snapshot_row.get("summary", "Y") if snapshot_row else "Y"),
                    "baseline_finish": baseline_finish,
                    "current_finish": current_finish,
                    "delta_baseline_days": delta,
                    "escalation": escalation,
                    "ai_strategic_analysis": "",
                    "snapshot_version": snapshot_version,
                }
            )

        if entries:
            self.insert_strategic_entries(entries)

        return {
            "entries_written": len(entries),
            "delays": delays,
            "ahead": ahead,
            "over_30_days": over_30,
            "escalations": escalations,
        }

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

    def purge_all_data(self) -> dict[str, bool]:
        tables = [
            "snapshots",
            "project_meta",
            "strategic_baseline",
            "strategic_control",
            "change_log",
        ]
        for table_name in tables:
            self._alter_delete(table_name, "1 = 1")
        return {table_name: True for table_name in tables}

    def delete_project_data(self, project_name: str) -> None:
        escaped = escape_sql_string(project_name)
        condition = f"project_name = '{escaped}'"
        for table_name in [
            "snapshots",
            "project_meta",
            "strategic_baseline",
            "strategic_control",
            "change_log",
        ]:
            self._alter_delete(table_name, condition)

    def _get_project_versions_numbers(self, project_name: str) -> list[int]:
        rows = self.query_rows(
            "SELECT DISTINCT snapshot_version AS version FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            "ORDER BY version"
        )
        return [int(row["version"]) for row in rows]

    def _build_project_meta_from_latest_snapshot(
        self, project_name: str, latest_version: int
    ) -> dict[str, Any]:
        existing_meta = self.get_project_meta(project_name) or {}
        aggregate = self.query_row(
            "SELECT any(status_date) AS status_date, "
            "count() AS total_tasks, "
            "countIf(summary = 'Y') AS summary_tasks, "
            "countIf(milestone = 'Y') AS milestones, "
            "countIf(summary = 'N') AS leaf_tasks, "
            "countIf(baseline_finish IS NOT NULL) AS with_baseline "
            "FROM snapshots FINAL "
            f"WHERE project_name = '{escape_sql_string(project_name)}' "
            f"AND snapshot_version = {latest_version}"
        )
        if aggregate is None:
            raise ClickHouseError("ClickHouse error: latest snapshot aggregate not found")

        aggregate = serialize_record(aggregate)
        return {
            "project_name": project_name,
            "ms_project_name": existing_meta.get("ms_project_name", ""),
            "status_date": aggregate["status_date"],
            "project_start": existing_meta.get("project_start"),
            "project_finish": existing_meta.get("project_finish"),
            "last_version": latest_version,
            "total_tasks": int(aggregate["total_tasks"]),
            "summary_tasks": int(aggregate["summary_tasks"]),
            "milestones": int(aggregate["milestones"]),
            "leaf_tasks": int(aggregate["leaf_tasks"]),
            "with_baseline": int(aggregate["with_baseline"]),
            "total_resources": int(existing_meta.get("total_resources", 0) or 0),
        }

    def delete_project_versions(self, project_name: str, versions: list[int]) -> dict[str, Any]:
        escaped = escape_sql_string(project_name)
        existing_versions = self._get_project_versions_numbers(project_name)
        requested_versions = sorted(set(versions))

        changelog_entries_deleted = int(
            self.query_scalar(
                "SELECT count() AS value FROM change_log FINAL "
                f"WHERE project_name = '{escaped}' "
                f"AND (snapshot_from IN ({', '.join(str(v) for v in requested_versions)}) "
                f"OR snapshot_to IN ({', '.join(str(v) for v in requested_versions)}))"
            )
            or 0
        )
        strategic_entries_deleted = int(
            self.query_scalar(
                "SELECT count() AS value FROM strategic_control FINAL "
                f"WHERE project_name = '{escaped}' "
                f"AND snapshot_version IN ({', '.join(str(v) for v in requested_versions)})"
            )
            or 0
        )

        versions_clause = ", ".join(str(version) for version in requested_versions)
        self._alter_delete(
            "snapshots",
            f"project_name = '{escaped}' AND snapshot_version IN ({versions_clause})",
        )
        self._alter_delete(
            "change_log",
            f"project_name = '{escaped}' AND (snapshot_from IN ({versions_clause}) "
            f"OR snapshot_to IN ({versions_clause}))",
        )
        self._alter_delete(
            "strategic_control",
            f"project_name = '{escaped}' AND snapshot_version IN ({versions_clause})",
        )

        remaining_versions = [version for version in existing_versions if version not in requested_versions]
        deleted_latest = bool(existing_versions) and max(existing_versions) in requested_versions

        if not remaining_versions:
            self._alter_delete("project_meta", f"project_name = '{escaped}'")
            self._alter_delete("strategic_baseline", f"project_name = '{escaped}'")
            self._alter_delete("strategic_control", f"project_name = '{escaped}'")
        else:
            latest_remaining = max(remaining_versions)
            self.upsert_project_meta(
                self._build_project_meta_from_latest_snapshot(project_name, latest_remaining)
            )
            if deleted_latest:
                self.recalc_strategic_from_baseline(project_name, latest_remaining)

        return {
            "status": "ok",
            "action": "delete_versions",
            "project_name": project_name,
            "deleted_versions": requested_versions,
            "remaining_versions": remaining_versions,
            "changelog_entries_deleted": changelog_entries_deleted,
            "strategic_entries_deleted": strategic_entries_deleted,
            "message": (
                f"Удалены версии {', '.join(str(v) for v in requested_versions)}. "
                + (
                    f"Остались версии {', '.join(str(v) for v in remaining_versions)}."
                    if remaining_versions
                    else "Версий проекта не осталось."
                )
            ),
        }


_repository: ClickHouseRepository | None = None


def get_repository() -> ClickHouseRepository:
    global _repository
    if _repository is None:
        _repository = ClickHouseRepository()
    return _repository
