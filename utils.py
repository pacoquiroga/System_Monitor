import json
import zlib
import base64
import time

class MetricsOptimizer:
    """
    Clase para optimizar la recopilación y envío de métricas del sistema
    """
    
    def __init__(self):
        self.last_data = {}
        self.last_sent_time = {}
        
        # Definir umbrales de cambio significativo para cada tipo de métrica
        self.change_thresholds = {
            'cpu_percent': 2.0,  # 2% de cambio en CPU
            'memory_percent': 1.0,  # 1% de cambio en RAM
            'disk_usage': 0.5,    # 0.5% de cambio en uso de disco
        }
        
        # Intervalos mínimos entre actualizaciones (en segundos)
        self.update_intervals = {
            'cpu': 1,
            'memory': 1,
            'disk': 5,
            'network': 2,
            'processes': 3,
            'battery': 10
        }
    
    def should_send_update(self, metric_type, new_data):
        """
        Determina si una actualización debe enviarse basada en:
        1. Si ha pasado suficiente tiempo desde la última actualización
        2. Si los datos han cambiado significativamente
        """
        current_time = time.time()
        
        # Verificar si es la primera vez que se envían estos datos
        if metric_type not in self.last_sent_time:
            self.last_sent_time[metric_type] = current_time
            self.last_data[metric_type] = new_data
            return True
            
        # Verificar si ha pasado suficiente tiempo
        time_elapsed = current_time - self.last_sent_time[metric_type]
        if time_elapsed < self.update_intervals.get(metric_type, 1):
            return False
            
        # Verificar si los datos han cambiado significativamente
        if metric_type in self.last_data:
            if not self._data_changed_significantly(metric_type, self.last_data[metric_type], new_data):
                return False
                
        # Actualizar datos y tiempo
        self.last_sent_time[metric_type] = current_time
        self.last_data[metric_type] = new_data
        return True
    
    def _data_changed_significantly(self, metric_type, old_data, new_data):
        """Determina si los datos han cambiado lo suficiente para justificar una nueva transmisión"""
        
        # Verificaciones específicas por tipo de métrica
        if metric_type == 'cpu':
            cpu_change = abs(new_data.get('cpu_percent', 0) - old_data.get('cpu_percent', 0))
            return cpu_change > self.change_thresholds['cpu_percent']
            
        elif metric_type == 'memory':
            memory_change = abs(new_data.get('memory_percent', 0) - old_data.get('memory_percent', 0))
            return memory_change > self.change_thresholds['memory_percent']
            
        elif metric_type == 'disk':
            disk_change = abs(new_data.get('disk_usage', 0) - old_data.get('disk_usage', 0))
            return disk_change > self.change_thresholds['disk_usage']
            
        # Para procesos, siempre enviar si ha pasado el tiempo suficiente
        elif metric_type == 'processes':
            return True
            
        # Para red y batería, enviar según el intervalo de tiempo
        return True
    
    @staticmethod
    def compress_data(data):
        """Comprime los datos para una transmisión más eficiente"""
        json_str = json.dumps(data)
        compressed = zlib.compress(json_str.encode('utf-8'))
        return base64.b64encode(compressed).decode('ascii')
    
    @staticmethod
    def decompress_data(compressed_data):
        """Descomprime los datos recibidos"""
        decoded = base64.b64decode(compressed_data)
        decompressed = zlib.decompress(decoded)
        return json.loads(decompressed.decode('utf-8'))
