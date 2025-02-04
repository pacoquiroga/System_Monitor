import psutil
print(psutil.cpu_percent(interval=1))
print(psutil.virtual_memory().percent)
print(psutil.disk_usage('/').percent)
print(psutil.net_io_counters().bytes_sent)
