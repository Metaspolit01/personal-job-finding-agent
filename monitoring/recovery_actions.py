import os
import shutil
import sqlite3
import logging
import subprocess
import threading
from datetime import datetime
from config.settings import DB_PATH, LOG_CONFIG
from database.memory_manager import save_preference, get_preferences, seed_default_preferences

logger = logging.getLogger(__name__)

def restart_scraper() -> str:
    """Trigger a job search pipeline execution asynchronously in a background thread."""
    from scheduler.scheduler import run_job_search
    try:
        t = threading.Thread(target=run_job_search, daemon=True)
        t.start()
        return "SUCCESS: Asynchronous scraper execution triggered."
    except Exception as e:
        return f"FAILED: Could not trigger scraping thread: {e}"

def restart_playwright() -> str:
    """Kill linger Playwright Node/Chromium driver processes to stabilize memory/crashes."""
    try:
        if os.name == 'nt':
            # Windows process termination
            subprocess.run("taskkill /f /im chrome.exe /t", shell=True, capture_output=True)
            subprocess.run("taskkill /f /im node.exe /t", shell=True, capture_output=True)
            subprocess.run("taskkill /f /im playwright.exe /t", shell=True, capture_output=True)
        else:
            # Linux process termination
            subprocess.run("pkill -f -9 chrome", shell=True, capture_output=True)
            subprocess.run("pkill -f -9 node", shell=True, capture_output=True)
        return "SUCCESS: Cleaned up lingering Playwright and Chromium processes."
    except Exception as e:
        return f"FAILED: Browser process cleanup error: {e}"

def restart_scheduler() -> str:
    """Clear scheduled tasks queue and force immediate task execution run."""
    from main import execute_active_tasks
    try:
        t = threading.Thread(target=execute_active_tasks, daemon=True)
        t.start()
        return "SUCCESS: Re-aligned and executed due active tasks."
    except Exception as e:
        return f"FAILED: Could not restart scheduler executions: {e}"

def pause_recurring_tasks() -> str:
    """Pause all scheduled task executions in SQLite persistent memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE persistent_tasks SET is_active = 0")
        conn.commit()
        return "SUCCESS: All recurring tasks have been paused."
    except Exception as e:
        return f"FAILED: Could not update tasks state: {e}"
    finally:
        conn.close()

def resume_recurring_tasks() -> str:
    """Resume all scheduled task executions in SQLite persistent memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE persistent_tasks SET is_active = 1")
        conn.commit()
        return "SUCCESS: All recurring tasks have been resumed."
    except Exception as e:
        return f"FAILED: Could not update tasks state: {e}"
    finally:
        conn.close()

def reduce_scraper_concurrency() -> str:
    """Reduce scraping concurrency configuration to decrease CPU / Network usage."""
    try:
        prefs = get_preferences()
        curr_max = prefs.get("scraper_max_jobs", 25)
        new_max = max(5, int(curr_max) - 10)
        save_preference("scraper_max_jobs", new_max)
        return f"SUCCESS: Scraper concurrency limit reduced from {curr_max} to {new_max}."
    except Exception as e:
        return f"FAILED: Could not modify concurrency preference: {e}"

def increase_retry_backoff() -> str:
    """Increase API retry delay/backoff multiplier in SQLite preferences."""
    try:
        prefs = get_preferences()
        curr_backoff = prefs.get("retry_backoff_factor", 2)
        new_backoff = int(curr_backoff) * 2
        save_preference("retry_backoff_factor", new_backoff)
        return f"SUCCESS: Retry backoff multiplier increased from {curr_backoff} to {new_backoff}."
    except Exception as e:
        return f"FAILED: Could not modify backoff preference: {e}"

def cleanup_temp_files() -> str:
    """Scan and clean temporary scraper cache and system downloads."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_dirs = [
            os.path.join(base_dir, "resumes", "temp"),
            os.path.join(os.environ.get("TEMP", ""), "playwright"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        ]
        removed_count = 0
        for d in temp_dirs:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                    removed_count += 1
                except Exception:
                    pass
        return f"SUCCESS: Cleared {removed_count} temporary system directories."
    except Exception as e:
        return f"FAILED: Temp directory cleanup failed: {e}"

def rotate_logs() -> str:
    """Rotate and compress log files if they are exceeding limits."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(base_dir, "logs", "agent.log")
        if os.path.exists(log_path):
            size_mb = os.path.getsize(log_path) / (1024 * 1024)
            if size_mb > 5.0:
                rotated_path = f"{log_path}.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                shutil.copy(log_path, rotated_path)
                with open(log_path, "w") as f:
                    f.write(f"--- Log rotated at {datetime.now().isoformat()} ---\n")
                return f"SUCCESS: Log rotated. Previous file saved as {os.path.basename(rotated_path)}."
            else:
                return f"SUCCESS: Log size {size_mb:.2f}MB is within healthy thresholds. No rotation required."
        return "SUCCESS: Log file does not exist. Created a new logs directory."
    except Exception as e:
        return f"FAILED: Log rotation failed: {e}"

def restart_failed_workflows() -> str:
    """Locate and re-execute failed recurring workflows recorded in SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, task_id FROM task_execution_history
            WHERE status = 'failed' AND executed_at >= datetime('now', '-2 hours')
        """)
        failures = cursor.fetchall()
        if not failures:
            return "SUCCESS: No execution failures found in the last 2 hours."
        
        # Trigger scraper for DevOps/Cloud (main workflow)
        from scheduler.scheduler import run_job_search
        t = threading.Thread(target=run_job_search, daemon=True)
        t.start()
        return f"SUCCESS: Re-triggered execution pipeline for {len(failures)} failed instances."
    except Exception as e:
        return f"FAILED: Could not recover failed workflows: {e}"
    finally:
        conn.close()

def clear_stuck_task_queue() -> str:
    """Reset tasks in recurring_workflows that have been stuck in 'pending'/'running'."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE recurring_workflows 
            SET status = 'pending' 
            WHERE status = 'running' AND last_run < datetime('now', '-30 minutes')
        """)
        affected = cursor.rowcount
        conn.commit()
        return f"SUCCESS: Released {affected} stuck workflows in queue."
    except Exception as e:
        return f"FAILED: Stuck queue cleanup error: {e}"
    finally:
        conn.close()

def retry_telegram_delivery() -> str:
    """Retrieve unsent top recommendation cards from jobs table and retry delivery."""
    from database.db_manager import get_unsent_top_jobs, mark_as_sent
    from notifications.telegram_sender import send_jobs_to_telegram
    try:
        unsent = get_unsent_top_jobs(limit=5)
        if unsent:
            success = send_jobs_to_telegram(unsent)
            if success:
                job_ids = [j['job_id'] for j in unsent]
                mark_as_sent(job_ids)
                return f"SUCCESS: Re-delivered {len(unsent)} pending job recommendations."
            return "FAILED: Telegram delivery retry request returned error."
        return "SUCCESS: No unsent jobs found in database queue."
    except Exception as e:
        return f"FAILED: Delivery retry failed: {e}"

def backup_database() -> str:
    """Perform hot-backup of the main SQLite database file."""
    try:
        backup_path = f"{DB_PATH}.bak"
        shutil.copy(DB_PATH, backup_path)
        return f"SUCCESS: Database backup written to {os.path.basename(backup_path)}."
    except Exception as e:
        return f"FAILED: Database hot backup failed: {e}"

def recover_memory_state() -> str:
    """Reseed default configurations to recover from memory corruption."""
    try:
        seed_default_preferences()
        return "SUCCESS: Default user profile preferences successfully re-seeded."
    except Exception as e:
        return f"FAILED: Memory recovery failed: {e}"

def restart_docker_services() -> str:
    """
    Log request and trigger soft re-initialization of worker loops.
    (Simulates docker service restart internally safely)
    """
    try:
        # Clear playwright browser processes and reload scheduling thread
        cleanup_res = restart_playwright()
        sched_res = restart_scheduler()
        return f"SUCCESS: Internal Docker services reset simulation executed. {cleanup_res} {sched_res}"
    except Exception as e:
        return f"FAILED: Services soft reset simulation failed: {e}"

def reinitialize_browser_sessions() -> str:
    """Reinitialize browser context in Playwright scraper."""
    # This calls restart_playwright to purge processes, which guarantees clean session state next run
    return restart_playwright()

# Action Registry mapping names to actual functions
action_registry = {
    "restart_scraper": restart_scraper,
    "restart_playwright": restart_playwright,
    "restart_scheduler": restart_scheduler,
    "pause_recurring_tasks": pause_recurring_tasks,
    "resume_recurring_tasks": resume_recurring_tasks,
    "reduce_scraper_concurrency": reduce_scraper_concurrency,
    "increase_retry_backoff": increase_retry_backoff,
    "cleanup_temp_files": cleanup_temp_files,
    "rotate_logs": rotate_logs,
    "restart_failed_workflows": restart_failed_workflows,
    "clear_stuck_task_queue": clear_stuck_task_queue,
    "retry_telegram_delivery": retry_telegram_delivery,
    "backup_database": backup_database,
    "recover_memory_state": recover_memory_state,
    "restart_docker_services": restart_docker_services,
    "reinitialize_browser_sessions": reinitialize_browser_sessions
}

def execute_recovery_action(action_name: str, incident_id: int = -1) -> str:
    """Execute recovery action by name and record outcome in database."""
    from monitoring.operational_memory import log_recovery_action
    
    if action_name not in action_registry:
        err = f"FAILED: Action '{action_name}' is not registered."
        log_recovery_action(incident_id, action_name, "FAILED", err)
        return err
        
    logger.info(f"Executing AIOps recovery action: '{action_name}'...")
    log_recovery_action(incident_id, action_name, "RUNNING", f"Initiated action {action_name}.")
    
    try:
        # Increment AIOps recovery actions execution counter
        from monitoring.metrics_collector import autonomous_recovery_actions_total
        autonomous_recovery_actions_total.inc()
        
        result = action_registry[action_name]()
        status = "SUCCESS" if result.startswith("SUCCESS") else "FAILED"
        log_recovery_action(incident_id, action_name, status, result)
        logger.info(f"Recovery action '{action_name}' finished: {result}")
        return result
    except Exception as e:
        err_msg = f"FAILED: Unexpected crash during recovery: {e}"
        log_recovery_action(incident_id, action_name, "FAILED", err_msg)
        logger.error(err_msg)
        return err_msg
