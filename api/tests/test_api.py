from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.logic import date_diff
from app.main import app
from app.repository import get_repository


class FakeRepository:
    def __init__(self) -> None:
        self.tables = [
            "snapshots",
            "strategic_control",
            "change_log",
            "classifier",
            "project_meta",
        ]
        self.snapshot_rows: dict[tuple[str, int], list[dict]] = {}
        self.project_meta: dict[str, dict] = {}
        self.changelog_entries: dict[tuple[str, str], dict] = {}
        self.strategic_entries: dict[str, list[dict]] = {}
        self.baseline_entries: dict[str, list[dict]] = {}
        self.classifier_codes = [{"code": "UNKNOWN", "category": "Нет данных"}]

    def list_tables(self) -> list[str]:
        return self.tables

    def get_latest_snapshot_version(self, project_name: str) -> int:
        versions = [
            version for current_project, version in self.snapshot_rows if current_project == project_name
        ]
        return max(versions, default=0)

    def insert_snapshot_rows(self, rows: list[dict], batch_size: int = 100) -> None:
        for row in rows:
            key = (row["project_name"], row["snapshot_version"])
            prepared = {
                **row,
                "parsed_at": row.get("parsed_at", "2026-05-22T10:00:00"),
            }
            self.snapshot_rows.setdefault(key, []).append(prepared)

    def upsert_project_meta(self, meta: dict) -> None:
        self.project_meta[meta["project_name"]] = {
            **meta,
            "last_parsed_at": "2026-05-22T10:00:00",
            "updated_at": "2026-05-22T10:00:00",
        }

    def get_project_meta(self, project_name: str) -> dict | None:
        return self.project_meta.get(project_name)

    def get_snapshot_rows(
        self, project_name: str, version: int, limit: int | None = None
    ) -> list[dict]:
        rows = self.snapshot_rows.get((project_name, version), [])
        prepared = []
        for row in rows[: limit or None]:
            prepared.append(
                {
                    **row,
                    "status_date": row["status_date"].isoformat(),
                    "start": row["start"].isoformat() if row["start"] else None,
                    "finish": row["finish"].isoformat() if row["finish"] else None,
                    "baseline_start": row["baseline_start"].isoformat()
                    if row["baseline_start"]
                    else None,
                    "baseline_finish": row["baseline_finish"].isoformat()
                    if row["baseline_finish"]
                    else None,
                    "actual_start": row["actual_start"].isoformat() if row["actual_start"] else None,
                    "actual_finish": row["actual_finish"].isoformat()
                    if row["actual_finish"]
                    else None,
                }
            )
        return prepared

    def get_snapshot_total_count(self, project_name: str, version: int) -> int:
        return len(self.snapshot_rows.get((project_name, version), []))

    def get_snapshot_status_date(self, project_name: str, version: int) -> str | None:
        rows = self.snapshot_rows.get((project_name, version), [])
        if not rows:
            return None
        return rows[0]["status_date"].isoformat()

    def list_project_versions(self, project_name: str) -> list[dict]:
        versions = []
        for (current_project, version), rows in sorted(
            self.snapshot_rows.items(), key=lambda item: item[0][1]
        ):
            if current_project != project_name or not rows:
                continue
            has_changelog = any(
                entry["snapshot_from"] == version or entry["snapshot_to"] == version
                for (entry_project, _), entry in self.changelog_entries.items()
                if entry_project == project_name
            )
            versions.append(
                {
                    "version": version,
                    "status_date": rows[0]["status_date"].isoformat(),
                    "tasks_count": len(rows),
                    "parsed_at": rows[0]["parsed_at"],
                    "has_changelog": has_changelog,
                }
            )
        return versions

    def insert_changelog_entries(self, entries: list[dict]) -> None:
        for entry in entries:
            normalized = {
                **entry,
                "date": entry["date"].isoformat() if isinstance(entry["date"], date) else entry["date"],
                "updated_at": "2026-05-22T10:00:00",
            }
            self.changelog_entries[(entry["project_name"], entry["log_id"])] = normalized

    def get_changelog_entry(self, project_name: str, log_id: str) -> dict | None:
        entry = self.changelog_entries.get((project_name, log_id))
        return dict(entry) if entry else None

    def list_changelog(
        self,
        project_name: str,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
        status_filter: str | None = None,
    ) -> list[dict]:
        entries = [
            dict(entry)
            for (current_project, _), entry in self.changelog_entries.items()
            if current_project == project_name
        ]
        if snapshot_from is not None:
            entries = [entry for entry in entries if entry["snapshot_from"] == snapshot_from]
        if snapshot_to is not None:
            entries = [entry for entry in entries if entry["snapshot_to"] == snapshot_to]
        if status_filter is not None:
            entries = [entry for entry in entries if entry["status"] == status_filter]
        return entries

    def insert_strategic_entries(self, entries: list[dict]) -> None:
        if not entries:
            return
        project_name = entries[0]["project_name"]
        self.strategic_entries[project_name] = [
            {
                **entry,
                "baseline_finish": entry["baseline_finish"].isoformat()
                if hasattr(entry["baseline_finish"], "isoformat") and entry["baseline_finish"]
                else entry["baseline_finish"],
                "current_finish": entry["current_finish"].isoformat()
                if hasattr(entry["current_finish"], "isoformat") and entry["current_finish"]
                else entry["current_finish"],
                "updated_at": "2026-05-22T10:00:00",
            }
            for entry in entries
        ]

    def list_strategic(self, project_name: str) -> list[dict]:
        return self.strategic_entries.get(project_name, [])

    def replace_baseline(
        self, project_name: str, source_snapshot: int, entries: list[dict]
    ) -> int:
        prepared = []
        for entry in entries:
            prepared.append(
                {
                    "project_name": project_name,
                    "uid": int(entry["uid"]),
                    "wbs": entry.get("wbs", ""),
                    "name": entry.get("name", ""),
                    "baseline_start": entry.get("baseline_start").isoformat()
                    if hasattr(entry.get("baseline_start"), "isoformat") and entry.get("baseline_start")
                    else entry.get("baseline_start"),
                    "baseline_finish": entry.get("baseline_finish").isoformat()
                    if hasattr(entry.get("baseline_finish"), "isoformat") and entry.get("baseline_finish")
                    else entry.get("baseline_finish"),
                    "baseline_source": entry.get("baseline_source", "manual_form"),
                    "source_snapshot": source_snapshot,
                    "user_comment": entry.get("user_comment", ""),
                    "created_at": "2026-05-22T10:00:00",
                    "updated_at": "2026-05-22T10:00:00",
                }
            )
        self.baseline_entries[project_name] = prepared
        return len(prepared)

    def list_baseline(self, project_name: str) -> list[dict]:
        return [dict(entry) for entry in self.baseline_entries.get(project_name, [])]

    def patch_baseline(
        self,
        project_name: str,
        source_snapshot: int,
        upsert_entries: list[dict],
        remove_uids: list[int],
    ) -> dict:
        current = {entry["uid"]: entry for entry in self.baseline_entries.get(project_name, [])}
        for uid in remove_uids:
            current.pop(int(uid), None)
        for entry in upsert_entries:
            current[int(entry["uid"])] = {
                "project_name": project_name,
                "uid": int(entry["uid"]),
                "wbs": entry.get("wbs", ""),
                "name": entry.get("name", ""),
                "baseline_start": entry.get("baseline_start").isoformat()
                if hasattr(entry.get("baseline_start"), "isoformat") and entry.get("baseline_start")
                else entry.get("baseline_start"),
                "baseline_finish": entry.get("baseline_finish").isoformat()
                if hasattr(entry.get("baseline_finish"), "isoformat") and entry.get("baseline_finish")
                else entry.get("baseline_finish"),
                "baseline_source": entry.get("baseline_source", "manual_form"),
                "source_snapshot": source_snapshot,
                "user_comment": entry.get("user_comment", ""),
                "created_at": "2026-05-22T10:00:00",
                "updated_at": "2026-05-22T10:00:00",
            }
        self.baseline_entries[project_name] = sorted(current.values(), key=lambda e: e["uid"])
        return {"upserted": len(upsert_entries), "removed": len(remove_uids)}

    def delete_baseline(self, project_name: str) -> int:
        entries = self.baseline_entries.pop(project_name, [])
        self.strategic_entries.pop(project_name, None)
        return len(entries)

    def recalc_strategic_from_baseline(
        self, project_name: str, snapshot_version: int
    ) -> dict:
        baseline = self.baseline_entries.get(project_name, [])
        if not baseline:
            return {
                "entries_written": 0,
                "delays": 0,
                "ahead": 0,
                "over_30_days": 0,
                "escalations": 0,
            }
        rows = self.snapshot_rows.get((project_name, snapshot_version), [])
        rows_by_uid = {row["uid"]: row for row in rows}
        entries = []
        delays = ahead = over_30 = escalations = 0
        for item in baseline:
            uid = item["uid"]
            snapshot_row = rows_by_uid.get(uid)
            current_finish = snapshot_row.get("finish") if snapshot_row else None
            current_finish_iso = (
                current_finish.isoformat()
                if hasattr(current_finish, "isoformat") and current_finish
                else current_finish
            )
            delta = date_diff(item.get("baseline_finish"), current_finish_iso)
            if delta > 0:
                delays += 1
                escalations += 1
            elif delta < 0:
                ahead += 1
            if abs(delta) > 30:
                over_30 += 1
            entries.append(
                {
                    "project_name": project_name,
                    "uid": uid,
                    "wbs": item.get("wbs", ""),
                    "name": item.get("name", ""),
                    "summary": (snapshot_row.get("summary", "Y") if snapshot_row else "Y"),
                    "baseline_finish": item.get("baseline_finish"),
                    "current_finish": current_finish_iso,
                    "delta_baseline_days": delta,
                    "escalation": delta > 0,
                    "ai_strategic_analysis": "",
                    "snapshot_version": snapshot_version,
                    "updated_at": "2026-05-22T10:00:00",
                }
            )
        self.strategic_entries[project_name] = entries
        return {
            "entries_written": len(entries),
            "delays": delays,
            "ahead": ahead,
            "over_30_days": over_30,
            "escalations": escalations,
        }

    def list_classifier_codes(self) -> list[dict]:
        return self.classifier_codes

    def purge_all_data(self) -> dict[str, bool]:
        self.snapshot_rows.clear()
        self.project_meta.clear()
        self.changelog_entries.clear()
        self.strategic_entries.clear()
        self.baseline_entries.clear()
        return {
            "snapshots": True,
            "project_meta": True,
            "strategic_baseline": True,
            "strategic_control": True,
            "change_log": True,
        }

    def delete_project_data(self, project_name: str) -> None:
        self.snapshot_rows = {
            key: value for key, value in self.snapshot_rows.items() if key[0] != project_name
        }
        self.project_meta.pop(project_name, None)
        self.strategic_entries.pop(project_name, None)
        self.baseline_entries.pop(project_name, None)
        self.changelog_entries = {
            key: value
            for key, value in self.changelog_entries.items()
            if key[0] != project_name
        }

    def delete_project_versions(self, project_name: str, versions: list[int]) -> dict:
        existing_versions = sorted(
            [version for current_project, version in self.snapshot_rows if current_project == project_name]
        )
        requested = sorted(set(versions))
        deleted_latest = bool(existing_versions) and max(existing_versions) in requested

        changelog_entries_deleted = sum(
            1
            for (current_project, _), entry in self.changelog_entries.items()
            if current_project == project_name
            and (entry["snapshot_from"] in requested or entry["snapshot_to"] in requested)
        )
        strategic_entries_deleted = sum(
            1
            for entry in self.strategic_entries.get(project_name, [])
            if entry["snapshot_version"] in requested
        )

        self.snapshot_rows = {
            key: value
            for key, value in self.snapshot_rows.items()
            if not (key[0] == project_name and key[1] in requested)
        }
        self.changelog_entries = {
            key: value
            for key, value in self.changelog_entries.items()
            if not (
                key[0] == project_name
                and (value["snapshot_from"] in requested or value["snapshot_to"] in requested)
            )
        }

        self.strategic_entries[project_name] = [
            entry
            for entry in self.strategic_entries.get(project_name, [])
            if entry["snapshot_version"] not in requested
        ]

        remaining_versions = [version for version in existing_versions if version not in requested]
        if not remaining_versions:
            self.project_meta.pop(project_name, None)
            self.strategic_entries.pop(project_name, None)
            self.baseline_entries.pop(project_name, None)
        else:
            latest_version = max(remaining_versions)
            rows = self.snapshot_rows[(project_name, latest_version)]
            current_meta = self.project_meta.get(project_name, {})
            self.project_meta[project_name] = {
                **current_meta,
                "project_name": project_name,
                "status_date": rows[0]["status_date"],
                "last_version": latest_version,
                "total_tasks": len(rows),
                "summary_tasks": sum(1 for row in rows if row["summary"] == "Y"),
                "milestones": sum(1 for row in rows if row["milestone"] == "Y"),
                "leaf_tasks": sum(1 for row in rows if row["summary"] == "N"),
                "with_baseline": sum(1 for row in rows if row["baseline_finish"] is not None),
                "updated_at": "2026-05-22T10:00:00",
                "last_parsed_at": "2026-05-22T10:00:00",
            }
            if deleted_latest:
                self.recalc_strategic_from_baseline(project_name, latest_version)

        return {
            "status": "ok",
            "action": "delete_versions",
            "project_name": project_name,
            "deleted_versions": requested,
            "remaining_versions": remaining_versions,
            "changelog_entries_deleted": changelog_entries_deleted,
            "strategic_entries_deleted": strategic_entries_deleted,
            "message": (
                f"Удалены версии {', '.join(str(version) for version in requested)}. "
                + (
                    f"Остались версии {', '.join(str(version) for version in remaining_versions)}."
                    if remaining_versions
                    else "Версий проекта не осталось."
                )
            ),
        }


def make_client() -> tuple[TestClient, FakeRepository]:
    repository = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app), repository


def auth_headers() -> dict[str, str]:
    return {"X-Api-Key": "dev-api-key-please-change-me-32chars"}


def build_snapshot_payload(
    project_name: str, status_date: str, uid: int, name: str = "Задача", summary: str = "Y"
) -> dict:
    return {
        "project_name": project_name,
        "status_date": status_date,
        "rows": [
            {
                "UID": uid,
                "ID": uid,
                "WBS": "1",
                "Name": name,
                "Level": 1,
                "Outline": "1",
                "Parent_UID": 0,
                "Summary": summary,
                "Milestone": "N",
                "Start": status_date,
                "Finish": status_date,
                "Baseline_Start": status_date,
                "Baseline_Finish": status_date,
                "Duration": "1d",
                "Pct_Complete": 0,
                "Actual_Start": None,
                "Actual_Finish": None,
                "Cost": 0,
                "Baseline_Cost": 0,
                "Work": 0,
                "Baseline_Work": 0,
                "Predecessors": "",
                "Resources": "",
                "Notes": "",
            }
        ],
    }


def test_health() -> None:
    client, _ = make_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["clickhouse"] is True


def test_snapshot_roundtrip_and_latest() -> None:
    client, repository = make_client()
    payload = {
        "project_name": "Пилот-2026",
        "status_date": "2026-02-01",
        "project_info": {
            "project_name": "Проект пДЦПД v3",
            "start_date": "2025-09-01",
            "finish_date": "2027-03-15",
        },
        "summary": {
            "total_tasks": 2,
            "summary_tasks": 1,
            "milestones": 0,
            "leaf_tasks": 1,
            "with_baseline": 2,
            "total_resources": 3,
        },
        "rows": [
            {
                "UID": 1,
                "ID": 1,
                "WBS": "1",
                "Name": "Подготовительный этап",
                "Level": 1,
                "Outline": "1",
                "Parent_UID": 0,
                "Summary": "Y",
                "Milestone": "N",
                "Start": "2025-09-01",
                "Finish": "2026-03-01",
                "Baseline_Start": "2025-09-01",
                "Baseline_Finish": "2026-02-15",
                "Duration": "130d",
                "Pct_Complete": 45,
                "Actual_Start": "2025-09-01",
                "Actual_Finish": None,
                "Cost": 0,
                "Baseline_Cost": 0,
                "Work": 0,
                "Baseline_Work": 0,
                "Predecessors": "",
                "Resources": "Иванов И.И.",
                "Notes": "",
            },
            {
                "UID": 2,
                "ID": 2,
                "WBS": "1.1",
                "Name": "Задача 2",
                "Level": 2,
                "Outline": "1.1",
                "Parent_UID": 1,
                "Summary": "N",
                "Milestone": "N",
                "Start": "2026-02-01",
                "Finish": "2026-02-10",
                "Baseline_Start": "2026-02-01",
                "Baseline_Finish": "2026-02-09",
                "Duration": "8d",
                "Pct_Complete": 0,
                "Actual_Start": None,
                "Actual_Finish": None,
                "Cost": 0,
                "Baseline_Cost": 0,
                "Work": 0,
                "Baseline_Work": 0,
                "Predecessors": "",
                "Resources": "",
                "Notes": "",
            },
        ],
    }

    response = client.post("/api/v1/snapshot", headers=auth_headers(), json=payload)
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert repository.get_latest_snapshot_version("Пилот-2026") == 1

    latest = client.get("/api/v1/snapshot/Пилот-2026/latest", headers=auth_headers())
    assert latest.status_code == 200
    assert latest.json()["meta"]["ms_project_name"] == "Проект пДЦПД v3"

    snapshot = client.get("/api/v1/snapshot/Пилот-2026/1", headers=auth_headers())
    assert snapshot.status_code == 200
    assert snapshot.json()["count"] == 2


def test_deltas_endpoint() -> None:
    client, _ = make_client()
    base_payload = {
        "project_name": "Пилот-2026",
        "status_date": "2026-01-15",
        "rows": [
            {
                "UID": 45,
                "ID": 45,
                "WBS": "1.3.2",
                "Name": "Подготовка ОТР",
                "Level": 2,
                "Outline": "1.3.2",
                "Parent_UID": 1,
                "Summary": "N",
                "Milestone": "N",
                "Start": "2026-02-01",
                "Finish": "2026-04-10",
                "Baseline_Start": "2026-02-01",
                "Baseline_Finish": "2026-03-30",
                "Duration": "10d",
                "Pct_Complete": 0,
                "Actual_Start": None,
                "Actual_Finish": None,
                "Cost": 0,
                "Baseline_Cost": 0,
                "Work": 0,
                "Baseline_Work": 0,
                "Predecessors": "",
                "Resources": "",
                "Notes": "",
            }
        ],
    }
    updated_payload = {
        **base_payload,
        "status_date": "2026-02-01",
        "rows": [
            {
                **base_payload["rows"][0],
                "Finish": "2026-04-28",
            },
            {
                "UID": 112,
                "ID": 112,
                "WBS": "1.4.7",
                "Name": "Повторный анализ образцов",
                "Level": 3,
                "Outline": "1.4.7",
                "Parent_UID": 1,
                "Summary": "N",
                "Milestone": "N",
                "Start": "2026-02-20",
                "Finish": "2026-03-10",
                "Baseline_Start": None,
                "Baseline_Finish": None,
                "Duration": "4d",
                "Pct_Complete": 0,
                "Actual_Start": None,
                "Actual_Finish": None,
                "Cost": 0,
                "Baseline_Cost": 0,
                "Work": 0,
                "Baseline_Work": 0,
                "Predecessors": "",
                "Resources": "",
                "Notes": "",
            },
        ],
    }

    client.post("/api/v1/snapshot", headers=auth_headers(), json=base_payload)
    client.post("/api/v1/snapshot", headers=auth_headers(), json=updated_payload)

    response = client.get("/api/v1/deltas/Пилот-2026/1/2", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["unchanged_count"] == 0
    assert body["added"][0]["uid"] == 112
    assert body["changed"][0]["change_type"] == "increase"
    assert body["changed"][0]["delta_finish_days"] == 18


def test_changelog_status_patch() -> None:
    client, _ = make_client()
    payload = {
        "project_name": "Пилот-2026",
        "entries": [
            {
                "log_id": "Пилот-2026_1_2_45",
                "snapshot_from": 1,
                "snapshot_to": 2,
                "date": "2026-02-01",
                "uid": 45,
                "wbs": "1.3.2",
                "name": "Подготовка ОТР",
                "level": 2,
                "change_type": "increase",
                "delta_start_days": 0,
                "delta_finish_days": 18,
                "delta_baseline_days": 29,
                "category_code": "DELAY-EXT",
                "technical_summary": "Задержка поставки",
                "impact_type": "Задержка",
                "confidence": 0.9,
                "warnings": "",
                "escalation_required": False,
                "expert_comment": "",
                "status": "Auto",
            }
        ],
    }
    create_response = client.post("/api/v1/changelog", headers=auth_headers(), json=payload)
    assert create_response.status_code == 200

    patch_response = client.patch(
        "/api/v1/changelog/Пилот-2026/Пилот-2026_1_2_45/status",
        headers=auth_headers(),
        json={
            "new_status": "Corrected",
            "category_code": "DELAY-INT",
            "expert_comment": "Уточнено",
        },
    )
    assert patch_response.status_code == 200

    list_response = client.get("/api/v1/changelog/Пилот-2026", headers=auth_headers())
    assert list_response.status_code == 200
    entry = list_response.json()["entries"][0]
    assert entry["status"] == "Corrected"
    assert entry["category_code"] == "DELAY-INT"


def test_admin_purge_requires_confirmation() -> None:
    client, _ = make_client()
    response = client.delete("/api/v1/admin/purge", headers=auth_headers())
    assert response.status_code == 400
    assert "X-Confirm" in response.json()["detail"]


def test_admin_purge_clears_data() -> None:
    client, repository = make_client()
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("Пилот-2026", "2026-02-01", 1),
    )
    response = client.delete(
        "/api/v1/admin/purge",
        headers={**auth_headers(), "X-Confirm": "PURGE-ALL"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "purge_all"
    assert repository.snapshot_rows == {}


def test_get_versions_and_delete_versions() -> None:
    client, repository = make_client()
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("ИМТГФА", "2026-04-26", 1),
    )
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("ИМТГФА", "2026-05-10", 2),
    )
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("ИМТГФА", "2026-05-20", 3),
    )
    client.post(
        "/api/v1/changelog",
        headers=auth_headers(),
        json={
            "project_name": "ИМТГФА",
            "entries": [
                {
                    "log_id": "ИМТГФА_2_3_3",
                    "snapshot_from": 2,
                    "snapshot_to": 3,
                    "date": "2026-05-20",
                    "uid": 3,
                    "wbs": "1",
                    "name": "Задача",
                    "level": 1,
                    "change_type": "increase",
                    "delta_start_days": 0,
                    "delta_finish_days": 10,
                    "delta_baseline_days": 10,
                    "category_code": "DELAY-EXT",
                    "technical_summary": "test",
                    "impact_type": "Задержка",
                    "confidence": 0.8,
                    "warnings": "",
                    "escalation_required": False,
                    "expert_comment": "",
                    "status": "Auto",
                }
            ],
        },
    )
    repository.insert_strategic_entries(
        [
            {
                "project_name": "ИМТГФА",
                "uid": 3,
                "wbs": "1",
                "name": "Задача",
                "summary": "Y",
                "baseline_finish": "2026-05-20",
                "current_finish": "2026-05-20",
                "delta_baseline_days": 0,
                "escalation": False,
                "ai_strategic_analysis": "",
                "snapshot_version": 3,
            }
        ]
    )

    versions_response = client.get("/api/v1/project/ИМТГФА/versions", headers=auth_headers())
    assert versions_response.status_code == 200
    assert [item["version"] for item in versions_response.json()["versions"]] == [1, 2, 3]
    assert versions_response.json()["versions"][1]["has_changelog"] is True

    delete_response = client.request(
        "DELETE",
        "/api/v1/project/ИМТГФА/versions",
        headers=auth_headers(),
        json={"versions": [2, 3]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_versions"] == [2, 3]
    assert delete_response.json()["remaining_versions"] == [1]
    assert delete_response.json()["changelog_entries_deleted"] == 1
    assert repository.project_meta["ИМТГФА"]["last_version"] == 1


def test_delete_versions_returns_missing_versions() -> None:
    client, _ = make_client()
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("ИМТГФА", "2026-04-26", 1),
    )
    response = client.request(
        "DELETE",
        "/api/v1/project/ИМТГФА/versions",
        headers=auth_headers(),
        json={"versions": [4, 5]},
    )
    assert response.status_code == 404
    assert "Версии не найдены" in response.json()["detail"]


def test_baseline_lifecycle_and_recalc() -> None:
    client, repository = make_client()
    project = "Пилот-2026"
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload(project, "2026-04-26", 10, name="Подготовка"),
    )

    save = client.post(
        "/api/v1/baseline",
        headers=auth_headers(),
        json={
            "project_name": project,
            "source_snapshot": 1,
            "entries": [
                {
                    "uid": 10,
                    "wbs": "1",
                    "name": "Подготовка",
                    "baseline_start": "2026-04-01",
                    "baseline_finish": "2026-04-26",
                    "baseline_source": "mpp_baseline_fields",
                }
            ],
        },
    )
    assert save.status_code == 200
    assert save.json()["entries_saved"] == 1

    listed = client.get(f"/api/v1/baseline/{project}", headers=auth_headers())
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["entries"][0]["baseline_source"] == "mpp_baseline_fields"

    # New snapshot with later finish
    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json={
            "project_name": project,
            "status_date": "2026-05-26",
            "rows": [
                {
                    "UID": 10,
                    "ID": 10,
                    "WBS": "1",
                    "Name": "Подготовка",
                    "Level": 1,
                    "Outline": "1",
                    "Parent_UID": 0,
                    "Summary": "Y",
                    "Milestone": "N",
                    "Start": "2026-04-01",
                    "Finish": "2026-05-20",
                    "Baseline_Start": "2026-04-01",
                    "Baseline_Finish": "2026-04-26",
                    "Duration": "1d",
                    "Pct_Complete": 0,
                    "Actual_Start": None,
                    "Actual_Finish": None,
                    "Cost": 0,
                    "Baseline_Cost": 0,
                    "Work": 0,
                    "Baseline_Work": 0,
                    "Predecessors": "",
                    "Resources": "",
                    "Notes": "",
                }
            ],
        },
    )

    recalc = client.post(
        f"/api/v1/strategic/{project}/recalc",
        headers=auth_headers(),
        json={"snapshot_version": 2},
    )
    assert recalc.status_code == 200
    body = recalc.json()
    assert body["entries_written"] == 1
    assert body["delays"] == 1
    assert body["escalations"] == 1

    strategic = client.get(f"/api/v1/strategic/{project}", headers=auth_headers())
    assert strategic.status_code == 200
    entry = strategic.json()["entries"][0]
    assert entry["delta_baseline_days"] == 24
    assert entry["escalation"] is True

    patched = client.patch(
        f"/api/v1/baseline/{project}",
        headers=auth_headers(),
        json={
            "source_snapshot": 2,
            "upsert": [
                {
                    "uid": 10,
                    "wbs": "1",
                    "name": "Подготовка",
                    "baseline_start": "2026-04-01",
                    "baseline_finish": "2026-05-30",
                    "baseline_source": "manual_form",
                }
            ],
            "remove": [],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["upserted"] == 1

    deleted = client.delete(f"/api/v1/baseline/{project}", headers=auth_headers())
    assert deleted.status_code == 200
    assert deleted.json()["entries_deleted"] == 1
    assert repository.baseline_entries.get(project, []) == []


def test_baseline_requires_existing_project() -> None:
    client, _ = make_client()
    response = client.post(
        "/api/v1/baseline",
        headers=auth_headers(),
        json={
            "project_name": "Нет",
            "source_snapshot": 1,
            "entries": [{"uid": 1, "name": "x"}],
        },
    )
    assert response.status_code == 404


def test_delete_project_not_found_and_success() -> None:
    client, repository = make_client()
    missing = client.delete("/api/v1/project/Несуществующий", headers=auth_headers())
    assert missing.status_code == 404

    client.post(
        "/api/v1/snapshot",
        headers=auth_headers(),
        json=build_snapshot_payload("Удаляемый", "2026-02-01", 1),
    )
    response = client.delete("/api/v1/project/Удаляемый", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["action"] == "delete_project"
    assert repository.get_latest_snapshot_version("Удаляемый") == 0
