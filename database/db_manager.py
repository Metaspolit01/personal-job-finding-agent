import sqlite3
import logging
from config.settings import DB_PATH

logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Existing jobs table for backwards compatibility
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            title TEXT,
            company TEXT,
            url TEXT,
            source TEXT,
            score REAL,
            sent_to_telegram BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Alter jobs table to add description if it doesn't exist
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN description TEXT")
    except sqlite3.OperationalError:
        pass # already exists

    # Drop RBAC tables to clean up RBAC architecture
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS permissions")
    
    # Only drop audit_logs if it still contains the legacy 'role' column
    try:
        cursor.execute("SELECT role FROM audit_logs LIMIT 1")
        cursor.execute("DROP TABLE IF EXISTS audit_logs")
    except sqlite3.OperationalError:
        pass # Already migrated

    # 1. preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pref_key TEXT UNIQUE NOT NULL,
            pref_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. jobs_seen table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs_seen (
            job_id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            url TEXT,
            source TEXT,
            score REAL,
            status TEXT DEFAULT 'seen',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Alter jobs_seen table to add description if it doesn't exist
    try:
        cursor.execute("ALTER TABLE jobs_seen ADD COLUMN description TEXT")
    except sqlite3.OperationalError:
        pass # already exists

    # 3. applied_jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            job_id TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs_seen(job_id)
        )
    """)

    # 4. ignored_jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ignored_jobs (
            job_id TEXT PRIMARY KEY,
            ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs_seen(job_id)
        )
    """)

    # 5. memory_entries table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            confidence REAL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 6. interaction_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interaction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 7. audit_logs table (without role)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tool TEXT,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            details TEXT
        )
    """)

    # 8. scoring_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            resume_version TEXT,
            tfidf_score REAL,
            llm_score REAL,
            adaptive_bonus REAL,
            final_score REAL,
            scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 9. conversation_memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT DEFAULT 'default',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 10. recommendation_feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 11. persistent_tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persistent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            task_description TEXT NOT NULL,
            schedule_interval_hours REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 12. recurring_workflows table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_name TEXT NOT NULL,
            task_id TEXT,
            status TEXT DEFAULT 'pending',
            last_run TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES persistent_tasks(task_id)
        )
    """)

    # 13. user_instructions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_instructions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instruction_text TEXT NOT NULL,
            is_processed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 14. automation_rules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT UNIQUE NOT NULL,
            rule_type TEXT NOT NULL,
            rule_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 15. task_execution_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            output_log TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 16. preference_updates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preference_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pref_key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 17. operational_incidents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operational_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)

    # 18. recovery_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovery_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER,
            action_name TEXT NOT NULL,
            status TEXT NOT NULL,
            logs TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES operational_incidents(id)
        )
    """)

    # 19. workflow_failures table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_name TEXT NOT NULL,
            failure_reason TEXT,
            failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 20. self_healing_actions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS self_healing_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER,
            action_type TEXT NOT NULL,
            result TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES operational_incidents(id)
        )
    """)

    # 21. operational_memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operational_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_pattern TEXT UNIQUE NOT NULL,
            successful_recovery_action TEXT NOT NULL,
            success_count INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 22. monitoring_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 23. anomaly_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            threshold_value REAL,
            observed_value REAL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 24. infrastructure_state_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS infrastructure_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpu_util REAL,
            ram_util REAL,
            disk_util REAL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 25. operational_alerts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operational_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_name TEXT NOT NULL,
            message TEXT NOT NULL,
            sent_to_telegram BOOLEAN DEFAULT 0,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def is_duplicate(job_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def save_job(job_data: dict, score: float):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Save to main jobs table
        cursor.execute("""
            INSERT INTO jobs (job_id, title, company, url, source, score, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_data.get('job_id'), job_data.get('title'), job_data.get('company'), job_data.get('url'), job_data.get('source'), score, job_data.get('description', '')))
        
        # Save to jobs_seen table for RBAC/memory tracking
        cursor.execute("""
            INSERT OR REPLACE INTO jobs_seen (job_id, title, company, url, source, score, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_data.get('job_id'), job_data.get('title'), job_data.get('company'), job_data.get('url'), job_data.get('source'), score, job_data.get('description', '')))
        
        conn.commit()
    except sqlite3.IntegrityError:
        pass # already exists
    conn.close()

def get_unsent_top_jobs(limit=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM jobs 
        WHERE sent_to_telegram = 0 
        ORDER BY score DESC 
        LIMIT ?
    """, (limit,))
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs

def mark_as_sent(job_ids: list):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE jobs SET sent_to_telegram = 1 WHERE job_id IN ({','.join(['?']*len(job_ids))})", job_ids)
    conn.commit()
    conn.close()
