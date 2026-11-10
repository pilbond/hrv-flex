# -*- coding: utf-8 -*-
"""Backup opcional de los artefactos canónicos a Dropbox tras un sync exitoso.

El histórico del atleta vive en un único volumen (Railway); el sueño y el
wellness subjetivo no son regenerables desde las APIs si ese volumen se pierde.
Este módulo sube los `ENDURANCE_HRV_*.csv` / `*.json` de `DATA_DIR`, más el
histórico IA en `DATA_DIR/ai_briefs/`, a Dropbox sobrescribiendo cada archivo
(sin versionado propio: Dropbox ya conserva versiones anteriores de cada
archivo).

Contrato operativo:
- Opt-in vía `HRV_BACKUP_DROPBOX_ENABLED` (default off).
- Reutiliza las credenciales Dropbox ya configuradas para la ingesta RR
  (`DROPBOX_ACCESS_TOKEN` o `DROPBOX_REFRESH_TOKEN` + `DROPBOX_APP_KEY` +
  `DROPBOX_APP_SECRET`).
- NUNCA lanza: cualquier fallo se reporta como warning y el sync continúa.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path, PurePosixPath

import requests

from .config import DATA_DIR
from .polar_utils import env_flag

_UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
_CREATE_FOLDER_URL = "https://api.dropboxapi.com/2/files/create_folder_v2"
_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
_LIST_FOLDER_CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"
_DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"
_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

_TIMEOUT_SEC = 60

_RESTORE_REQUIRED_CSVS = (
    "ENDURANCE_HRV_master_CORE.csv",
    "ENDURANCE_HRV_master_BETA_AUDIT.csv",
    "ENDURANCE_HRV_master_FINAL.csv",
    "ENDURANCE_HRV_master_DASHBOARD.csv",
    "ENDURANCE_HRV_sleep.csv",
)
_CORE_REQUIRED_COLUMNS = {"Fecha", "Calidad", "HR_stable", "RMSSD_stable", "lnRMSSD"}


def _warn(message: str) -> None:
    print(f"[WARN] Backup Dropbox: {message}", file=sys.stderr)


def backup_enabled() -> bool:
    return env_flag("HRV_BACKUP_DROPBOX_ENABLED", default=False)


def _backup_root() -> str:
    raw = (os.environ.get("HRV_BACKUP_DROPBOX_PATH") or "/hrv_backups").strip() or "/hrv_backups"
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/")


def _get_access_token() -> str | None:
    """Token Dropbox desde el entorno; mismo esquema que la ingesta RR."""
    access_token = (os.environ.get("DROPBOX_ACCESS_TOKEN") or "").strip()
    refresh_token = (os.environ.get("DROPBOX_REFRESH_TOKEN") or "").strip()
    app_key = (os.environ.get("DROPBOX_APP_KEY") or "").strip()
    app_secret = (os.environ.get("DROPBOX_APP_SECRET") or "").strip()

    if refresh_token and app_key and app_secret:
        try:
            resp = requests.post(
                _TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=(app_key, app_secret),
                timeout=30,
            )
            if resp.status_code == 200:
                token = (resp.json().get("access_token") or "").strip()
                if token:
                    return token
            _warn(f"refresh de token falló ({resp.status_code}); se intenta token directo")
        except requests.RequestException as exc:
            _warn(f"refresh de token falló por red ({exc}); se intenta token directo")

    return access_token or None


def _canonical_files() -> list[Path]:
    files = sorted(DATA_DIR.glob("ENDURANCE_HRV_*.csv")) + sorted(DATA_DIR.glob("ENDURANCE_HRV_*.json"))
    ai_briefs_dir = DATA_DIR / "ai_briefs"
    if ai_briefs_dir.exists():
        files.extend(sorted(ai_briefs_dir.rglob("ENDURANCE_HRV_*.json")))
    return [p for p in files if p.is_file()]


def _backup_relative_path(path: Path) -> str:
    return path.relative_to(DATA_DIR).as_posix()


def _safe_relative_path(raw_path: str) -> str | None:
    rel = str(raw_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    parts = PurePosixPath(rel).parts
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        return None
    return PurePosixPath(*parts).as_posix()


def _core_row_count(data_dir: Path | None = None) -> int | None:
    """Cuenta filas utiliables del CORE; None si el archivo no se puede leer."""
    target_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    core_path = target_dir / "ENDURANCE_HRV_master_CORE.csv"
    if not core_path.exists():
        return 0
    try:
        with core_path.open("r", encoding="utf-8", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except (OSError, ValueError, UnicodeDecodeError, csv.Error):
        return None


def _validate_restore_set(directory: Path) -> None:
    """Require the complete operational dataset before making it visible."""
    for name in _RESTORE_REQUIRED_CSVS:
        path = directory / name
        if not path.is_file():
            raise RuntimeError(f"Falta el canónico obligatorio {name}")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, strict=True)
                header = next(reader, None)
                if not header or not any(field.strip() for field in header):
                    raise ValueError("sin cabecera CSV")
                rows = [row for row in reader if row]
                if name == "ENDURANCE_HRV_master_CORE.csv":
                    if any(len(row) != len(header) for row in rows):
                        raise ValueError("filas CORE con distinto número de columnas")
                    missing = _CORE_REQUIRED_COLUMNS - set(header)
                    if missing:
                        raise ValueError(f"CORE sin columnas obligatorias: {sorted(missing)}")
                    if not rows:
                        raise ValueError("CORE sin filas")
                    fecha_index = header.index("Fecha")
                    valid_date_found = False
                    for row in rows:
                        fecha = row[fecha_index].strip()
                        try:
                            valid_date_found = date.fromisoformat(fecha).isoformat() == fecha
                        except ValueError:
                            continue
                        if valid_date_found:
                            break
                    if not valid_date_found:
                        raise ValueError("CORE sin fila con Fecha válida")
        except Exception as exc:
            raise RuntimeError(f"Canónico ilegible o inválido {name}: {exc}") from exc


def _publish_restore_set(staging_dir: Path, target_dir: Path, names: list[str]) -> list[str]:
    """Publish staged files atomically per file and roll back on any failure."""
    from .io_utils import _replace_atomic

    backup_dir = target_dir / "backup" / "pre_restore"
    existed: dict[str, bool] = {}
    backed_up: list[str] = []
    published: list[str] = []
    try:
        for name in names:
            dest = target_dir / Path(name)
            existed[name] = dest.exists()
            if dest.exists():
                durable = backup_dir / Path(name)
                durable.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, durable)
                backed_up.append(name)
        for name in names:
            dest = target_dir / Path(name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f"{dest.name}.", suffix=".tmp")
            os.close(fd)
            tmp_path = Path(tmp)
            try:
                shutil.copyfile(staging_dir / Path(name), tmp_path)
                _replace_atomic(tmp_path, dest)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
            published.append(name)
    except Exception as exc:
        rollback_errors = []
        for name in reversed(published):
            dest = target_dir / Path(name)
            try:
                if existed[name]:
                    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f"{dest.name}.", suffix=".rollback")
                    os.close(fd)
                    tmp_path = Path(tmp)
                    try:
                        shutil.copyfile(backup_dir / Path(name), tmp_path)
                        _replace_atomic(tmp_path, dest)
                    finally:
                        if tmp_path.exists():
                            try:
                                tmp_path.unlink()
                            except OSError:
                                pass
                elif dest.exists():
                    dest.unlink()
            except Exception as rollback_exc:
                rollback_errors.append(f"{name}: {rollback_exc}")
        suffix = f"; rollback incompleto: {'; '.join(rollback_errors)}" if rollback_errors else ""
        raise RuntimeError(f"Falló la publicación del restore: {exc}{suffix}") from exc
    return backed_up


def _upload_file(token: str, local_path: Path, dropbox_path: str) -> bool:
    api_arg = json.dumps(
        {"path": dropbox_path, "mode": "overwrite", "mute": True},
        ensure_ascii=True,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": api_arg,
        "Content-Type": "application/octet-stream",
    }
    resp = requests.post(_UPLOAD_URL, headers=headers, data=local_path.read_bytes(), timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        _warn(f"upload de {local_path.name} falló ({resp.status_code})")
        return False
    return True


def _ensure_dropbox_folder(token: str, folder: str) -> bool:
    """Crea una carpeta Dropbox si no existe; un conflicto de carpeta es válido."""
    resp = requests.post(
        _CREATE_FOLDER_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"path": folder, "autorename": False},
        timeout=_TIMEOUT_SEC,
    )
    if resp.status_code == 200:
        return True
    if resp.status_code == 409:
        try:
            error_summary = str(resp.json().get("error_summary") or "")
        except (ValueError, TypeError):
            error_summary = ""
        if error_summary.startswith("path/conflict/folder"):
            return True
    _warn(f"creación de carpeta {folder} falló ({resp.status_code})")
    return False


def _dropbox_parent_dirs(dropbox_path: str) -> list[str]:
    parent = PurePosixPath(dropbox_path).parent
    dirs: list[str] = []
    for index in range(1, len(parent.parts) + 1):
        candidate = PurePosixPath(*parent.parts[:index]).as_posix()
        if candidate != "/":
            dirs.append(candidate)
    return dirs


def _entry_relative_path(entry: dict, root: str) -> str | None:
    path_display = str(entry.get("path_display") or "")
    root_prefix = root.rstrip("/") + "/"
    if path_display.startswith(root_prefix):
        return _safe_relative_path(path_display[len(root_prefix):])
    return _safe_relative_path(str(entry.get("name") or ""))


def _list_folder_files(token: str, folder: str, *, recursive: bool = False) -> list[str]:
    """Lista los archivos (no carpetas) dentro de una carpeta de Dropbox."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = _LIST_FOLDER_URL
    payload = {"path": folder, "recursive": recursive}
    files: list[str] = []
    while True:
        resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT_SEC)
        if resp.status_code != 200:
            # 409 típico cuando la carpeta aún no existe: no hay nada que listar.
            return []
        response_json = resp.json()
        entries = response_json.get("entries", [])
        files.extend(
            rel_path
            for e in entries
            if e.get(".tag") == "file"
            for rel_path in [_entry_relative_path(e, folder)]
            if rel_path is not None
        )
        if not response_json.get("has_more"):
            return files
        cursor = str(response_json.get("cursor") or "").strip()
        if not cursor:
            return []
        url = _LIST_FOLDER_CONTINUE_URL
        payload = {"cursor": cursor}


def _download_file(token: str, dropbox_path: str) -> bytes | None:
    api_arg = json.dumps({"path": dropbox_path}, ensure_ascii=True)
    headers = {"Authorization": f"Bearer {token}", "Dropbox-API-Arg": api_arg}
    resp = requests.post(_DOWNLOAD_URL, headers=headers, timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        _warn(f"descarga de {dropbox_path} falló ({resp.status_code})")
        return None
    return resp.content


def run_backup() -> dict:
    """Sube los artefactos canónicos a Dropbox (sobrescribiendo). Nunca lanza."""
    if not backup_enabled():
        return {"status": "disabled"}

    try:
        token = _get_access_token()
        if not token:
            _warn("sin credenciales (DROPBOX_ACCESS_TOKEN o refresh trio); se omite backup")
            return {"status": "no_credentials"}

        files = _canonical_files()
        if not files:
            _warn(f"no hay artefactos ENDURANCE_HRV_* en {DATA_DIR}; se omite backup")
            return {"status": "no_files"}

        root = _backup_root()
        uploaded = 0
        failed = 0
        ensured_dirs: set[str] = set()
        for path in files:
            dropbox_path = f"{root}/{_backup_relative_path(path)}"
            parent_dirs = _dropbox_parent_dirs(dropbox_path)
            folders_ready = True
            for folder in parent_dirs:
                if folder in ensured_dirs:
                    continue
                if not _ensure_dropbox_folder(token, folder):
                    folders_ready = False
                    break
                ensured_dirs.add(folder)
            if not folders_ready:
                failed += 1
                continue
            if _upload_file(token, path, dropbox_path):
                uploaded += 1
            else:
                failed += 1

        status = "ok" if failed == 0 else "partial"
        print(
            f"Backup Dropbox: {uploaded} archivos -> {root}"
            + (f" ({failed} fallidos)" if failed else "")
        )
        return {
            "status": status,
            "uploaded": uploaded,
            "failed": failed,
            "folder": root,
        }
    except Exception as exc:
        _warn(f"error inesperado ({exc}); el sync continúa")
        return {"status": "error", "error": str(exc)}


def list_available_backups() -> dict:
    """Lista los archivos de backup disponibles en Dropbox."""
    token = _get_access_token()
    if not token:
        return {"status": "no_credentials", "files": []}
    root = _backup_root()
    files = _list_folder_files(token, root, recursive=True)
    return {"status": "ok", "files": sorted(files), "folder": root}


def restore_backup(data_dir: Path | None = None) -> dict:
    """Download, validate, then publish the complete required dataset."""
    target_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    token = _get_access_token()
    if not token:
        raise RuntimeError("Sin credenciales Dropbox (DROPBOX_ACCESS_TOKEN o refresh trio)")

    root = _backup_root()
    file_names = _list_folder_files(token, root, recursive=True)
    if not file_names:
        raise FileNotFoundError(f"No hay archivos en {root}")

    target_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix="restore_staging_", dir=target_dir))
    try:
        staged_names = []
        failed = []
        for name in file_names:
            rel_path = _safe_relative_path(name)
            if rel_path is None:
                failed.append(name)
                continue
            data = _download_file(token, f"{root}/{rel_path}")
            if data is None:
                failed.append(name)
                continue
            staged_path = staging_dir / Path(rel_path)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(data)
            staged_names.append(rel_path)

        if failed:
            raise RuntimeError(f"Descarga incompleta desde {root}: {failed}")
        missing = sorted(set(_RESTORE_REQUIRED_CSVS) - set(staged_names))
        if missing:
            raise RuntimeError(f"Backup incompleto en {root}; faltan: {missing}")
        _validate_restore_set(staging_dir)
        # Publish every downloaded artifact after validating the required CSV set.
        backed_up = _publish_restore_set(staging_dir, target_dir, staged_names)
        return {
            "status": "ok",
            "source_folder": root,
            "restored": staged_names,
            "backed_up": backed_up,
            "backup_dir": str(target_dir / "backup" / "pre_restore") if backed_up else None,
        }
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def auto_restore_if_empty(*, data_dir: Path | None = None, enabled: bool | None = None) -> dict:
    """Restaura Dropbox si el conjunto obligatorio no es utilizable.

    Devuelve un dict de estado para que los entrypoints decidan si continúan.
    Si el restore queda parcial o falla, lanza para bloquear el sync.
    """
    target_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    auto_restore_enabled = enabled if enabled is not None else env_flag("HRV_AUTO_RESTORE_ON_EMPTY_DATA", default=False)
    rows = _core_row_count(target_dir)
    try:
        _validate_restore_set(target_dir)
        empty = False
    except RuntimeError:
        empty = True

    if not auto_restore_enabled:
        return {"status": "disabled", "data_empty": empty, "core_rows": rows}

    if not empty:
        return {"status": "skipped", "data_empty": False, "core_rows": rows}

    if rows is None:
        print(f"[INFO] Auto-restore Dropbox: CORE ilegible o ausente en {target_dir}; restaurando backup...")
    else:
        print(f"[INFO] Auto-restore Dropbox: DATA_DIR vacío en {target_dir}; restaurando backup...")
    try:
        result = restore_backup(target_dir)
    except Exception as exc:
        raise RuntimeError(f"Auto-restore falló: {exc}") from exc
    if result.get("status") != "ok":
        raise RuntimeError(f"Auto-restore incompleto desde Dropbox: {result}")

    try:
        _validate_restore_set(target_dir)
    except RuntimeError as exc:
        raise RuntimeError(f"Auto-restore no dejó el conjunto obligatorio utilizable: {exc}") from exc
    post_rows = _core_row_count(target_dir)

    restored_count = len(result.get("restored", []))
    print(
        f"[OK] Auto-restore Dropbox: restaurado desde {result.get('source_folder')} "
        f"({restored_count} archivos)"
    )
    return {
        **result,
        "status": "restored",
        "data_empty": False,
        "core_rows": post_rows,
        "auto_restored": True,
    }
