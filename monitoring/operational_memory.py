import sqlite3
import logging
from datetime import datetime
from config.settings import DB_PATH

logger = logging.getLogger(__name__)

def log_operational_incident(category: str, description: str, status: str = 'open') -> int:
    """Log an operational incident to SQLite and return the row ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    incident_id = -1
    try:
        cursor.execute("""
            INSERT INTO operational_incidents (category, description, status)
            VALUES (?, ?, ?)
        """, (category, description, status))
        incident_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log operational incident: {e}")
    finally:
        conn.close()
    return incident_id

def resolve_operational_incident(incident_id: int):
    """Resolve an open operational incident."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE operational_incidents
            SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (incident_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to resolve operational incident {incident_id}: {e}")
    finally:
        conn.close()

def log_recovery_action(incident_id: int, action_name: str, status: str, logs: str = None):
    """Log a recovery execution to recovery_history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO recovery_history (incident_id, action_name, status, logs)
            VALUES (?, ?, ?, ?)
        """, (incident_id if incident_id > 0 else None, action_name, status, logs))
        
        # Also log to self_healing_actions for quick metrics
        if incident_id > 0:
            cursor.execute("""
                INSERT INTO self_healing_actions (incident_id, action_type, result, details)
                VALUES (?, ?, ?, ?)
            """, (incident_id, action_name, status, logs))
            
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log recovery action: {e}")
    finally:
        conn.close()

def get_successful_recovery_strategy(incident_pattern: str) -> str:
    """Retrieve successful recovery action from operational memory if exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    action = None
    try:
        cursor.execute("""
            SELECT successful_recovery_action FROM operational_memory
            WHERE incident_pattern = ?
        """, (incident_pattern,))
        row = cursor.fetchone()
        if row:
            action = row[0]
    except Exception as e:
        logger.error(f"Failed to retrieve operational memory: {e}")
    finally:
        conn.close()
    return action

def log_successful_recovery_strategy(incident_pattern: str, action_name: str):
    """Upsert successful recovery strategy count into operational memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO operational_memory (incident_pattern, successful_recovery_action, success_count)
            VALUES (?, ?, 1)
            ON CONFLICT(incident_pattern) DO UPDATE SET
                successful_recovery_action = excluded.successful_recovery_action,
                success_count = success_count + 1,
                updated_at = CURRENT_TIMESTAMP
        """, (incident_pattern, action_name))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save operational memory: {e}")
    finally:
        conn.close()

def log_infrastructure_state(cpu_util: float, ram_util: float, disk_util: float):
    """Log periodic infrastructure state snapshots."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO infrastructure_state_history (cpu_util, ram_util, disk_util)
            VALUES (?, ?, ?)
        """, (cpu_util, ram_util, disk_util))
        
        # Clean up history older than 7 days to avoid database bloat
        cursor.execute("""
            DELETE FROM infrastructure_state_history
            WHERE checked_at < datetime('now', '-7 days')
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log infrastructure state: {e}")
    finally:
        conn.close()

def log_alert(alert_name: str, message: str, sent_to_telegram: bool = False):
    """Log generated alerts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO operational_alerts (alert_name, message, sent_to_telegram)
            VALUES (?, ?, ?)
        """, (alert_name, message, 1 if sent_to_telegram else 0))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log alert: {e}")
    finally:
        conn.close()

def log_monitoring_event(event_type: str, severity: str, message: str):
    """Log generic monitoring event."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO monitoring_events (event_type, severity, message)
            VALUES (?, ?, ?)
        """, (event_type, severity, message))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log monitoring event: {e}")
    finally:
        conn.close()

def log_anomaly(metric_name: str, threshold: float, observed: float):
    """Log anomaly events."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO anomaly_events (metric_name, threshold_value, observed_value)
            VALUES (?, ?, ?)
        """, (metric_name, threshold, observed))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log anomaly event: {e}")
    finally:
        conn.close()
