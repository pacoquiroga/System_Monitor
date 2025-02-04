from flask import Flask, render_template
from flask_socketio import SocketIO
import psutil
import time
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def get_system_metrics():
    """Obtiene el estado del sistema"""
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent,
        "network": round(psutil.net_io_counters().bytes_sent / (1024 * 1024), 2)  # En MB
    }

def send_metrics():
    """Envía métricas en tiempo real cada segundo sin bloquear Flask"""
    while True:
        socketio.emit("update_metrics", get_system_metrics())
        socketio.sleep(1)  

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    """Inicia el envío de métricas cuando un cliente se conecta"""
    socketio.start_background_task(target=send_metrics)

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, use_reloader=False)
