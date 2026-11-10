"""HG-04 replay, paso 1: extraer los RR de todas las fechas de CORE a un directorio
de trabajo FUERA del repo ($HOME/hg04_replay_work/rr_src por defecto).
Elige el fichero cuyo nombre coincide con `src=` de las Notes de CORE.
Solo lectura sobre data/. No deja copias de datos personales en el repo."""
from __future__ import annotations
import hashlib, json, os, re, zipfile
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")).resolve()
OUT = WORK / "rr_src"

def write_copy(out, name, content):
    """Normalize duplicate suffix only in the replay copy; never overwrite a collision."""
    normalized = re.sub(r"_RR \(\d+\)\.CSV$", "_RR.CSV", Path(name).name, flags=re.IGNORECASE)
    target = out / normalized
    if target.exists() and target.read_bytes() != content:
        raise ValueError(f"Replay filename collision: {normalized}")
    target.write_bytes(content)
    return normalized
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    core = pd.read_csv(ROOT / "data/ENDURANCE_HRV_master_CORE.csv", usecols=["Fecha", "Notes"])
    want = {}
    for d, n in zip(core.Fecha, core.Notes.astype(str)):
        m = re.search(r"src=([^;]+)", n)
        if m: want[m.group(1).strip().lower()] = d
    index = {}
    for path in sorted((ROOT / "data/rr_downloads").iterdir()):
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as z:
                for mname in z.namelist():
                    d = want.get(Path(mname).name.lower())
                    if d and d not in index:
                        b = z.read(mname); filename = write_copy(OUT, mname, b)
                        index[d] = {"source": f"{path.name}::{mname}", "file": filename, "sha256": hashlib.sha256(b).hexdigest()}
        elif path.is_file():
            d = want.get(path.name.lower())
            if d and d not in index:
                b = path.read_bytes(); filename = write_copy(OUT, path.name, b)
                index[d] = {"source": path.name, "file": filename, "sha256": hashlib.sha256(b).hexdigest()}
    (OUT / "_index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    miss = sorted(set(core.Fecha) - set(index))
    print(f"CORE filas={len(core)} con src={len(want)} extraidos={len(index)} sin RR={miss}")
if __name__ == "__main__":
    main()
