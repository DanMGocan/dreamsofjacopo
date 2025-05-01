import psutil
import platform
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def get_system_stats():
    """
    Get current system statistics including CPU and memory usage.
    
    Returns:
        dict: A dictionary containing system statistics
    """
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_total_mb = memory.total / (1024 * 1024)
        memory_used_mb = memory.used / (1024 * 1024)
        memory_percent = memory.percent
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 * 1024 * 1024)
        disk_used_gb = disk.used / (1024 * 1024 * 1024)
        disk_percent = disk.percent
        
        # Get system uptime
        if platform.system() == 'Windows':
            boot_time = psutil.boot_time()
            uptime_seconds = datetime.now().timestamp() - boot_time
        else:
            uptime_seconds = psutil.boot_time()
            uptime_seconds = datetime.now().timestamp() - uptime_seconds
        
        uptime_days = int(uptime_seconds // (24 * 3600))
        uptime_hours = int((uptime_seconds % (24 * 3600)) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        
        # Get process information
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
            try:
                pinfo = proc.info
                if pinfo['cpu_percent'] > 0.5 or pinfo['memory_percent'] > 0.5:  # Only include significant processes
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'username': pinfo['username'],
                        'cpu_percent': pinfo['cpu_percent'],
                        'memory_percent': pinfo['memory_percent']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort processes by CPU usage (descending)
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        
        # Get the top 5 processes
        top_processes = processes[:5]
        
        # Check for LibreOffice processes specifically
        libreoffice_processes = [p for p in processes if 'soffice' in p['name'].lower() or 'libreoffice' in p['name'].lower()]
        
        return {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': cpu_percent
            },
            'memory': {
                'total_mb': round(memory_total_mb, 2),
                'used_mb': round(memory_used_mb, 2),
                'percent': memory_percent
            },
            'disk': {
                'total_gb': round(disk_total_gb, 2),
                'used_gb': round(disk_used_gb, 2),
                'percent': disk_percent
            },
            'uptime': {
                'days': uptime_days,
                'hours': uptime_hours,
                'minutes': uptime_minutes,
                'total_seconds': int(uptime_seconds)
            },
            'top_processes': top_processes,
            'libreoffice_processes': libreoffice_processes
        }
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
