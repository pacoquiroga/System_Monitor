from flask import Flask, render_template
from flask_socketio import SocketIO
import psutil
import socket
import mysql.connector
import time 

# Configuración de la conexión a MySQL
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "12345",
    "database": "system_monitor"
}

last_alert_times = {
    "CPU": 0,
    "Memoria": 0,
    "Disco": 0
}

# Umbrales críticos
CRITICAL_CPU = 90  # 90% de uso de CPU
CRITICAL_MEMORY = 90  # 90% de uso de memoria
CRITICAL_DISK = 90  # 90% de uso de disco
COOLDOWN_TIME = 300

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
socketio = SocketIO(app, cors_allowed_origins="*")

def get_cpu_metrics():
    cpu_times = psutil.cpu_times()
    cpu_freq = psutil.cpu_freq(percpu=False)
    temps = "N/A"
    if hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_battery()

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5) * 10,
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
        "cpu_temp" : temps 
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



# def get_temperature_metrics():
#     temps = psutil.sensors_temperatures()
#     if not temps:
#         return {
#             "cpu_temp": "N/A",
#             "gpu_temp": "N/A"
#         }
    
#     cpu_temp = "N/A"
#     gpu_temp = "N/A"
    
#     # Obtener temperatura de la CPU
#     if 'coretemp' in temps:
#         cpu_temp = max([temp.current for temp in temps['coretemp']])
    
#     # Obtener temperatura de la GPU (si está disponible)
#     if 'amdgpu' in temps:
#         gpu_temp = max([temp.current for temp in temps['amdgpu']])
#     elif 'nvidia' in temps:
#         gpu_temp = max([temp.current for temp in temps['nvidia']])
    
#     return {
#         "cpu_temp": cpu_temp,
#         "gpu_temp": gpu_temp
#     }



def send_metrics():
    while True:
        # Obtener métricas
        cpu_data = get_cpu_metrics()
        memory_data = get_memory_metrics()
        disk_data = get_disk_metrics()

        # Verificar umbrales críticos
        check_cpu_usage(cpu_data['cpu_percent'])
        check_memory_usage(memory_data['memory_percent'])
        check_disk_usage(disk_data['disk_usage'])

        # Enviar métricas al cliente
        socketio.emit("update_cpu", cpu_data)
        socketio.emit("update_memory", memory_data)
        socketio.emit("update_disk", disk_data)

        socketio.sleep(1)  # Esperar 1 segundo antes de la siguiente actualización



@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    """Inicia el envío de métricas cuando un cliente se conecta"""

    socketio.start_background_task(send_metrics)

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, use_reloader=False, log_output=True)
