from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io_utils import json_safe, write_json_atomic


MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_KIND = "hrv_run_manifest"
CORE_FILENAME = "ENDURANCE_HRV_master_CORE.csv"
BETA_AUDIT_FILENAME = "ENDURANCE_HRV_master_BETA_AUDIT.csv"
FINAL_FILENAME = "ENDURANCE_HRV_master_FINAL.csv"
DASHBOARD_FILENAME = "ENDURANCE_HRV_master_DASHBOARD.csv"
CORE_MANIFEST_FILENAME = "ENDURANCE_HRV_master_CORE_manifest.json"
FINAL_MANIFEST_FILENAME = "ENDURANCE_HRV_master_FINAL_manifest.json"
GENERATION_FILENAMES = (
    CORE_FILENAME,
    BETA_AUDIT_FILENAME,
    FINAL_FILENAME,
    DASHBOARD_FILENAME,
    CORE_MANIFEST_FILENAME,
    FINAL_MANIFEST_FILENAME,
)


class GenerationCoherenceError(RuntimeError):
    """The on-disk HRV generation cannot safely be presented to consumers."""

    code = "generation_incoherent"

    def __init__(self, reason: str = "faltan archivos o no se pueden leer") -> None:
        self.reason = reason
        super().__init__(f"Generación HRV incoherente: {reason}")


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


def _manifest_payload(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationCoherenceError("manifest ilegible") from exc
    if not isinstance(payload, dict):
        raise GenerationCoherenceError("estructura de manifest inválida")
    return payload


def _output_sha256(manifest: Mapping[str, Any], role: str) -> str:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise GenerationCoherenceError("salidas del manifest ausentes")
    for output in outputs:
        if isinstance(output, Mapping) and output.get("role") == role:
            digest = output.get("sha256")
            if isinstance(digest, str) and digest:
                return digest
    raise GenerationCoherenceError(f"salida {role} ausente o sin hash")


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GenerationCoherenceError(f"campo {key} ausente en manifest")
    return value


def generation_present(data_dir: Path) -> bool:
    """¿Hay algo de una generación HRV en `data_dir`?

    Un directorio sin ninguno de esos archivos no es una generación incoherente:
    es un directorio sin generación (solo sesiones y sueño, o recién creado), y
    quien lee o respalda no debe tratarlo como un fallo.
    """
    data_dir = Path(data_dir)
    return any((data_dir / name).exists() for name in GENERATION_FILENAMES)


def verify_generation_coherence(data_dir: Path) -> None:
    """Fail closed unless CORE/BETA and FINAL/DASHBOARD match their manifests."""
    data_dir = Path(data_dir)
    core_path = data_dir / CORE_FILENAME
    beta_audit_path = data_dir / BETA_AUDIT_FILENAME
    final_path = data_dir / FINAL_FILENAME
    dashboard_path = data_dir / DASHBOARD_FILENAME
    core_manifest_path = data_dir / CORE_MANIFEST_FILENAME
    final_manifest_path = data_dir / FINAL_MANIFEST_FILENAME

    try:
        core_manifest_bytes = core_manifest_path.read_bytes()
        core_manifest = _manifest_payload(core_manifest_bytes)
        final_manifest = _manifest_payload(final_manifest_path.read_bytes())

        if _required_string(final_manifest, "source_manifest_sha256") != hashlib.sha256(core_manifest_bytes).hexdigest():
            raise GenerationCoherenceError("linaje CORE→FINAL desalineado")
        if (
            _required_string(final_manifest, "source_manifest_effective_config_hash")
            != _required_string(core_manifest, "effective_config_hash")
        ):
            raise GenerationCoherenceError("configuración CORE→FINAL desalineada")
        if file_digest(core_path) != _output_sha256(core_manifest, "core"):
            raise GenerationCoherenceError("hash CORE no coincide")
        if file_digest(beta_audit_path) != _output_sha256(core_manifest, "beta_audit"):
            raise GenerationCoherenceError("hash BETA_AUDIT no coincide")
        if file_digest(final_path) != _output_sha256(final_manifest, "final"):
            raise GenerationCoherenceError("hash FINAL no coincide")
        if file_digest(dashboard_path) != _output_sha256(final_manifest, "dashboard"):
            raise GenerationCoherenceError("hash DASHBOARD no coincide")
    except GenerationCoherenceError:
        raise
    except OSError as exc:
        raise GenerationCoherenceError() from exc
