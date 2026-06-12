# -*- coding: utf-8 -*-
"""Backup opcional de los artefactos canónicos a Dropbox tras un sync exitoso.

El histórico del atleta vive en un único volumen (Railway); el sueño y el
wellness subjetivo no son regenerables desde las APIs si ese volumen se pierde.
Este módulo sube los `ENDURANCE_HRV_*.csv` / `*.json` de `DATA_DIR` a una
carpeta fechada de Dropbox y rota las copias antiguas.

Contrato operativo:
- Opt-in vía `HRV_BACKUP_DROPBOX_ENABLED` (default off).
- Reutiliza las credenciales Dropbox ya configuradas para la ingesta RR
  (`DROPBOX_ACCESS_TOKEN` o `DROPBOX_REFRESH_TOKEN` + `DROPBOX_APP_KEY` +
  `DROPBOX_APP_SECRET`).
- NUNCA lanza: cualquier fallo se reporta como warning y el sync continúa.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import requests

from .config import DATA_DIR
from .polar_utils import env_flag

_UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
_DELETE_URL = "https://api.dropboxapi.com/2/files/delete_v2"
_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

_DATE_FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMEOUT_SEC = 60


def _warn(message: str) -> None:
    print(f"⚠️  Backup Dropbox: {message}", file=sys.stderr)


def backup_enabled() -> bool:
    return env_flag("HRV_BACKUP_DROPBOX_ENABLED", default=False)


def _backup_root() -> str:
    raw = (os.environ.get("HRV_BACKUP_DROPBOX_PATH") or "/hrv_backups").strip() or "/hrv_backups"
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/")


def _backup_keep(default: int = 14) -> int:
    raw = (os.environ.get("HRV_BACKUP_KEEP") or "").strip()
    try:
        value = int(raw)
        return value if value >= 1 else default
    except ValueError:
        return default


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
    return [p for p in files if p.is_file()]


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


def _list_backup_date_folders(token: str, root: str) -> list[str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(_LIST_FOLDER_URL, headers=headers, json={"path": root}, timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        # 409 típico cuando la carpeta aún no existe: no hay nada que rotar.
        return []
    entries = resp.json().get("entries", [])
    return sorted(
        e.get("name", "")
        for e in entries
        if e.get(".tag") == "folder" and _DATE_FOLDER_RE.match(e.get("name", ""))
    )


_DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"


def _list_folder_files(token: str, folder: str) -> list[str]:
    """Lista los archivos (no carpetas) dentro de una carpeta de Dropbox."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(_LIST_FOLDER_URL, headers=headers, json={"path": folder}, timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        return []
    entries = resp.json().get("entries", [])
    return [e["name"] for e in entries if e.get(".tag") == "file"]


def _download_file(token: str, dropbox_path: str) -> bytes | None:
    api_arg = json.dumps({"path": dropbox_path}, ensure_ascii=True)
    headers = {"Authorization": f"Bearer {token}", "Dropbox-API-Arg": api_arg}
    resp = requests.post(_DOWNLOAD_URL, headers=headers, timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        _warn(f"descarga de {dropbox_path} falló ({resp.status_code})")
        return None
    return resp.content


def _delete_path(token: str, path: str) -> bool:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(_DELETE_URL, headers=headers, json={"path": path}, timeout=_TIMEOUT_SEC)
    if resp.status_code != 200:
        _warn(f"no se pudo borrar copia antigua {path} ({resp.status_code})")
        return False
    return True


def run_backup() -> dict:
    """Sube los artefactos canónicos a Dropbox. Nunca lanza."""
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
        day_folder = f"{root}/{date.today().isoformat()}"
        uploaded = 0
        failed = 0
        for path in files:
            if _upload_file(token, path, f"{day_folder}/{path.name}"):
                uploaded += 1
            else:
                failed += 1

        deleted = 0
        keep = _backup_keep()
        folders = _list_backup_date_folders(token, root)
        for name in folders[:-keep] if len(folders) > keep else []:
            if _delete_path(token, f"{root}/{name}"):
                deleted += 1

        status = "ok" if failed == 0 else "partial"
        print(
            f"💾 Backup Dropbox: {uploaded} archivos → {day_folder}"
            + (f" ({failed} fallidos)" if failed else "")
            + (f"; {deleted} copias antiguas rotadas" if deleted else "")
        )
        return {
            "status": status,
            "uploaded": uploaded,
            "failed": failed,
            "deleted_old": deleted,
            "folder": day_folder,
        }
    except Exception as exc:
        _warn(f"error inesperado ({exc}); el sync continúa")
        return {"status": "error", "error": str(exc)}


def list_available_backups() -> dict:
    """Lista las carpetas de backup disponibles en Dropbox (más reciente primero)."""
    token = _get_access_token()
    if not token:
        return {"status": "no_credentials", "folders": []}
    root = _backup_root()
    folders = _list_backup_date_folders(token, root)
    return {"status": "ok", "folders": list(reversed(folders))}


def restore_backup(date_folder: str | None = None) -> dict:
    """Descarga la copia de backup de Dropbox a DATA_DIR. Lanza en caso de error."""
    from .io_utils import _replace_atomic

    token = _get_access_token()
    if not token:
        raise RuntimeError("Sin credenciales Dropbox (DROPBOX_ACCESS_TOKEN o refresh trio)")

    root = _backup_root()
    if not date_folder:
        folders = _list_backup_date_folders(token, root)
        if not folders:
            raise FileNotFoundError(f"No hay backups en {root}")
        date_folder = folders[-1]

    if not _DATE_FOLDER_RE.match(date_folder):
        raise ValueError(f"Nombre de carpeta inválido: {date_folder}")

    folder_path = f"{root}/{date_folder}"
    file_names = _list_folder_files(token, folder_path)
    if not file_names:
        raise FileNotFoundError(f"No hay archivos en {folder_path}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = DATA_DIR / "backup" / f"pre_restore_{date_folder}"

    restored = []
    failed = []
    backed_up = []
    for name in file_names:
        data = _download_file(token, f"{folder_path}/{name}")
        if data is None:
            failed.append(name)
            continue

        dest = DATA_DIR / name
        if dest.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup_dir / name)
            backed_up.append(name)

        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f"{name}.", suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp)
        try:
            tmp_path.write_bytes(data)
            _replace_atomic(tmp_path, dest)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        restored.append(name)

    if not restored:
        raise RuntimeError(f"No se pudo descargar ningún archivo de {folder_path}")

    return {
        "status": "ok" if not failed else "partial",
        "source_folder": folder_path,
        "restored": restored,
        "failed": failed,
        "backed_up": backed_up,
        "backup_dir": str(backup_dir) if backed_up else None,
    }
