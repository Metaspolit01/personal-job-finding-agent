import time
import schedule
import logging
import os
import socket
import subprocess
import threading
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config.settings import LOG_CONFIG, BOT_TOKEN
from scheduler.scheduler import run_job_search
from notifications.telegram_bot import (
    start_command,
    chat_handler,
    list_jobs_command,
    resume_upload_handler,
    memory_command,
    callback_query_handler,
    id_command
)
from database.db_manager import init_db
from database.memory_manager import seed_default_preferences

# Configure main logger
logging.basicConfig(**LOG_CONFIG)
logger = logging.getLogger(__name__)

INSTANCE_LOCK_PORT = 47839
_instance_lock_socket = None


def find_existing_main_processes():
    if os.name != "nt":
        return []

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process "
                    "-Filter \"name = 'python.exe' or name = 'pythonw.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'main\\.py' } | "
                    "Select-Object ProcessId,CommandLine | ConvertTo-Json"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if not result.stdout.strip():
        return []

    import json

    try:
        processes = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(processes, dict):
        processes = [processes]

    current_pid = os.getpid()
    parent_pid = os.getppid() if hasattr(os, "getppid") else None
    return [
        process
        for process in processes
        if int(process.get("ProcessId", current_pid)) not in (current_pid, parent_pid)
    ]


def acquire_instance_lock():
    """Prevent two local bot pollers from running with the same Telegram token."""
    global _instance_lock_socket

    existing_processes = find_existing_main_processes()
    if existing_processes:
        process_ids = ", ".join(str(p["ProcessId"]) for p in existing_processes)
        logger.error(
            "Another Job Finder Agent process is already running with PID(s): %s. "
            "Start only one copy for this Telegram bot token.",
            process_ids,
        )
        return False

    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        lock_socket.bind(("127.0.0.1", INSTANCE_LOCK_PORT))
        lock_socket.listen(1)
    except OSError:
        lock_socket.close()
        logger.error(
            "Another Job Finder Agent instance is already running on this machine. "
            "Start only one copy for this Telegram bot token."
        )
        return False

    _instance_lock_socket = lock_socket
    return True

def execute_active_tasks():
    """Fetch and execute due persistent tasks from SQLite."""
    import sqlite3
    from database.memory_manager import log_task_execution, get_active_tasks
    from scheduler.scheduler import run_job_search
    from config.settings import DB_PATH
    
    # Update active task gauge
    try:
        from monitoring.metrics_collector import recurring_tasks_active
        recurring_tasks_active.set(len(get_active_tasks()))
    except Exception:
        pass

    logger.info("Checking SQLite for due persistent tasks...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT * FROM persistent_tasks 
            WHERE is_active = 1 
              AND (last_run IS NULL OR next_run <= datetime('now'))
        """)
        due_tasks = [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Error querying due tasks: {e}")
        due_tasks = []
    finally:
        conn.close()
        
    if not due_tasks:
        logger.info("No due persistent tasks found.")
        return
        
    for task in due_tasks:
        task_id = task["task_id"]
        logger.info(f"Executing due task: {task_id} ('{task['task_description']}')")
        try:
            # Execute job search sequence
            success = run_job_search()
            log_task_execution(task_id, "success", f"Execution finished. Search status: {success}")
        except Exception as e:
            from monitoring.metrics_collector import workflow_failures_total
            workflow_failures_total.inc()
            log_task_execution(task_id, "failed", f"Execution error: {e}")
            logger.error(f"Persistent task '{task_id}' failed: {e}")

def scheduler_thread():
    logger.info("Starting persistent task scheduler thread...")
    try:
        execute_active_tasks()
    except Exception as e:
        logger.error(f"Error during initial task check: {e}")
        
    # Poll for due tasks every 5 minutes
    schedule.every(5).minutes.do(execute_active_tasks)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logger.error(f"Unexpected error in scheduler loop: {e}")
            time.sleep(60)

def main():
    logger.info("Starting Job Finder Agent...")

    if not acquire_instance_lock():
        return
    
    # Initialize SQLite database schema & seed standard preferences on boot
    logger.info("Initializing database schema...")
    init_db()
    
    logger.info("Seeding default user preferences...")
    seed_default_preferences()
    
    # Start AIOps self-monitoring engine
    from monitoring.self_monitor_agent import start_monitoring
    start_monitoring()
    
    # Start the job scraping schedule in a background thread
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()
    
    # Start the Telegram interactive bot on the main thread
    if BOT_TOKEN:
        logger.info("Starting interactive Telegram bot on main thread...")
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("list", list_jobs_command))
        application.add_handler(CommandHandler("memory", memory_command))
        application.add_handler(CommandHandler("id", id_command))
        application.add_handler(CallbackQueryHandler(callback_query_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
        application.add_handler(MessageHandler(filters.Document.ALL, resume_upload_handler))
        
        # This will block forever to listen for your messages
        application.run_polling()
    else:
        logger.error("No TELEGRAM_BOT_TOKEN found. Cannot start interactive bot. Exiting.")

if __name__ == "__main__":
    main()
