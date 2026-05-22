from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CHANGE_TYPES = {"add", "remove", "rename", "reduction", "increase", "postpone"}
CHANGE_STATUSES = {"Auto", "Pending", "Confirmed", "Corrected"}
CATEGORY_CODES = {
    "OPT-TECH",
    "OPT-RES",
    "OPT-SCOPE",
    "DELAY-EXT",
    "DELAY-INT",
    "DELAY-TECH",
    "SCOPE-ADD",
    "REPLAN",
    "UNKNOWN",
}
NULLISH_DATE_VALUES = {"", "NA", "None", "null", "1970-01-01"}


def normalize_nullable_date(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() in NULLISH_DATE_VALUES:
        return None
    return value


class BaseSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ProjectInfoIn(BaseSchema):
    project_name: str = ""
    start_date: date | None = None
    finish_date: date | None = None

    _normalize_dates = field_validator("start_date", "finish_date", mode="before")(
        normalize_nullable_date
    )


class SummaryIn(BaseSchema):
    total_tasks: int = 0
    summary_tasks: int = 0
    milestones: int = 0
    leaf_tasks: int = 0
    with_baseline: int = 0
    total_resources: int = 0


class SnapshotRowIn(BaseSchema):
    uid: int = Field(alias="UID")
    id: int = Field(default=0, alias="ID")
    wbs: str = Field(default="", alias="WBS")
    name: str = Field(alias="Name")
    level: int = Field(default=0, alias="Level")
    outline: str = Field(default="", alias="Outline")
    parent_uid: int = Field(default=0, alias="Parent_UID")
    summary: str = Field(default="N", alias="Summary")
    milestone: str = Field(default="N", alias="Milestone")
    start: date | None = Field(default=None, alias="Start")
    finish: date | None = Field(default=None, alias="Finish")
    baseline_start: date | None = Field(default=None, alias="Baseline_Start")
    baseline_finish: date | None = Field(default=None, alias="Baseline_Finish")
    duration: str = Field(default="", alias="Duration")
    pct_complete: int = Field(default=0, alias="Pct_Complete")
    actual_start: date | None = Field(default=None, alias="Actual_Start")
    actual_finish: date | None = Field(default=None, alias="Actual_Finish")
    cost: float = Field(default=0, alias="Cost")
    baseline_cost: float = Field(default=0, alias="Baseline_Cost")
    work: float = Field(default=0, alias="Work")
    baseline_work: float = Field(default=0, alias="Baseline_Work")
    predecessors: str = Field(default="", alias="Predecessors")
    resources: str = Field(default="", alias="Resources")
    notes: str = Field(default="", alias="Notes")

    _normalize_dates = field_validator(
        "start",
        "finish",
        "baseline_start",
        "baseline_finish",
        "actual_start",
        "actual_finish",
        mode="before",
    )(normalize_nullable_date)


class SnapshotRequest(BaseSchema):
    project_name: str
    status_date: date
    project_info: ProjectInfoIn | None = None
    summary: SummaryIn | None = None
    rows: list[SnapshotRowIn]


class ChangelogEntryIn(BaseSchema):
    log_id: str
    snapshot_from: int
    snapshot_to: int
    date: date
    uid: int
    wbs: str = ""
    name: str = ""
    level: int = 0
    change_type: Literal["add", "remove", "rename", "reduction", "increase", "postpone"]
    delta_start_days: int = 0
    delta_finish_days: int = 0
    delta_baseline_days: int = 0
    category_code: str = "UNKNOWN"
    technical_summary: str = ""
    impact_type: str = ""
    confidence: float = 0.0
    warnings: str = ""
    escalation_required: bool = False
    expert_comment: str = ""
    status: Literal["Auto", "Pending", "Confirmed", "Corrected"]

    @field_validator("category_code")
    @classmethod
    def validate_category_code(cls, value: str) -> str:
        if value not in CATEGORY_CODES:
            raise ValueError("Unsupported category_code")
        return value


class ChangelogRequest(BaseSchema):
    project_name: str
    entries: list[ChangelogEntryIn]


class ChangelogStatusPatchRequest(BaseSchema):
    new_status: Literal["Auto", "Pending", "Confirmed", "Corrected"]
    category_code: str | None = None
    expert_comment: str | None = None

    @field_validator("category_code")
    @classmethod
    def validate_optional_category_code(cls, value: str | None) -> str | None:
        if value is not None and value not in CATEGORY_CODES:
            raise ValueError("Unsupported category_code")
        return value


class StrategicEntryIn(BaseSchema):
    uid: int
    wbs: str = ""
    name: str
    summary: str = "N"
    baseline_finish: date | None = None
    current_finish: date | None = None
    delta_baseline_days: int = 0
    escalation: bool = False
    ai_strategic_analysis: str = ""

    _normalize_dates = field_validator(
        "baseline_finish", "current_finish", mode="before"
    )(normalize_nullable_date)


class StrategicRequest(BaseSchema):
    project_name: str
    snapshot_version: int
    entries: list[StrategicEntryIn]
