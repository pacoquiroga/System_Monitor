from flask import Flask, render_template
from flask_socketio import SocketIO
import psutil
import socket
import mysql.connector
import time 
import json
import zlib
import base64
from utils import MetricsOptimizer  # Importar la clase MetricsOptimizer

# Configuración de la conexión a MySQL
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "system_monitor"
}

last_alert_times = {
    "CPU": 0,
    "Memoria": 0,
    "Disco": 0
}

# Umbrales críticos
CRITICAL_CPU = 90  # 90% de uso de SCPU
CRITICAL_MEMORY = 90  # 90% de uso de memoria
CRITICAL_DISK = 90  # 90% de uso de disco
COOLDOWN_TIME = 10

def check_cpu_usage(cpu_percent):
    if cpu_percent > CRITICAL_CPU:
        message = f"Uso de CPU crítico: {cpu_percent}%"
        save_alert("CPU", cpu_percent, message)
        socketio.emit("alert", {"type": "CPU", "message": message})

def check_memory_usage(memory_percent):
    if memory_percent > CRITICAL_MEMORY:
        message = f"Uso de memoria crítico: {memory_percent}%"
        save_alert("Memoria", memory_percent, message)
        socketio.emit("alert", {"type": "Memoria", "message": message})

def check_disk_usage(disk_percent):
    if disk_percent > CRITICAL_DISK:
        message = f"Uso de disco crítico: {disk_percent}%"
        save_alert("Disco", disk_percent, message)
        socketio.emit("alert", {"type": "Disco", "message": message})

# Función para conectar a MySQL
def connect_to_mysql():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error al conectar a MySQL: {err}")
        return None
    

def save_alert(resource_type, resource_value, message):
    global last_alert_times

    # Obtener el tiempo actual
    current_time = time.time()

    # Verificar si ha pasado el tiempo de cooldown desde la última alerta
    if current_time - last_alert_times[resource_type] >= COOLDOWN_TIME:
        conn = connect_to_mysql()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                INSERT INTO alerts (resource_type, resource_value, message)
                VALUES (%s, %s, %s)
                ''', (resource_type, resource_value, message))
                conn.commit()
                print("Alerta guardada en la base de datos.")

                # Actualizar el timestamp de la última alerta
                last_alert_times[resource_type] = current_time
            except mysql.connector.Error as err:
                print(f"Error al guardar la alerta: {err}")
            finally:
                cursor.close()
                conn.close()
    else:
        print(f"Cooldown activo para {resource_type}. No se guardará la alerta.")


app = Flask(__name__)
socketio = SocketIO(app, 
    cors_allowed_origins="*",
    async_mode='threading',  # Cambia el modo async
    ping_timeout=5,         # Reduce el timeout
    ping_interval=25000     # Ajusta el intervalo de ping
)

def get_cpu_metrics():
    cpu_times = psutil.cpu_times()
    cpu_freq = psutil.cpu_freq(percpu=False)
    temps = "N/A"
    if hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_battery()

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),  # Reducido a 0.1 segundos para mediciones más rápidas
        "cpu_count": psutil.cpu_count(logical=False),	
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_freq_min": cpu_freq.min if cpu_freq.min else "N/A",
        "cpu_freq_max": cpu_freq.max if cpu_freq.max else "N/A",
        "cpu_freq_current": cpu_freq.current if cpu_freq.current else "N/A",
        "cpu_user": cpu_times.user,
        "cpu_system": cpu_times.system,
        "cpu_idle": cpu_times.idle,
        "cpu_irq": getattr(cpu_times, "irq", None),
        "cpu_softirq": getattr(cpu_times, "softirq", None),
        "cpu_temp" : temps,
        "timestamp": time.time()  # Agregar timestamp para seguimiento
    }


def get_memory_metrics():
    memory = psutil.virtual_memory()

    return {
        "memory_percent": memory.percent,
        "memory_total": memory.total,
        "memory_available": memory.available,
        "memory_used": memory.used,
        "memory_buffers": memory.buffers if hasattr(memory, "buffers") else "N/A",
        "memory_cached": memory.cached if hasattr(memory, "cached") else "N/A",
        "memory_shared": memory.shared if hasattr(memory, "shared") else "N/A",
    }


def get_disk_metrics():
    disk = psutil.disk_usage('/')
    disk_io = psutil.disk_io_counters()
    return {
        "disk_usage": disk.percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "disk_read": disk_io.read_bytes,
        "disk_write": disk_io.write_bytes,
        "disk_read_count": disk_io.read_count,
        "disk_write_count": disk_io.write_count,
        "disk_read_time": disk_io.read_time,
        "disk_write_time": disk_io.write_time,
    }



def get_network_metrics():
    net_io = psutil.net_io_counters(pernic=True)
    net_addrs = psutil.net_if_addrs()
    net_stats = psutil.net_if_stats()
    
    metrics = {}
    for interface, stats in net_io.items():
        interface_info = {
            "is_up": net_stats[interface].isup if interface in net_stats else False,
            "ip_address": "N/A",
            "mac_address": "N/A",
            "speed": net_stats[interface].speed if interface in net_stats else "N/A",
            "network_sent": stats.bytes_sent,
            "network_recv": stats.bytes_recv,
            "network_sent_packets": stats.packets_sent,
            "network_recv_packets": stats.packets_recv,
            "network_sent_errs": stats.errout,
            "network_recv_errs": stats.errin,
            "network_dropin": stats.dropin,
            "network_dropout": stats.dropout,
        }
        
        if interface in net_addrs:
            for addr in net_addrs[interface]:
                if addr.family == socket.AF_INET:  # IPv4
                    interface_info["ip_address"] = addr.address
                elif addr.family == psutil.AF_LINK:  # MAC address
                    interface_info["mac_address"] = addr.address
        
        metrics[interface] = interface_info
    
    return metrics


def get_process_metrics():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_info', 'create_time']):
        try:
            process_info = proc.info
            processes.append({
                "pid": process_info['pid'],
                "name": process_info['name'],
                "status": process_info['status'],
                "cpu_percent": process_info['cpu_percent'],
                "memory_rss": process_info['memory_info'].rss,  # Memoria RSS (Resident Set Size)
                "memory_vms": process_info['memory_info'].vms,  # Memoria VMS (Virtual Memory Size)
                "create_time": process_info['create_time'],      # Tiempo de creación del proceso
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue  # Ignorar procesos que ya no existen o no se pueden acceder

    # Filtrar procesos principales (los que consumen más CPU o memoria)
    processes.sort(key=lambda p: p['cpu_percent'], reverse=True)  # Ordenar por uso de CPU
    top_processes = processes[:50]  # Seleccionar los 10 procesos más relevantes

    # Clasificar procesos en primer plano y segundo plano
    foreground_processes = [p for p in top_processes if p['status'] in ['running', 'sleeping']]
    background_processes = [p for p in top_processes if p['status'] not in ['running', 'sleeping']]

    return {
        "foreground": foreground_processes,
        "background": background_processes
    }


def get_battery_metrics():
    battery = psutil.sensors_battery()
    if battery is None:
        return {
            "battery_percent": "N/A",
            "battery_plugged": "N/A",
            "battery_secsleft": "N/A"
        }
    return {
        "battery_percent": battery.percent,
        "battery_plugged": "Conectado" if battery.power_plugged else "Desconectado",
        "battery_secsleft": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "N/A"
    }


# Función para comprimir datos (reduce la cantidad de datos transferidos)
def compress_data(data):
    json_data = json.dumps(data)
    compressed = zlib.compress(json_data.encode('utf-8'))
    return base64.b64encode(compressed).decode('ascii')

# Variables para almacenar datos anteriores y controlar la frecuencia
last_sent_data = {}
last_sent_time = {}
MIN_UPDATE_INTERVAL = {
    'cpu': 0.5,       # Actualización cada 0.5 segundos (antes 1)
    'memory': 0.5,    # Actualización cada 0.5 segundos (antes 1)
    'disk': 2,        # Actualización cada 2 segundos (antes 5)
    'network': 1,     # Actualización cada 1 segundo (antes 2)
    'processes': 1.5, # Actualización cada 1.5 segundos (antes 3)
    'battery': 5      # Actualización cada 5 segundos (antes 10)
}

# Esta función determina si debemos enviar una actualización basada en el tiempo transcurrido
def should_update(metric_type, current_time):
    if metric_type not in last_sent_time:
        last_sent_time[metric_type] = 0
        return True
    
    return current_time - last_sent_time[metric_type] >= MIN_UPDATE_INTERVAL[metric_type]

# Esta función determina si los datos han cambiado lo suficiente para enviarlos
def data_changed_significantly(old_data, new_data, metric_type):
    if metric_type not in last_sent_data:
        return True
        
    # Forzar actualización cada cierto tiempo incluso si no hay cambios significativos
    force_update_interval = MIN_UPDATE_INTERVAL[metric_type] * 4
    if new_data.get('timestamp', time.time()) - old_data.get('timestamp', 0) > force_update_interval:
        return True
        
    if metric_type == 'cpu':
        # Para CPU, enviar si el porcentaje cambió en más de 1% (antes 2%)
        return abs(new_data.get('cpu_percent', 0) - old_data.get('cpu_percent', 0)) > 1
    
    elif metric_type == 'memory':
        # Para memoria, enviar si el porcentaje cambió en más de 0.5% (antes 1%)
        return abs(new_data.get('memory_percent', 0) - old_data.get('memory_percent', 0)) > 0.5
    
    # Para otros tipos de datos, siempre enviar cuando toca según el intervalo
    return True

def send_metrics():
    metrics_optimizer = MetricsOptimizer()  # Crear una instancia del optimizador
    last_metrics_bundle_time = time.time()  # Para controlar actualizaciones consolidadas
    
    while True:
        # Verificar si hay clientes conectados
        if len(socketio.server.eio.sockets) == 0:
            socketio.sleep(0.5)  # Si no hay clientes, esperar menos tiempo
            continue
            
        current_time = time.time()
        
        # Recopilar métricas en paralelo utilizando background tasks
        cpu_data = None
        memory_data = None
        disk_data = None
        network_data = None
        process_data = None
        battery_data = None
        
        # CPU - Prioridad alta, siempre obtener datos recientes
        if should_update('cpu', current_time):
            cpu_data = get_cpu_metrics()
            if data_changed_significantly(last_sent_data.get('cpu', {}), cpu_data, 'cpu'):
                # Emitir inmediatamente los datos críticos para mayor fluidez
                socketio.emit("update_cpu", cpu_data)
                last_sent_data['cpu'] = cpu_data
                last_sent_time['cpu'] = current_time
                
                # Verificar umbrales críticos
                check_cpu_usage(cpu_data['cpu_percent'])
        
        # Memoria - También prioridad alta
        if should_update('memory', current_time):
            memory_data = get_memory_metrics()
            if data_changed_significantly(last_sent_data.get('memory', {}), memory_data, 'memory'):
                # Emitir inmediatamente los datos críticos para mayor fluidez
                socketio.emit("update_memory", memory_data)
                last_sent_data['memory'] = memory_data
                last_sent_time['memory'] = current_time
                
                # Verificar umbrales críticos
                check_memory_usage(memory_data['memory_percent'])
        
        # Recopilar otras métricas solo cuando sea necesario
        metrics_bundle = {}
        
        # Disco - Menor prioridad
        if should_update('disk', current_time):
            disk_data = get_disk_metrics()
            metrics_bundle['disk'] = disk_data
            last_sent_data['disk'] = disk_data
            last_sent_time['disk'] = current_time
            
            # Verificar umbrales críticos
            check_disk_usage(disk_data['disk_usage'])
        
        # Red
        if should_update('network', current_time):
            network_data = get_network_metrics()
            metrics_bundle['network'] = network_data
            last_sent_data['network'] = network_data
            last_sent_time['network'] = current_time
        
        # Procesos
        if should_update('processes', current_time):
            process_data = get_process_metrics()
            metrics_bundle['processes'] = process_data
            last_sent_data['processes'] = process_data
            last_sent_time['processes'] = current_time
        
        # Batería
        if should_update('battery', current_time):
            battery_data = get_battery_metrics()
            metrics_bundle['battery'] = battery_data
            last_sent_data['battery'] = battery_data
            last_sent_time['battery'] = current_time
        
        # Enviar métricas menos prioritarias en lote
        if metrics_bundle and (current_time - last_metrics_bundle_time) >= 0.5:
            if 'disk' in metrics_bundle:
                socketio.emit("update_disk", metrics_bundle['disk'])
            if 'network' in metrics_bundle:
                socketio.emit("update_network", metrics_bundle['network'])
            if 'processes' in metrics_bundle:
                socketio.emit("update_processes", metrics_bundle['processes'])
            if 'battery' in metrics_bundle:
                socketio.emit("update_battery", metrics_bundle['battery'])
            
            last_metrics_bundle_time = current_time
        
        # Utilizar un intervalo de espera dinámico basado en la carga
        if cpu_data and cpu_data.get('cpu_percent', 0) > 70:
            # Si la CPU está bajo carga alta, reducir la frecuencia de muestreo
            sleep_time = 0.3
        else:
            # En condiciones normales, muestreo rápido
            sleep_time = 0.1
            
        socketio.sleep(sleep_time)

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    """Inicia el envío de métricas cuando un cliente se conecta"""
    print("Cliente conectado")
    if not hasattr(app, 'metrics_task_started') or not app.metrics_task_started:
        socketio.start_background_task(send_metrics)
        app.metrics_task_started = True
        
    # Enviar datos iniciales inmediatamente al conectar
    initial_data = {
        'cpu': get_cpu_metrics(),
        'memory': get_memory_metrics(),
        'disk': get_disk_metrics()
    }
    socketio.emit("initial_data", initial_data)

@socketio.on("disconnect")
def handle_disconnect():
    print("Cliente desconectado")

if __name__ == "__main__":
    app.metrics_task_started = False
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, use_reloader=False, log_output=True)
