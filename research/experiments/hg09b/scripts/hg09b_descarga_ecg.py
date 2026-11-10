"""HG-09B: descarga local (solo lectura en Dropbox) de los ECG seleccionados por el protocolo.

Ejecutar en el equipo del usuario, desde la raíz del repositorio:
    python -B research/experiments/hg09b/scripts/hg09b_descarga_ecg.py

Qué hace:
  1. Lee results/hg09b_seleccion_2026-10-27.json (controles y reservas fijados antes de ver señal).
  2. Lista la carpeta Dropbox configurada (.env), de forma recursiva, solo metadatos.
  3. Descarga TODOS los ZIP PolarRecording_* de las fechas de controles y reservas, y de toda
     fecha de la era ECG con >=2 grabaciones (mañanas repetidas).
  4. Guarda los ZIP en data/rr_downloads/_source_jsonl_recovered/ y los JSONL en
     _source_jsonl_recovered/_unzipped/; escribe un manifiesto con
     nombres, tamaños y SHA-256 en results/hg09b_descarga_manifest.json.
No escribe tokens ni rutas de Dropbox. No modifica nada en Dropbox ni en los CSV canónicos.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import egc_to_rr as converter  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"
SEL = RES / "hg09b_seleccion_2026-10-27.json"
DEST = ROOT / "data" / "rr_downloads" / "_source_jsonl_recovered"
MANIFEST = RES / "hg09b_descarga_manifest.json"
ECG_START = "2026-03-06"


def load_local_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k, v)


def rec_date(name: str) -> str | None:
    m = re.search(r"PolarRecording_(\d{4})(\d{2})(\d{2})_\d{6}", name, re.IGNORECASE)
    return "-".join(m.groups()) if m else None


def main() -> None:
    load_local_env()
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    targets = set()
    for k in ("controles", "reservas"):
        for case, dates in sel[k].items():
            targets.update(dates)
    folder = converter.get_default_dropbox_folder_path()
    if not folder:
        raise SystemExit("Carpeta Dropbox no configurada en .env")
    token, _ = converter._get_dropbox_access_token()
    entries = converter.list_dropbox_input_files(token, folder, recursive=True)
    by_date = defaultdict(list)
    for e in entries:
        if not e.name.lower().endswith(".zip"):
            continue
        d = rec_date(e.name) or rec_date(e.cloud_id or "")
        if d and d >= ECG_START:
            by_date[d].append(e)
    repeated = {d for d, es in by_date.items() if len({x.name.lower() for x in es}) >= 2}
    want = sorted(targets | repeated)
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {"seleccion_sha256": hashlib.sha256(SEL.read_bytes()).hexdigest(),
                "fechas_objetivo": sorted(targets), "mananas_repetidas": sorted(repeated),
                "fechas_objetivo_sin_zip": sorted(targets - set(by_date)),
                "n_fechas_era_ECG_con_zip": len(by_date), "ficheros": []}
    seen = set()
    for d in want:
        for e in sorted(by_date.get(d, []), key=lambda x: x.name.lower()):
            key = e.name.lower()
            if key in seen:
                continue
            seen.add(key)
            out = DEST / e.name
            if not out.exists():
                r = requests.post(f"{converter.DROPBOX_CONTENT_ROOT}/files/download",
                                  headers={"Authorization": f"Bearer {token}",
                                           "Dropbox-API-Arg": json.dumps({"path": e.cloud_id})},
                                  timeout=180)
                r.raise_for_status()
                tmp = out.with_suffix(".part")
                tmp.write_bytes(r.content)
                tmp.replace(out)
            b = out.read_bytes()
            if not any((d / "ECG.jsonl").exists() for d in (DEST / "_unzipped").glob(out.stem + "_*")):
                converter.extract_zip_archives([out], DEST / "_unzipped")
            manifest["ficheros"].append({"fecha": d, "fichero": e.name, "bytes": len(b),
                                         "sha256": hashlib.sha256(b).hexdigest(),
                                         "rol": ("objetivo" if d in targets else "") + ("+repetida" if d in repeated else "")})
            print(f"{d}  {e.name}  {len(b)} bytes")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(manifest['ficheros'])} ZIP en {DEST}. Manifiesto: {MANIFEST}")
    if manifest["fechas_objetivo_sin_zip"]:
        print("Fechas objetivo sin ZIP en Dropbox:", manifest["fechas_objetivo_sin_zip"])


if __name__ == "__main__":
    main()
