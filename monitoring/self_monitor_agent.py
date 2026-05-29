import time
import threading
import logging
from prometheus_client import start_http_server
from monitoring.metrics_collector import collect_all_metrics
from monitoring.operational_memory import (
    log_infrastructure_state,
    log_anomaly,
    log_monitoring_event
)
from monitoring.decision_engine import analyze_and_heal

logger = logging.getLogger(__name__)

# State cache to detect counter increments
_previous_counters = {
    "scraper_failures": 0.0,
    "workflow_failures": 0.0
}

_monitoring_running = False

def detect_anomalies(metrics: dict) -> list:
    """Analyze current metrics and extract list of threshold violations."""
    global _previous_counters
    anomalies = []
    
    # 1. System resource thresholds from environment
    import os
    THRESHOLD_CPU = float(os.getenv("MONITORING_THRESHOLD_CPU", "90.0"))
    THRESHOLD_RAM = float(os.getenv("MONITORING_THRESHOLD_RAM", "90.0"))
    THRESHOLD_DISK = float(os.getenv("MONITORING_THRESHOLD_DISK", "95.0"))
    
    cpu = metrics["system"]["cpu_usage"]
    ram = metrics["system"]["ram_usage"]
    disk = metrics["system"]["disk_usage"]
    
    if cpu > THRESHOLD_CPU:
        anomalies.append(f"CPU usage is critical: {cpu}% (Threshold: {THRESHOLD_CPU}%)")
        log_anomaly("cpu_usage", THRESHOLD_CPU, cpu)
    if ram > THRESHOLD_RAM:
        anomalies.append(f"Memory (RAM) usage is critical: {ram}% (Threshold: {THRESHOLD_RAM}%)")
        log_anomaly("ram_usage", THRESHOLD_RAM, ram)
    if disk > THRESHOLD_DISK:
        anomalies.append(f"Disk space is critical: {disk}% (Threshold: {THRESHOLD_DISK}%)")
        log_anomaly("disk_usage", THRESHOLD_DISK, disk)
        
    # 2. Check for application failures incrementing
    scraper_fails = metrics["app"]["scraper_failures"]
    workflow_fails = metrics["app"]["workflow_failures"]
    
    if scraper_fails > _previous_counters["scraper_failures"]:
        diff = scraper_fails - _previous_counters["scraper_failures"]
        anomalies.append(f"New job scraper failures detected: +{diff} (Total: {scraper_fails})")
        log_anomaly("scraper_failures_increment", 0.0, diff)
        
    if workflow_fails > _previous_counters["workflow_failures"]:
        diff = workflow_fails - _previous_counters["workflow_failures"]
        anomalies.append(f"New workflow executions failed: +{diff} (Total: {workflow_fails})")
        log_anomaly("workflow_failures_increment", 0.0, diff)

    # Update previous state cache
    _previous_counters["scraper_failures"] = scraper_fails
    _previous_counters["workflow_failures"] = workflow_fails

    return anomalies

def monitoring_loop():
    """Periodic daemon loop to poll health indicators, record metrics, and trigger decisions."""
    logger.info("AIOps self-monitoring loop started.")
    global _previous_counters
    
    # Initialize cache on startup so we don't trigger alerts for historical count increments
    try:
        init_metrics = collect_all_metrics()
        _previous_counters["scraper_failures"] = init_metrics["app"]["scraper_failures"]
        _previous_counters["workflow_failures"] = init_metrics["app"]["workflow_failures"]
    except Exception as e:
        logger.error(f"Failed to perform initial metrics collection: {e}")

    while True:
        try:
            # 1. Collect health report
            metrics = collect_all_metrics()
            
            # 2. Record infrastructure state in history
            log_infrastructure_state(
                cpu_util=metrics["system"]["cpu_usage"],
                ram_util=metrics["system"]["ram_usage"],
                disk_util=metrics["system"]["disk_usage"]
            )
            
            # 3. Assess anomalies
            anomalies = detect_anomalies(metrics)
            if anomalies:
                log_monitoring_event(
                    event_type="ANOMALY_TRIGGERED",
                    severity="WARNING",
                    message=f"Anomalies detected: {', '.join(anomalies)}"
                )
                
                # 4. Trigger decision reasoning and self-healing action execution
                analyze_and_heal(metrics, anomalies)
            else:
                logger.debug("Monitoring scan complete. All systems healthy.")
                
        except Exception as e:
            logger.error(f"Unexpected error in operational monitoring loop: {e}")
            
        # Poll health status every 60 seconds
        time.sleep(60)

def start_monitoring(metrics_port: int = 8000):
    """Start the metrics exporter and operational monitoring loop daemon thread."""
    global _monitoring_running
    if _monitoring_running:
        logger.warning("AIOps monitoring is already running.")
        return
        
    logger.info(f"Starting Prometheus metrics exporter HTTP server on port {metrics_port}...")
    try:
        start_http_server(metrics_port)
        logger.info("Prometheus metrics exporter started successfully.")
    except Exception as e:
        logger.warning(
            f"Could not start metrics exporter server on port {metrics_port}: {e}. "
            "It might already be running."
        )
        
    t = threading.Thread(target=monitoring_loop, daemon=True)
    t.start()
    _monitoring_running = True
    logger.info("Self-healing monitoring thread spawned successfully.")
