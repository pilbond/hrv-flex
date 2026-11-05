# Core Audit Fix 05 — Runtime WSGI de producción

## Objetivo

Sustituir el servidor de desarrollo de Flask (`python web_ui.py` → `app.run()`) por `waitress` en producción. Higiene operativa de baja urgencia (cierra un hallazgo del audit 2026-07-10), no un bug funcional.

## Diagnóstico (confirmado)

Producción arranca hoy el dev server de Flask en tres sitios coherentes entre sí:
- `Procfile` → `web: python web_ui.py`
- `railway.json` → `startCommand: "python web_ui.py"`
- `Dockerfile` → `CMD ["python", "web_ui.py"]`

El objeto WSGI ya sirve: `app = Flask(__name__)` a nivel de módulo en `web_ui.py`, así que un servidor externo apunta a `web_ui:app` sin refactor.

## Decisión: `waitress`

WSGI puro-Python, multiplataforma y **mono-proceso**. Elegido sobre gunicorn porque el dev local es Windows (`scripts\run-web-ui.bat`) y gunicorn no corre en Windows; waitress da el mismo arranque en local y Railway. Sin coste económico (dependencia `pip`, mismo consumo de recursos).

> Nota: waitress es un solo proceso con pool de hilos, así que el estado en memoria de `web_ui.py` (`execution_state_lock`, `_oauth_states`) se preserva sin cambios. **No cambiar a gunicorn con `-w >1`** sin releer esto: rompería la regla de no-paralelismo y la validación OAuth.

## Implementación

1. Añadir `waitress>=3.0.0` a `requirements_web.txt`.
2. Fijar el arranque a waitress apuntando a `web_ui:app`, `0.0.0.0:$PORT` (fallback `8080`), en `Procfile`, `railway.json` y `Dockerfile`.
3. Mantener `app.run()` en `web_ui.py` solo bajo `if __name__ == '__main__'` para local.
4. Alinear docs (`AGENTS.md` / `CLAUDE.md`) si mencionan `python web_ui.py` como runtime.

## Absorción de IU-10

CAF-05 absorbe el arranque/runtime. Tras esto, IU-10 queda reducida a `.dockerignore` mínimo + coherencia documental de timeout.

## Aceptación

- Railway no arranca con el dev server de Flask.
- `/health` y `POST /api/sync` funcionan con waitress.
- `Procfile`, `railway.json`, `Dockerfile` y docs coherentes entre sí.

> Shutdown: las escrituras canónicas ya son atómicas (`hrv_app.io_utils`), que mitiga corrupción si un job está en curso en un redeploy. No requiere trabajo extra.
