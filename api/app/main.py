from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth import verify_api_key
from .logic import build_project_meta, build_snapshot_rows, compute_deltas
from .models import (
    CHANGE_STATUSES,
    ChangelogRequest,
    ChangelogStatusPatchRequest,
    SnapshotRequest,
    StrategicRequest,
)
from .repository import ClickHouseError, ClickHouseRepository, get_repository

RepositoryDep = Annotated[ClickHouseRepository, Depends(get_repository)]
AuthDep = Annotated[str, Depends(verify_api_key)]


def create_app() -> FastAPI:
    app = FastAPI(title="Changelog API", version="1.0.0")

    @app.exception_handler(ClickHouseError)
    async def clickhouse_error_handler(_: Request, exc: ClickHouseError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        messages = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", []) if part != "body")
            if loc:
                messages.append(f"{loc}: {error['msg']}")
            else:
                messages.append(error["msg"])
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "; ".join(messages) or "Invalid request"},
        )

    @app.get("/api/v1/health")
    def health(repository: RepositoryDep) -> dict[str, Any]:
        try:
            tables = repository.list_tables()
            clickhouse_ok = True
        except ClickHouseError:
            tables = []
            clickhouse_ok = False
        return {
            "status": "ok" if clickhouse_ok else "degraded",
            "clickhouse": clickhouse_ok,
            "tables": tables,
            "timestamp": datetime.utcnow().replace(microsecond=0).isoformat(),
        }

    @app.post("/api/v1/snapshot")
    def save_snapshot(
        payload: SnapshotRequest, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        if not payload.rows:
            raise HTTPException(status_code=400, detail="rows must not be empty")

        previous_version = repository.get_latest_snapshot_version(payload.project_name)
        version = previous_version + 1

        snapshot_rows = build_snapshot_rows(payload, version)
        repository.insert_snapshot_rows(snapshot_rows)
        repository.upsert_project_meta(build_project_meta(payload, version))

        has_previous = previous_version > 0
        message = (
            f"Снепшот v{version} сохранён. Задач: {len(payload.rows)}. "
            + ("Доступен расчёт дельт." if has_previous else "Это первая версия проекта.")
        )
        return {
            "status": "ok",
            "project_name": payload.project_name,
            "version": version,
            "tasks_saved": len(payload.rows),
            "has_previous": has_previous,
            "message": message,
        }

    @app.get("/api/v1/snapshot/{project_name}/latest")
    def get_latest_snapshot(
        project_name: str, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        meta = repository.get_project_meta(project_name)
        if meta is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "project_name": project_name,
            "latest_version": meta["last_version"],
            "meta": meta,
        }

    @app.get("/api/v1/snapshot/{project_name}/{version}")
    def get_snapshot(
        project_name: str,
        version: int,
        _: AuthDep,
        repository: RepositoryDep,
        limit: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        total_count = repository.get_snapshot_total_count(project_name, version)
        if total_count == 0:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        rows = repository.get_snapshot_rows(project_name, version, limit=limit)
        return {
            "project_name": project_name,
            "version": version,
            "count": total_count,
            "rows": rows,
        }

    @app.get("/api/v1/deltas/{project_name}/{v_from}/{v_to}")
    def get_deltas(
        project_name: str,
        v_from: int,
        v_to: int,
        _: AuthDep,
        repository: RepositoryDep,
    ) -> dict[str, Any]:
        rows_from = repository.get_snapshot_rows(project_name, v_from)
        rows_to = repository.get_snapshot_rows(project_name, v_to)
        if not rows_from or not rows_to:
            raise HTTPException(status_code=404, detail="Snapshot version not found")

        status_date_from = repository.get_snapshot_status_date(project_name, v_from)
        status_date_to = repository.get_snapshot_status_date(project_name, v_to)
        return compute_deltas(
            project_name=project_name,
            version_from=v_from,
            version_to=v_to,
            status_date_from=status_date_from or "",
            status_date_to=status_date_to or "",
            rows_from=rows_from,
            rows_to=rows_to,
        )

    @app.post("/api/v1/changelog")
    def save_changelog(
        payload: ChangelogRequest, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        if not payload.entries:
            raise HTTPException(status_code=400, detail="entries must not be empty")
        entries = []
        for entry in payload.entries:
            entries.append(
                {
                    "project_name": payload.project_name,
                    **entry.model_dump(),
                }
            )
        repository.insert_changelog_entries(entries)
        return {"status": "ok", "entries_saved": len(entries)}

    @app.patch("/api/v1/changelog/{project_name}/{log_id}/status")
    def patch_changelog_status(
        project_name: str,
        log_id: str,
        payload: ChangelogStatusPatchRequest,
        _: AuthDep,
        repository: RepositoryDep,
    ) -> dict[str, Any]:
        existing = repository.get_changelog_entry(project_name, log_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Change log entry not found")

        existing["status"] = payload.new_status
        if payload.category_code is not None:
            existing["category_code"] = payload.category_code
        if payload.expert_comment is not None:
            existing["expert_comment"] = payload.expert_comment
        existing.pop("updated_at", None)

        repository.insert_changelog_entries([existing])
        return {"status": "ok", "log_id": log_id, "new_status": payload.new_status}

    @app.get("/api/v1/changelog/{project_name}")
    def get_changelog(
        project_name: str,
        _: AuthDep,
        repository: RepositoryDep,
        snapshot_from: int | None = Query(default=None, ge=1),
        snapshot_to: int | None = Query(default=None, ge=1),
        status_filter: str | None = Query(default=None),
    ) -> dict[str, Any]:
        if status_filter is not None and status_filter not in CHANGE_STATUSES:
            raise HTTPException(status_code=400, detail="Unsupported status_filter")
        entries = repository.list_changelog(
            project_name,
            snapshot_from=snapshot_from,
            snapshot_to=snapshot_to,
            status_filter=status_filter,
        )
        return {
            "project_name": project_name,
            "count": len(entries),
            "entries": entries,
        }

    @app.post("/api/v1/strategic")
    def save_strategic(
        payload: StrategicRequest, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        if not payload.entries:
            raise HTTPException(status_code=400, detail="entries must not be empty")

        entries = []
        for entry in payload.entries:
            entries.append(
                {
                    "project_name": payload.project_name,
                    "snapshot_version": payload.snapshot_version,
                    **entry.model_dump(),
                }
            )
        repository.insert_strategic_entries(entries)
        return {"status": "ok", "entries_saved": len(entries)}

    @app.get("/api/v1/strategic/{project_name}")
    def get_strategic(
        project_name: str, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        entries = repository.list_strategic(project_name)
        return {"project_name": project_name, "count": len(entries), "entries": entries}

    @app.get("/api/v1/meta/{project_name}")
    def get_meta(
        project_name: str, _: AuthDep, repository: RepositoryDep
    ) -> dict[str, Any]:
        meta = repository.get_project_meta(project_name)
        if meta is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return meta

    @app.get("/api/v1/classifier")
    def get_classifier(_: AuthDep, repository: RepositoryDep) -> dict[str, Any]:
        return {"codes": repository.list_classifier_codes()}

    return app


app = create_app()
