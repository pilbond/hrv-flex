"""HG-04: precision temporal de la deteccion de picos R sobre el ECG del H10 a 130 Hz (2026-10-25).

Exploratorio. No modifica CORE/FINAL ni contrato; no escribe nada.
Compara, sobre las mismas grabaciones ECG.jsonl de data/rr_downloads, el RR producido por
egc_to_rr.py (previamente convertido en $HOME/hg04_resp_work/<grabacion>/) con una deteccion
independiente escrita aqui (paso banda 5-20 Hz, energia, refinamiento parabolico). Las dos series
de instantes se alinean buscando el desplazamiento global que minimiza el residuo mediano, y se
empareja cada latido con el mas cercano (<60 ms). Mide cuanto difieren los dos algoritmos, no la
exactitud absoluta: ambos leen las mismas muestras a 130 Hz.
Se excluyen grabaciones con mas del 10% de latidos marcados offline.
"""
import json, glob, re, math, csv, os
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks
def load_ecg(p):
    ts=[];v=[]
    for line in open(p):
        line=line.strip()
        if not line: continue
        o=json.loads(line)
        for s in o.get('data',[]): ts.append(s['timeStamp']); v.append(s['voltage'])
    ts=np.array(ts,dtype=np.float64); v=np.array(v,float); o=np.argsort(ts)
    return (ts[o]-ts[o][0])/1e9, v[o]
def detect(t,v):
    fs=1/np.median(np.diff(t))
    b,a=butter(2,[5/(fs/2),min(20/(fs/2),0.99)],btype='band'); f=filtfilt(b,a,v); e=f**2
    pk,_=find_peaks(e, distance=int(0.33*fs), height=np.percentile(e,97)*0.25)
    out=[]
    for i in pk:
        if i<1 or i>=len(e)-1: out.append(t[i]); continue
        y0,y1,y2=e[i-1],e[i],e[i+1]; d=(y0-2*y1+y2)
        dl=0.5*(y0-y2)/d if d!=0 else 0.0
        out.append(t[i]+max(min(dl,0.5),-0.5)/fs)
    return np.array(out), fs
print(f"{'grabacion':30s} {'emparejados':>11s} {'sin pareja':>10s} {'|resid| mediana':>15s} {'resid p95':>9s} {'SD resid':>8s}")
allr=[]
for p in sorted(set(glob.glob('data/rr_downloads/_source_jsonl_recovered/_unzipped/**/ECG.jsonl',recursive=True))):
    rec=re.search(r'PolarRecording_(\d{8})_(\d{6})',p).group(0)
    g=glob.glob(f"{os.path.expanduser('~')}/hg04_resp_work/{rec}/ENDURANCE_*_RR.CSV")
    if not g: continue
    rr=[];off=[]
    for x in csv.DictReader(open(g[0],newline='')):
        try: w=float(x['duration'])
        except: continue
        if math.isnan(w): continue
        rr.append(w); off.append(str(x['offline']).strip().lower() in ('1','true'))
    if 100*np.mean(off)>10: continue
    conv_rel=np.cumsum(np.array(rr))/1000.0
    t,v=load_ecg(p); mine,fs=detect(t,v)
    # buscar el desplazamiento global que mejor alinea las dos series de instantes
    best=None
    for off0 in np.arange(mine[0]-2.0, mine[0]+2.0, 0.002):
        ct=conv_rel+off0
        j=np.searchsorted(mine,ct); j=np.clip(j,1,mine.size-1)
        r=np.minimum(np.abs(mine[j]-ct),np.abs(mine[j-1]-ct))
        s=np.median(r)
        if best is None or s<best[0]: best=(s,off0)
    off0=best[1]; ct=conv_rel+off0
    j=np.searchsorted(mine,ct); j=np.clip(j,1,mine.size-1)
    cand=np.where(np.abs(mine[j]-ct)<np.abs(mine[j-1]-ct), mine[j], mine[j-1])
    resid=(cand-ct)*1000.0
    pair=np.abs(resid)<60.0
    r=resid[pair]
    print(f"{rec:30s} {int(pair.sum()):11d} {int((~pair).sum()):10d} {np.median(np.abs(r)):15.2f} {np.percentile(np.abs(r),95):9.2f} {r.std(ddof=1):8.2f}")
    allr.append((np.median(np.abs(r)), r.std(ddof=1), int((~pair).sum())))
m=np.array([a[0] for a in allr]); s=np.array([a[1] for a in allr]); u=np.array([a[2] for a in allr])
print(f"\nn={len(allr)} grabaciones | |residuo| mediana global {np.median(m):.2f} ms | SD mediana {np.median(s):.2f} ms | latidos sin pareja: {u.tolist()}")
print(f"umbral de la literatura para sesgar el RMSSD mas del 5%: ~16 ms de desplazamiento del pico")
print(f"inflacion del RMSSD si el ruido de deteccion fuese {np.median(s):.1f} ms, sobre 45 ms reales: +{100*(math.sqrt(45**2+2*np.median(s)**2)/45-1):.1f}%")
