from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io_utils import json_safe, write_json_atomic


MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_KIND = "hrv_run_manifest"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json_dumps(payload: object) -> str:
    return json.dumps(
        json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def stable_digest(payload: object) -> str:
    return hashlib.sha256(_stable_json_dumps(payload).encode("utf-8")).hexdigest()


def file_digest(path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def artifact_signature(
    path: Path,
    *,
    role: str,
    row_count: int | None = None,
    column_count: int | None = None,
    extra: Mapping[str, Any] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    signature: dict[str, Any] = {
        "role": role,
        "path": str(path),
        "name": path.name,
        "exists": path.exists(),
    }
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        if extra:
            signature.update(json_safe(dict(extra)))
        return signature

    stat = path.stat()
    signature["sha256"] = file_digest(path)
    signature["size_bytes"] = stat.st_size
    if row_count is not None:
        signature["row_count"] = int(row_count)
    if column_count is not None:
        signature["column_count"] = int(column_count)
    if extra:
        signature.update(json_safe(dict(extra)))
    return signature


def build_run_manifest(
    *,
    stage: str,
    builder: str,
    builder_revision: str,
    data_dir: Path,
    effective_config: Mapping[str, Any],
    inputs: Sequence[Mapping[str, Any]],
    outputs: Sequence[Mapping[str, Any]],
    extra: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config_payload = json_safe(dict(effective_config))
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_kind": MANIFEST_KIND,
        "stage": stage,
        "builder": builder,
        "builder_revision": builder_revision,
        "generated_at": generated_at or utc_now_iso(),
        "data_dir": str(data_dir),
        "effective_config": config_payload,
        "effective_config_hash": stable_digest(config_payload),
        "inputs": [json_safe(dict(item)) for item in inputs],
        "outputs": [json_safe(dict(item)) for item in outputs],
    }
    if extra:
        manifest.update(json_safe(dict(extra)))
    return manifest


def write_run_manifest_atomic(manifest: Mapping[str, Any], path: Path) -> None:
    write_json_atomic(manifest, path)
