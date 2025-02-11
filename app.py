from flask import Flask, render_template
from flask_socketio import SocketIO
import psutil
import socket

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
            "network_sent": stats.bytes_sent,
            "network_recv": stats.bytes_recv,
            "network_sent_packets": stats.packets_sent,
            "network_recv_packets": stats.packets_recv,
            "network_sent_errs": stats.errin,
            "network_recv_errs": stats.errout,
            "network_dropin": stats.dropin,
            "network_dropout": stats.dropout,
        }
        
        if interface in net_addrs:
            for addr in net_addrs[interface]:
                if addr.family == socket.AF_INET:  
                    interface_info["ip_address"] = addr.address
                    interface_info["netmask"] = addr.netmask
                elif addr.family == psutil.AF_LINK:  
                    interface_info["mac_address"] = addr.address
        
        if interface in net_stats:
            stats = net_stats[interface]
            interface_info["is_up"] = stats.isup  
            interface_info["speed"] = stats.speed  # Velocidad en Mbps
        
        metrics[interface] = interface_info
    
    return metrics




def send_metrics():
    while True:
        socketio.emit("update_cpu", get_cpu_metrics())
        socketio.emit("update_memory", get_memory_metrics())
        socketio.emit("update_disk", get_disk_metrics())
        socketio.emit("update_network", get_network_metrics())
        socketio.sleep(0.1)

def send_cpu_metrics():
    while True:
        socketio.emit("update_cpu", get_cpu_metrics())
        socketio.sleep(1)

def send_memory_metrics():
    while True:
        socketio.emit("update_memory", get_memory_metrics())
        socketio.sleep(2)

def send_disk_metrics():
    while True:
        socketio.emit("update_disk", get_disk_metrics())
        socketio.sleep(5)

def send_network_metrics():
    while True:
        socketio.emit("update_network", get_network_metrics())
        socketio.sleep(3)

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    """Inicia el envío de métricas cuando un cliente se conecta"""
    # socketio.start_background_task(target=send_cpu_metrics)
    # socketio.start_background_task(target=send_memory_metrics)
    # socketio.start_background_task(target=send_disk_metrics)
    # socketio.start_background_task(target=send_network_metrics)

    socketio.start_background_task(send_metrics)

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, use_reloader=False, log_output=True)
