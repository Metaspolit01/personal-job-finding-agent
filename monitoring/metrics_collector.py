import os
import logging
import requests
import psutil
from prometheus_client import Counter, Histogram, Gauge, REGISTRY

logger = logging.getLogger(__name__)

# Prometheus Endpoint configuration
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

# Platform Exporter Configuration
EXPORTER_TYPE = os.getenv("EXPORTER_TYPE", "windows")
EXPORTER_HOST = os.getenv("EXPORTER_HOST", "host.docker.internal")
EXPORTER_PORT = os.getenv("EXPORTER_PORT", "9182")

# ==================================================
# APP INSTRUMENTATION METRICS DEFINITION
# ==================================================
jobs_scraped_total = Counter(
    'jobs_scraped_total', 
    'Total job cards successfully scraped'
)
scraper_failures_total = Counter(
    'scraper_failures_total', 
    'Total job scraper execution failures'
)
telegram_messages_sent_total = Counter(
    'telegram_messages_sent_total', 
    'Total Telegram recommendations sent successfully'
)
ai_response_latency = Histogram(
    'ai_response_latency', 
    'Latency of Ollama AI model queries in seconds'
)
recurring_tasks_active = Gauge(
    'recurring_tasks_active', 
    'Number of active persistent tasks configured in SQLite'
)
workflow_failures_total = Counter(
    'workflow_failures_total', 
    'Total failures executing persistent tasks or scheduler runs'
)
memory_hits_total = Counter(
    'memory_hits_total', 
    'Total queries/updates to preferences and conversation memory'
)
autonomous_recovery_actions_total = Counter(
    'autonomous_recovery_actions_total', 
    'Total autonomous self-healing recovery actions executed'
)

# ==================================================
# METRICS COLLECTION ENGINE
# ==================================================
def query_prometheus_metric(query: str, fallback_value: float = 0.0) -> float:
    """Helper to query a single value from Prometheus API."""
    try:
        url = f"{PROMETHEUS_URL.rstrip('/')}/api/v1/query"
        response = requests.get(url, params={"query": query}, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results:
                    val = results[0].get("value", [0, "0"])[1]
                    return float(val)
    except Exception as e:
        logger.debug(f"Failed to query Prometheus for '{query}': {e}")
    return fallback_value

def collect_system_metrics() -> dict:
    """
    Collect system metrics (CPU, RAM, Disk).
    Attempts Prometheus query first, falls back to local OS measurement via psutil.
    """
    metrics = {
        "cpu_usage": 0.0,
        "ram_usage": 0.0,
        "disk_usage": 0.0,
        "source": "local"
    }

    # 1. Try Prometheus queries
    cpu_query = '100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) or 100 - (avg(irate(windows_cpu_time_total{mode="idle"}[5m])) * 100)'
    ram_query = '((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100) or (100 - (windows_os_physical_memory_free_bytes / windows_os_visible_memory_bytes * 100))'
    disk_query = '((node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_free_bytes{mountpoint="/"}) / node_filesystem_size_bytes{mountpoint="/"} * 100) or (100 - (windows_logical_disk_free_bytes{volume="C:"} / windows_logical_disk_size_bytes{volume="C:"} * 100))'

    cpu_val = query_prometheus_metric(cpu_query, -1.0)
    ram_val = query_prometheus_metric(ram_query, -1.0)
    disk_val = query_prometheus_metric(disk_query, -1.0)

    if cpu_val >= 0 and ram_val >= 0 and disk_val >= 0:
        metrics["cpu_usage"] = round(cpu_val, 2)
        metrics["ram_usage"] = round(ram_val, 2)
        metrics["disk_usage"] = round(disk_val, 2)
        metrics["source"] = "prometheus"
        return metrics

    # 2. Local Fallback via psutil
    try:
        metrics["cpu_usage"] = round(psutil.cpu_percent(interval=None) or 0.0, 2)
        metrics["ram_usage"] = round(psutil.virtual_memory().percent or 0.0, 2)
        drive_path = os.path.abspath(os.sep)
        metrics["disk_usage"] = round(psutil.disk_usage(drive_path).percent or 0.0, 2)
    except Exception as e:
        logger.error(f"Error collecting local system metrics via psutil: {e}")

    return metrics

def get_app_metric_value(metric_name: str) -> float:
    """Get the current value of an app metric."""
    prom_query = f"sum(rate({metric_name}[5m])) or {metric_name}"
    val = query_prometheus_metric(prom_query, -1.0)
    if val >= 0:
        return val

    # Fallback to local in-memory registry
    try:
        sample = REGISTRY.get_sample_value(metric_name)
        if sample is not None:
            return float(sample)
        sample_total = REGISTRY.get_sample_value(f"{metric_name}_total")
        if sample_total is not None:
            return float(sample_total)
    except Exception as e:
        logger.debug(f"Failed to read local in-memory metric '{metric_name}': {e}")
        
    return 0.0

def collect_all_metrics() -> dict:
    """Consolidated state report of system and application health."""
    sys_metrics = collect_system_metrics()
    
    app_metrics = {
        "jobs_scraped": get_app_metric_value("jobs_scraped_total"),
        "scraper_failures": get_app_metric_value("scraper_failures_total"),
        "telegram_sends": get_app_metric_value("telegram_messages_sent_total"),
        "workflow_failures": get_app_metric_value("workflow_failures_total"),
        "memory_hits": get_app_metric_value("memory_hits_total"),
        "recovery_actions": get_app_metric_value("autonomous_recovery_actions_total"),
        "active_tasks": get_app_metric_value("recurring_tasks_active")
    }
    
    return {
        "system": sys_metrics,
        "app": app_metrics
    }
