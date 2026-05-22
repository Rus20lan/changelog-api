from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .models import SnapshotRequest


def serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize_value(value) for key, value in record.items()}


def date_diff(date_a: str | date | None, date_b: str | date | None) -> int:
    if not date_a or not date_b:
        return 0
    if isinstance(date_a, str):
        date_a = date.fromisoformat(date_a)
    if isinstance(date_b, str):
        date_b = date.fromisoformat(date_b)
    return (date_b - date_a).days


def build_project_meta(payload: SnapshotRequest, version: int) -> dict[str, Any]:
    summary = payload.summary
    project_info = payload.project_info
    return {
        "project_name": payload.project_name,
        "ms_project_name": project_info.project_name if project_info else "",
        "status_date": payload.status_date,
        "project_start": project_info.start_date if project_info else None,
        "project_finish": project_info.finish_date if project_info else None,
        "last_version": version,
        "total_tasks": summary.total_tasks if summary else len(payload.rows),
        "summary_tasks": summary.summary_tasks if summary else 0,
        "milestones": summary.milestones if summary else 0,
        "leaf_tasks": summary.leaf_tasks if summary else 0,
        "with_baseline": summary.with_baseline if summary else 0,
        "total_resources": summary.total_resources if summary else 0,
    }


def build_snapshot_rows(payload: SnapshotRequest, version: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload.rows:
        row_dict = row.model_dump()
        row_dict.update(
            {
                "project_name": payload.project_name,
                "snapshot_version": version,
                "status_date": payload.status_date,
            }
        )
        rows.append(row_dict)
    return rows


def compute_deltas(
    project_name: str,
    version_from: int,
    version_to: int,
    status_date_from: str | date,
    status_date_to: str | date,
    rows_from: list[dict[str, Any]],
    rows_to: list[dict[str, Any]],
) -> dict[str, Any]:
    map_from = {int(row["uid"]): row for row in rows_from}
    map_to = {int(row["uid"]): row for row in rows_to}

    uids_from = set(map_from)
    uids_to = set(map_to)

    added = []
    removed = []
    changed = []
    unchanged_count = 0

    for uid in sorted(uids_to - uids_from):
        curr = map_to[uid]
        added.append(
            {
                "uid": uid,
                "wbs": curr.get("wbs", ""),
                "name": curr.get("name", ""),
                "level": curr.get("level", 0),
                "summary": curr.get("summary", "N"),
                "change_type": "add",
                "delta_start_days": 0,
                "delta_finish_days": 0,
                "start_curr": serialize_value(curr.get("start")),
                "finish_curr": serialize_value(curr.get("finish")),
                "baseline_finish": serialize_value(curr.get("baseline_finish")),
                "delta_baseline_days": 0,
            }
        )

    for uid in sorted(uids_from - uids_to):
        prev = map_from[uid]
        removed.append(
            {
                "uid": uid,
                "wbs": prev.get("wbs", ""),
                "name": prev.get("name", ""),
                "level": prev.get("level", 0),
                "summary": prev.get("summary", "N"),
                "change_type": "remove",
                "start_prev": serialize_value(prev.get("start")),
                "finish_prev": serialize_value(prev.get("finish")),
                "baseline_finish": serialize_value(prev.get("baseline_finish")),
                "delta_baseline_days": 0,
            }
        )

    for uid in sorted(uids_from & uids_to):
        prev = map_from[uid]
        curr = map_to[uid]

        delta_start = date_diff(prev.get("start"), curr.get("start"))
        delta_finish = date_diff(prev.get("finish"), curr.get("finish"))
        name_changed = prev.get("name", "") != curr.get("name", "")

        if delta_start == 0 and delta_finish == 0 and not name_changed:
            unchanged_count += 1
            continue

        if delta_finish < 0:
            change_type = "reduction"
        elif delta_finish > 0:
            change_type = "increase"
        elif delta_start != 0:
            change_type = "postpone"
        else:
            change_type = "rename"

        delta_baseline = date_diff(curr.get("baseline_finish"), curr.get("finish"))
        changed.append(
            {
                "uid": uid,
                "wbs": curr.get("wbs", ""),
                "name": curr.get("name", ""),
                "name_prev": prev.get("name", "") if name_changed else "",
                "level": curr.get("level", 0),
                "summary": curr.get("summary", "N"),
                "change_type": change_type,
                "delta_start_days": delta_start,
                "delta_finish_days": delta_finish,
                "start_prev": serialize_value(prev.get("start")),
                "start_curr": serialize_value(curr.get("start")),
                "finish_prev": serialize_value(prev.get("finish")),
                "finish_curr": serialize_value(curr.get("finish")),
                "baseline_finish": serialize_value(curr.get("baseline_finish")),
                "delta_baseline_days": delta_baseline,
            }
        )

    return {
        "project_name": project_name,
        "version_from": version_from,
        "version_to": version_to,
        "status_date_from": serialize_value(status_date_from),
        "status_date_to": serialize_value(status_date_to),
        "total_from": len(rows_from),
        "total_to": len(rows_to),
        "unchanged_count": unchanged_count,
        "added": added,
        "removed": removed,
        "changed": changed,
    }
