"""
Strings centralizados del backend web (API, OAuth, consola).

Los textos de presentación (botones, banners JS) viven en templates/.
"""

API = {
    "ui_key_missing": "No autorizado: falta la clave HRV_UI_KEY (header X-HRV-KEY o ?key=).",
    "sync_missing_auth": "Falta autorización. Abre /auth para iniciar sesión en Polar y autorizar la app.",
    "sync_in_progress_prefix": "Ya hay un proceso en curso: ",
    "sync_started": "Sincronización iniciada",
    "sync_success": "Sincronización completada",
    "sync_error": "Error en sincronización",
    "sync_start_error": "Error iniciando sincronización",
    "sync_output_placeholder": "Procesando...",
    "sessions_started": "Sincronización de sesiones iniciada",
    "sessions_success": "Sincronización de sesiones completada",
    "sessions_error": "Error en sincronización de sesiones",
    "sessions_start_error": "Error iniciando sincronización de sesiones",
    "seed_import_started": "CSV seed importados",
    "seed_import_error": "Error importando CSV seed",
    "seed_import_in_progress_suffix": " Espera a que termine antes de importar.",
    "restore_started": "Backup restaurado desde Dropbox",
    "restore_error": "Error restaurando backup",
    "restore_in_progress_suffix": " Espera a que termine antes de restaurar.",
    "delete_started": "Último RR movido a backup",
    "delete_error": "Error borrando el último RR",
    "delete_in_progress_suffix": " Espera a que termine antes de borrar el último RR.",
    "auth_missing_credentials": "POLAR_CLIENT_ID o POLAR_CLIENT_SECRET no configurados",
}

OAUTH = {
    "success": {
        "title": "Autorización Exitosa",
        "pill": "OAuth completado",
        "heading": "Polar autorizado",
        "message_1": "Polar AccessLink ha sido autorizado correctamente.",
        "message_2": "Ya puedes volver a la app y lanzar la sincronización.",
        "button": "Volver a la App",
        "countdown_prefix": "Esta ventana se cerrará en ",
        "countdown_suffix": " segundos...",
    },
    "error": {
        "provider_title": "Error de Autorización",
        "provider_pill": "OAuth",
        "provider_heading": "Error de Autorización",
        "provider_detail_fallback": "Error desconocido",
        "missing_code_heading": "Error",
        "missing_code_pill": "OAuth",
        "missing_code_title": "Error",
        "missing_code_message": "No se recibió código de autorización",
        "state_title": "Estado OAuth",
        "state_pill": "Estado OAuth",
        "state_heading": "Estado OAuth inválido o caducado",
        "state_message": "Vuelve a iniciar la autorización desde /auth.",
        "state_button": "Reintentar autorización",
        "default_button": "Volver a la app",
        "persist_heading": "Error",
        "persist_message_prefix": "No se pudo guardar el código de autorización: ",
    },
}

CONSOLE = {
    "title": "POLAR HRV - WEB UI",
    "server_started": "Servidor iniciado en puerto {port}",
    "access_from": "Accede desde:",
    "local": "Local: http://localhost:{port}",
    "railway": "Railway: https://tu-app.up.railway.app",
    "tip": "Abre desde cualquier dispositivo (móvil, tablet, PC)",
}
