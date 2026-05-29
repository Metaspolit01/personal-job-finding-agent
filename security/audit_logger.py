import sqlite3
import logging
import os
from datetime import datetime
from config.settings import DB_PATH

logger = logging.getLogger(__name__)

# Ensure the logs directory exists
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_LOG_FILE = os.path.join(base_dir, "logs", "audit.log")
os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)

# Dedicated file logger for security and tool audit trails
audit_file_logger = logging.getLogger("audit_file")
audit_file_logger.setLevel(logging.INFO)

# Avoid adding duplicate handlers if the module is re-imported
if not audit_file_logger.handlers:
    fh = logging.FileHandler(AUDIT_LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    audit_file_logger.addHandler(fh)

def log_audit_action(tool: str, action: str, result: str, details: str = None):
    """
    Log an event to the unified audit trail.
    Formats and writes to logs/audit.log, then inserts into the audit_logs SQLite table.
    """
    timestamp = datetime.now().isoformat()
    details_str = details if details is not None else ""
    tool_str = tool if tool is not None else "None"
    
    # 1. Write pipe-separated entry to local text file
    log_line = f"{timestamp} | {tool_str} | {action} | {result} | {details_str}"
    audit_file_logger.info(log_line)
    
    # 2. Write to SQLite audit_logs table
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO audit_logs (tool, action, result, details)
            VALUES (?, ?, ?, ?)
        """, (tool_str, action, result, details_str))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record audit log in SQLite: {e}")
    finally:
        conn.close()
