#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI para Polar HRV Automation
Accesible desde cualquier dispositivo (móvil, tablet, PC)
"""

from flask import Flask, render_template_string, jsonify, request
from flask_cors import CORS
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import threading
import json

app = Flask(__name__)
CORS(app)

# Estado global de ejecución
execution_state = {
    'running': False,
    'last_run': None,
    'last_output': '',
    'last_error': '',
    'success': None
}

# HTML Template (UI móvil-first)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polar HRV Sync</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        
        .card {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        
        h1 {
            color: #667eea;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        
        .sync-button {
            width: 100%;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 15px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        .sync-button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }
        
        .sync-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .sync-button.running {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            animation: pulse 2s ease-in-out infinite;
        }
        
        .sync-button.success {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }
        
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            display: none;
        }
        
        .status.show {
            display: block;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .status.info {
            background: #e3f2fd;
            color: #1565c0;
            border-left: 4px solid #2196f3;
        }
        
        .status.success {
            background: #e8f5e9;
            color: #2e7d32;
            border-left: 4px solid #4caf50;
        }
        
        .status.error {
            background: #ffebee;
            color: #c62828;
            border-left: 4px solid #f44336;
        }
        
        .output {
            margin-top: 20px;
            padding: 15px;
            background: #f5f5f5;
            border-radius: 10px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-top: 20px;
        }
        
        .info-item {
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        
        .info-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }
        
        .info-value {
            font-size: 18px;
            font-weight: 600;
            color: #667eea;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @media (max-width: 480px) {
            .card {
                padding: 20px;
            }
            
            h1 {
                font-size: 24px;
            }
            
            .sync-button {
                padding: 16px;
                font-size: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>⚡ Polar HRV Sync</h1>
            <p class="subtitle">Sincronización automática de datos HRV</p>
            
            <button id="syncBtn" class="sync-button" onclick="syncPolar()">
                <span id="btnText">Sincronizar Ahora</span>
            </button>
            
            <div id="status" class="status"></div>
            
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Última Sync</div>
                    <div class="info-value" id="lastRun">-</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Estado</div>
                    <div class="info-value" id="statusValue">Listo</div>
                </div>
            </div>
        </div>
        
        <div id="outputCard" class="card" style="display: none;">
            <h3 style="margin-bottom: 15px; color: #667eea;">📊 Detalles</h3>
            <div id="output" class="output"></div>
        </div>
    </div>
    
    <script>
        let statusCheckInterval;
        
        async function syncPolar() {
            const btn = document.getElementById('syncBtn');
            const btnText = document.getElementById('btnText');
            const status = document.getElementById('status');
            const statusValue = document.getElementById('statusValue');
            const output = document.getElementById('output');
            const outputCard = document.getElementById('outputCard');
            
            // Deshabilitar botón
            btn.disabled = true;
            btn.classList.add('running');
            btnText.innerHTML = '<span class="spinner"></span> Sincronizando...';
            
            // Mostrar status
            status.className = 'status info show';
            status.textContent = '🔄 Conectando con Polar Flow...';
            statusValue.textContent = 'Procesando';
            
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                // Si el proceso se inició (no completó inmediatamente)
                if (data.message === 'Sincronización iniciada') {
                    // Hacer polling cada 2 segundos hasta que termine
                    await pollSyncStatus();
                } else if (data.success) {
                    // Completado inmediatamente
                    showSyncSuccess(data);
                } else {
                    // Error
                    showSyncError(data);
                }
                
            } catch (error) {
                btn.classList.remove('running');
                btnText.textContent = 'Sincronizar Ahora';
                btn.disabled = false;
                
                status.className = 'status error show';
                status.textContent = '❌ Error de conexión: ' + error.message;
                statusValue.textContent = 'Error';
            }
        }
        
        async function pollSyncStatus() {
            const btn = document.getElementById('syncBtn');
            const btnText = document.getElementById('btnText');
            const status = document.getElementById('status');
            const statusValue = document.getElementById('statusValue');
            
            let attempts = 0;
            const maxAttempts = 150; // 5 minutos (150 * 2s)
            
            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000)); // Esperar 2s
                
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();
                    
                    // Actualizar mensaje de progreso
                    status.textContent = '🔄 Procesando datos HRV... ' + Math.floor(attempts * 2 / 60) + 'm ' + (attempts * 2 % 60) + 's';
                    
                    // Si ya no está ejecutándose
                    if (!data.running) {
                        if (data.success) {
                            showSyncSuccess(data);
                        } else if (data.success === false) {
                            showSyncError(data);
                        }
                        return;
                    }
                    
                    attempts++;
                } catch (error) {
                    console.error('Error polling status:', error);
                    attempts++;
                }
            }
            
            // Timeout después de 5 minutos
            btn.classList.remove('running');
            btnText.textContent = 'Sincronizar Ahora';
            btn.disabled = false;
            
            status.className = 'status error show';
            status.textContent = '⏱️ Timeout: La sincronización tomó demasiado tiempo';
            statusValue.textContent = 'Error';
        }
        
        function showSyncSuccess(data) {
            const btn = document.getElementById('syncBtn');
            const btnText = document.getElementById('btnText');
            const status = document.getElementById('status');
            const statusValue = document.getElementById('statusValue');
            const output = document.getElementById('output');
            const outputCard = document.getElementById('outputCard');
            
            btn.classList.remove('running');
            btn.classList.add('success');
            btnText.textContent = '✅ Completado';
            
            status.className = 'status success show';
            status.textContent = data.message || '✅ Sincronización completada';
            statusValue.textContent = 'Éxito';
            
            // Mostrar output
            if (data.last_output || data.output) {
                outputCard.style.display = 'block';
                output.textContent = data.last_output || data.output;
            }
            
            // Actualizar última sync
            updateLastRun();
            
            // Reset button después de 3s
            setTimeout(() => {
                btn.classList.remove('success');
                btnText.textContent = 'Sincronizar Ahora';
                btn.disabled = false;
            }, 3000);
        }
        
        function showSyncError(data) {
            const btn = document.getElementById('syncBtn');
            const btnText = document.getElementById('btnText');
            const status = document.getElementById('status');
            const statusValue = document.getElementById('statusValue');
            const output = document.getElementById('output');
            const outputCard = document.getElementById('outputCard');
            
            btn.classList.remove('running');
            btnText.textContent = 'Sincronizar Ahora';
            btn.disabled = false;
            
            status.className = 'status error show';
            status.textContent = '❌ ' + (data.error || data.last_error || 'Error desconocido');
            statusValue.textContent = 'Error';
            
            if (data.last_output || data.output) {
                outputCard.style.display = 'block';
                output.textContent = data.last_output || data.output;
            }
        }
        
        async function updateLastRun() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                if (data.last_run) {
                    const date = new Date(data.last_run);
                    const now = new Date();
                    const diff = Math.floor((now - date) / 1000 / 60); // minutos
                    
                    let timeStr;
                    if (diff < 1) {
                        timeStr = 'Ahora';
                    } else if (diff < 60) {
                        timeStr = `${diff}m`;
                    } else if (diff < 1440) {
                        timeStr = `${Math.floor(diff/60)}h`;
                    } else {
                        timeStr = `${Math.floor(diff/1440)}d`;
                    }
                    
                    document.getElementById('lastRun').textContent = timeStr;
                }
            } catch (error) {
                console.error('Error actualizando status:', error);
            }
        }
        
        // Actualizar última sync cada 30 segundos
        setInterval(updateLastRun, 30000);
        
        // Cargar status inicial
        updateLastRun();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Interfaz web principal"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/sync', methods=['POST'])
def sync():
    """Ejecutar sincronización Polar"""
    global execution_state
    
    if execution_state['running']:
        return jsonify({
            'success': False,
            'error': 'Ya hay una sincronización en curso'
        })
    
    # Ejecutar en thread separado para no bloquear
    thread = threading.Thread(target=run_sync)
    thread.start()
    
    # Esperar un poco para capturar inicio
    thread.join(timeout=1)
    
    if execution_state['success'] is not None:
        return jsonify({
            'success': execution_state['success'],
            'message': 'Sincronización completada' if execution_state['success'] else 'Error en sincronización',
            'output': execution_state['last_output'],
            'error': execution_state['last_error']
        })
    
    return jsonify({
        'success': True,
        'message': 'Sincronización iniciada',
        'output': 'Procesando...'
    })


def run_sync():
    """Ejecutar polar_hrv_automation.py"""
    global execution_state
    
    execution_state['running'] = True
    execution_state['success'] = None
    execution_state['last_output'] = ''
    execution_state['last_error'] = ''
    
    try:
        script_path = Path('polar_hrv_automation.py')
        
        if not script_path.exists():
            raise FileNotFoundError('polar_hrv_automation.py no encontrado')
        
        # Ejecutar con --process
        result = subprocess.run(
            [sys.executable, str(script_path), '--process'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300,  # 5 minutos máximo
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        
        execution_state['last_output'] = result.stdout
        execution_state['last_error'] = result.stderr
        execution_state['success'] = (result.returncode == 0)
        execution_state['last_run'] = datetime.now().isoformat()
        
    except Exception as e:
        execution_state['last_error'] = str(e)
        execution_state['success'] = False
    
    finally:
        execution_state['running'] = False


@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtener estado actual"""
    return jsonify(execution_state)


@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    """
    Manejar callback OAuth de Polar AccessLink
    Este endpoint recibe el código de autorización después de que
    el usuario autoriza la app en Polar Flow
    """
    code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description')
    
    if error:
        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error de Autorización</title>
        </head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>❌ Error de Autorización</h1>
            <p><strong>{error}</strong></p>
            <p>{error_description or 'Error desconocido'}</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 400
    
    if not code:
        return """
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error</title>
        </head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>❌ Error</h1>
            <p>No se recibió código de autorización</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 400
    
    # Guardar código en archivo temporal
    # polar_hrv_automation.py lo leerá cuando se ejecute
    try:
        with open('.oauth_code.txt', 'w') as f:
            f.write(code)
        
        return """
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Autorización Exitosa</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                    padding: 20px;
                }
                .card {
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 400px;
                }
                h1 {
                    color: #4caf50;
                    margin-bottom: 20px;
                }
                p {
                    color: #666;
                    margin-bottom: 30px;
                }
                .btn {
                    display: inline-block;
                    padding: 12px 24px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                    transition: all 0.3s;
                }
                .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                }
                .countdown {
                    color: #999;
                    font-size: 14px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>✅ Autorización Exitosa</h1>
                <p>Polar AccessLink ha sido autorizado correctamente.</p>
                <p>Ya puedes usar la sincronización automática.</p>
                <a href="/" class="btn">Volver a la App</a>
                <p class="countdown">Esta ventana se cerrará en <span id="counter">5</span> segundos...</p>
            </div>
            <script>
                let count = 5;
                const counter = document.getElementById('counter');
                const interval = setInterval(() => {
                    count--;
                    counter.textContent = count;
                    if (count <= 0) {
                        clearInterval(interval);
                        // Intentar cerrar o redirigir
                        window.close();
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 500);
                    }
                }, 1000);
            </script>
        </body>
        </html>
        """
    
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ Error</h1>
            <p>No se pudo guardar el código de autorización: {str(e)}</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 500


@app.route('/health', methods=['GET'])
def health():
    """Health check para Railway/Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("  POLAR HRV - WEB UI")
    print("="*60)
    print(f"\n🌐 Servidor iniciado en puerto {port}")
    print(f"\n📱 Accede desde:")
    print(f"   - Local: http://localhost:{port}")
    print(f"   - Railway: https://tu-app.up.railway.app")
    print("\n💡 Abre desde cualquier dispositivo (móvil, tablet, PC)")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)