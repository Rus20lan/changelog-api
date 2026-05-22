from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

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
        self.classifier_codes = [{"code": "UNKNOWN", "category": "Нет данных"}]

    def list_tables(self) -> list[str]:
        return self.tables

    def get_latest_snapshot_version(self, project_name: str) -> int:
        versions = [version for current_project, version in self.snapshot_rows if current_project == project_name]
        return max(versions, default=0)

    def insert_snapshot_rows(self, rows: list[dict], batch_size: int = 100) -> None:
        for row in rows:
            key = (row["project_name"], row["snapshot_version"])
            self.snapshot_rows.setdefault(key, []).append(row)

    def upsert_project_meta(self, meta: dict) -> None:
        self.project_meta[meta["project_name"]] = {
            **meta,
            "last_parsed_at": "2026-05-22T10:00:00",
            "updated_at": "2026-05-22T10:00:00",
        }

    def get_project_meta(self, project_name: str) -> dict | None:
        return self.project_meta.get(project_name)

    def get_snapshot_rows(self, project_name: str, version: int, limit: int | None = None) -> list[dict]:
        rows = self.snapshot_rows.get((project_name, version), [])
        prepared = []
        for row in rows[: limit or None]:
            prepared.append(
                {
                    **row,
                    "status_date": row["status_date"].isoformat(),
                    "start": row["start"].isoformat() if row["start"] else None,
                    "finish": row["finish"].isoformat() if row["finish"] else None,
                    "baseline_start": row["baseline_start"].isoformat() if row["baseline_start"] else None,
                    "baseline_finish": row["baseline_finish"].isoformat() if row["baseline_finish"] else None,
                    "actual_start": row["actual_start"].isoformat() if row["actual_start"] else None,
                    "actual_finish": row["actual_finish"].isoformat() if row["actual_finish"] else None,
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
                "baseline_finish": entry["baseline_finish"].isoformat() if entry["baseline_finish"] else None,
                "current_finish": entry["current_finish"].isoformat() if entry["current_finish"] else None,
                "updated_at": "2026-05-22T10:00:00",
            }
            for entry in entries
        ]

    def list_strategic(self, project_name: str) -> list[dict]:
        return self.strategic_entries.get(project_name, [])

    def list_classifier_codes(self) -> list[dict]:
        return self.classifier_codes


def make_client() -> tuple[TestClient, FakeRepository]:
    repository = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app), repository


def auth_headers() -> dict[str, str]:
    return {"X-Api-Key": "dev-api-key-please-change-me-32chars"}


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
