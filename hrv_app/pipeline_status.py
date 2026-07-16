"""Structured status objects shared by the HRV pipeline and web adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


PIPELINE_RESULT_PREFIX = "##HRV_RESULT##"


@dataclass
class StageExecution:
    """Result of one executable pipeline stage."""

    stage: str
    status: str = "ok"
    outcome: str = "completed"
    returncode: int | None = 0
    stdout: str = ""
    stderr: str = ""
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def __bool__(self) -> bool:
        return self.ok

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "status": self.status,
            "outcome": self.outcome,
        }
        if self.returncode is not None:
            payload["returncode"] = self.returncode
        if self.error:
            payload["error"] = dict(self.error)
        return payload


@dataclass
class PipelineResult:
    """Terminal result propagated across the CLI subprocess boundary."""

    status: str = "ok"
    canonical_valid: bool = True
    stage: str = "preflight"
    date_from: str | None = None
    date_to: str | None = None
    processed_dates: list[str] = field(default_factory=list)
    uncovered_dates: list[str] = field(default_factory=list)
    pending_sleep_dates: list[str] = field(default_factory=list)
    source: dict[str, Any] = field(
        default_factory=lambda: {
            "name": "dropbox_rr",
            "status": "not_requested",
            "outcome": "not_applicable",
        }
    )
    error: dict[str, Any] | None = None
    degraded_stages: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status in {"ok", "degraded"}

    def _record_stage(
        self,
        stage: str,
        status: str,
        outcome: str = "completed",
        *,
        error: dict[str, Any] | None = None,
        returncode: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "stage": stage,
            "status": status,
            "outcome": outcome,
        }
        if returncode is not None:
            row["returncode"] = returncode
        if error:
            row["error"] = dict(error)
        row.update({k: v for k, v in extra.items() if v is not None})
        self.stages.append(row)
        self.stage = stage
        return row

    def ok(
        self,
        stage: str,
        outcome: str = "completed",
        *,
        returncode: int | None = None,
        **extra: Any,
    ) -> "PipelineResult":
        self._record_stage(stage, "ok", outcome, returncode=returncode, **extra)
        return self

    def not_requested(self, stage: str, outcome: str = "disabled") -> "PipelineResult":
        """Record an intentionally skipped optional stage without changing health."""
        self._record_stage(stage, "not_requested", outcome)
        return self

    def degrade(
        self,
        stage: str,
        outcome: str,
        code: str,
        message: str,
        *,
        returncode: int | None = None,
    ) -> "PipelineResult":
        row = self._record_stage(
            stage,
            "degraded",
            outcome,
            error={"code": code, "message": message},
            returncode=returncode,
        )
        if self.status != "failed":
            self.status = "degraded"
            self.degraded_stages.append(row)
        return self

    def set_source(self, *, status: str, outcome: str, **extra: Any) -> "PipelineResult":
        self.source = {
            "name": "dropbox_rr",
            "status": status,
            "outcome": outcome,
            **{k: v for k, v in extra.items() if v is not None},
        }
        return self

    def merge(self, other: Any) -> "PipelineResult":
        if not isinstance(other, PipelineResult):
            return self
        self.stages.extend(other.stages)
        self.degraded_stages.extend(other.degraded_stages)
        if other.stages and self.status != "failed":
            self.stage = other.stage
        if other.date_from is not None:
            self.date_from = other.date_from
        if other.date_to is not None:
            self.date_to = other.date_to
        if other.pending_sleep_dates:
            self.pending_sleep_dates = sorted(set(self.pending_sleep_dates) | set(other.pending_sleep_dates))
        if other.processed_dates:
            self.processed_dates = sorted(set(self.processed_dates) | set(other.processed_dates))
        if other.uncovered_dates:
            self.uncovered_dates = sorted(set(self.uncovered_dates) | set(other.uncovered_dates))
        other_source_is_meaningful = (
            other.source.get("status") != "not_requested"
            or other.source.get("outcome") != "not_applicable"
        )
        if other_source_is_meaningful and (
            self.source.get("status") != "not_requested"
            or self.source.get("outcome") == "not_applicable"
        ):
            self.source = dict(other.source)
        if other.status == "failed":
            self.status = "failed"
            self.canonical_valid = self.canonical_valid and other.canonical_valid
            self.stage = other.stage
            self.error = other.error
        elif other.status == "degraded" and self.status != "failed":
            self.status = "degraded"
        elif not other.canonical_valid:
            self.canonical_valid = False
        return self

    def fail(self, stage: str, code: str, message: str, *, returncode: int | None = None) -> "PipelineResult":
        row = self._record_stage(
            stage,
            "failed",
            "error",
            returncode=returncode,
            error={"code": code, "message": message},
        )
        self.status = "failed"
        self.error = dict(row["error"])
        self.canonical_valid = False
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "success": self.success,
            "canonical_valid": self.canonical_valid,
            "stage": self.stage,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "processed_dates": list(self.processed_dates),
            "uncovered_dates": list(self.uncovered_dates),
            "pending_sleep_dates": list(self.pending_sleep_dates),
            "source": dict(self.source),
            "source_status": self.source.get("status"),
            "source_outcome": self.source.get("outcome"),
            "error": dict(self.error) if self.error else None,
            "degraded_stages": list(self.degraded_stages),
            "stages": list(self.stages),
        }

    def emit_marker(self) -> str:
        line = PIPELINE_RESULT_PREFIX + json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
        print(line, flush=True)
        return line


def stage_from_execution(execution: Any, stage: str) -> StageExecution:
    """Normalize a real or mocked subprocess result into a stage execution."""

    if isinstance(execution, StageExecution):
        return execution
    ok = bool(execution) if execution is not None else False
    stdout = str(getattr(execution, "stdout", "") or "")
    stderr = str(getattr(execution, "stderr", "") or "")
    return StageExecution(
        stage=stage,
        status="ok" if ok else "failed",
        outcome="completed" if ok else "error",
        returncode=getattr(execution, "returncode", 0 if ok else 1),
        stdout=stdout,
        stderr=stderr,
        error=None if ok else {"code": f"{stage}_failed", "message": f"Fallo en {stage}"},
    )


def result_from_marker(stdout: str) -> dict[str, Any] | None:
    """Parse exactly one valid terminal marker from captured stdout."""

    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip().startswith(PIPELINE_RESULT_PREFIX)]
    if len(lines) != 1:
        return None
    try:
        payload = json.loads(lines[0][len(PIPELINE_RESULT_PREFIX):])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if _is_valid_pipeline_payload(payload) else None


def _is_valid_pipeline_payload(payload: Any) -> bool:
    """Validate the terminal CLI contract before trusting it in the UI."""
    if not isinstance(payload, dict):
        return False

    status = payload.get("status")
    if status not in {"ok", "degraded", "failed"}:
        return False
    expected_success = status in {"ok", "degraded"}
    if payload.get("success") is not expected_success:
        return False
    if payload.get("canonical_valid") is not expected_success:
        return False
    if not isinstance(payload.get("stage"), str) or not payload["stage"].strip():
        return False

    for key in ("date_from", "date_to"):
        if payload.get(key) is not None and not isinstance(payload.get(key), str):
            return False
    for key in ("processed_dates", "uncovered_dates", "pending_sleep_dates"):
        if not isinstance(payload.get(key), list) or not all(isinstance(item, str) for item in payload[key]):
            return False

    source = payload.get("source")
    if not isinstance(source, dict):
        return False
    if not isinstance(source.get("name"), str) or not source["name"].strip():
        return False
    if source.get("status") not in {"not_requested", "ok", "failed"}:
        return False
    if not isinstance(source.get("outcome"), str) or not source["outcome"].strip():
        return False
    if payload.get("source_status") != source["status"] or payload.get("source_outcome") != source["outcome"]:
        return False

    error = payload.get("error")
    if status == "failed":
        if not isinstance(error, dict) or not all(isinstance(error.get(key), str) and error[key].strip() for key in ("code", "message")):
            return False
    elif error is not None:
        return False

    degraded_stages = payload.get("degraded_stages")
    stages = payload.get("stages")
    if not isinstance(degraded_stages, list) or not all(isinstance(item, dict) for item in degraded_stages):
        return False
    if not isinstance(stages, list) or not all(isinstance(item, dict) for item in stages):
        return False
    if status == "degraded" and not degraded_stages:
        return False
    return True
