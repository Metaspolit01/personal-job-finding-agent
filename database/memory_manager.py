import sqlite3
import json
import logging
from config.settings import DB_PATH

logger = logging.getLogger(__name__)

def get_preferences() -> dict:
    """Retrieve all user preferences from the database as a key-value dictionary."""
    try:
        from monitoring.metrics_collector import memory_hits_total
        memory_hits_total.inc()
    except ImportError:
        pass
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pref_key, pref_value FROM preferences")
    rows = cursor.fetchall()
    conn.close()
    
    preferences = {}
    for key, value in rows:
        try:
            preferences[key] = json.loads(value)
        except json.JSONDecodeError:
            preferences[key] = value
    return preferences

def save_preference(key: str, value) -> bool:
    """Save or update a preference. Lists and dicts are serialized as JSON strings."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if isinstance(value, (list, dict)):
        serialized_val = json.dumps(value)
    else:
        serialized_val = str(value)
        
    try:
        cursor.execute("""
            INSERT INTO preferences (pref_key, pref_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pref_key) DO UPDATE SET
                pref_value = excluded.pref_value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, serialized_val))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save preference '{key}': {e}")
        return False
    finally:
        conn.close()

def add_conversation_turn(role: str, content: str, session_id: str = "default"):
    """Append a message turn to the persistent conversation memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO conversation_memory (session_id, role, content)
            VALUES (?, ?, ?)
        """, (session_id, role, content))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to add conversation turn: {e}")
    finally:
        conn.close()

def get_conversation_history(limit: int = 15, session_id: str = "default") -> list:
    """Retrieve the rolling conversation history as a list of dicts: [{'role': ..., 'content': ...}]."""
    try:
        from monitoring.metrics_collector import memory_hits_total
        memory_hits_total.inc()
    except ImportError:
        pass
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT role, content FROM conversation_memory
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (session_id, limit))
        rows = cursor.fetchall()
        # Return in chronological order
        history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return history
    except Exception as e:
        logger.error(f"Failed to fetch conversation history: {e}")
        return []
    finally:
        conn.close()

def clear_conversation_history(session_id: str = "default"):
    """Clear conversation history for a given session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM conversation_memory WHERE session_id = ?", (session_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to clear conversation history: {e}")
    finally:
        conn.close()

def record_job_interaction(job_id: str, action: str, details: dict = None):
    """
    Record user interaction with a job (e.g. 'click', 'apply', 'ignore').
    Also updates jobs_seen status and writes to applied_jobs/ignored_jobs.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    details_str = json.dumps(details) if details else "{}"
    
    try:
        # 1. Log to interaction_history
        cursor.execute("""
            INSERT INTO interaction_history (action, entity_type, entity_id, details)
            VALUES (?, 'job', ?, ?)
        """, (action, job_id, details_str))
        
        # 2. Update status in jobs_seen
        status = 'seen'
        if action == 'apply':
            status = 'applied'
            cursor.execute("INSERT OR REPLACE INTO applied_jobs (job_id) VALUES (?)", (job_id,))
            cursor.execute("""
                INSERT INTO recommendation_feedback (job_id, feedback_type, comments)
                VALUES (?, ?, ?)
            """, (job_id, 'apply', 'Marked applied via Telegram Bot'))
        elif action == 'ignore':
            status = 'ignored'
            cursor.execute("INSERT OR REPLACE INTO ignored_jobs (job_id) VALUES (?)", (job_id,))
            cursor.execute("""
                INSERT INTO recommendation_feedback (job_id, feedback_type, comments)
                VALUES (?, ?, ?)
            """, (job_id, 'ignore', 'Marked ignored via Telegram Bot'))
        elif action == 'click':
            status = 'clicked'
            
        cursor.execute("UPDATE jobs_seen SET status = ? WHERE job_id = ?", (status, job_id))
        
        # Also update main jobs table status for compatibility
        if action == 'apply':
            cursor.execute("UPDATE jobs SET sent_to_telegram = 1 WHERE job_id = ?", (job_id,))
            
        conn.commit()
        logger.info(f"Recorded '{action}' interaction for job '{job_id}'")
        return True
    except Exception as e:
        logger.error(f"Failed to record interaction '{action}' for job '{job_id}': {e}")
        return False
    finally:
        conn.close()

def get_job_details(job_id: str) -> dict:
    """Retrieve full details of a seen job."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_seen WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_scoring_run(job_id: str, tfidf_score: float, llm_score: float, adaptive_bonus: float, final_score: float, resume_version: str = "v1"):
    """Log individual scoring executions for transparency and audits."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO scoring_history (job_id, resume_version, tfidf_score, llm_score, adaptive_bonus, final_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, resume_version, tfidf_score, llm_score, adaptive_bonus, final_score))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log scoring run for job '{job_id}': {e}")
    finally:
        conn.close()

def seed_default_preferences():
    """Seed initial interests if none exist."""
    prefs = get_preferences()
    if 'preferred_roles' not in prefs:
        save_preference('preferred_roles', ["DevOps", "Cloud Engineer", "Kubernetes", "Platform Engineer", "SRE"])
    if 'preferred_technologies' not in prefs:
        save_preference('preferred_technologies', ["Kubernetes", "Docker", "Terraform", "AWS", "Python", "Linux", "CI/CD"])
    if 'rejected_companies' not in prefs:
        save_preference('rejected_companies', ["IgnoredInc", "StaffingLtd"])

def auto_extract_profile_memory(text: str) -> bool:
    """
    Search for name assignments in text (e.g. 'my name is Tom' or 'your name is Tom') 
    and save them to the persistent profile memory.
    """
    import re
    text_lower = text.lower().strip()
    
    # 1. Match "your name is X" / "you are X" / "call you X"
    agent_match = re.search(r"(?:your name is|you are called|call yourself|i will call you|your name will be)\s+([a-zA-Z0-9_\s]{1,20})", text_lower)
    if agent_match:
        name = agent_match.group(1).strip().title()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            # Delete any previous agent name records first to keep it unique
            cursor.execute("DELETE FROM memory_entries WHERE category = 'user_profile' AND key = 'agent_name'")
            cursor.execute("""
                INSERT INTO memory_entries (category, key, value, confidence)
                VALUES ('user_profile', 'agent_name', ?, 1.0)
            """, (name,))
            conn.commit()
            logger.info(f"Auto-extracted Agent Name: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save extracted agent name: {e}")
        finally:
            conn.close()
            
    # 2. Match "my name is X" / "call me X"
    user_match = re.search(r"(?:my name is|call me)\s+([a-zA-Z0-9_\s]{1,20})", text_lower)
    if user_match:
        name = user_match.group(1).strip()
        if len(name.split()) <= 2: # Name is usually 1 or 2 words
            name = name.title()
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                # Delete any previous user name records
                cursor.execute("DELETE FROM memory_entries WHERE category = 'user_profile' AND key = 'user_name'")
                cursor.execute("""
                    INSERT INTO memory_entries (category, key, value, confidence)
                    VALUES ('user_profile', 'user_name', ?, 1.0)
                """, (name,))
                conn.commit()
                logger.info(f"Auto-extracted User Name: {name}")
                return True
            except Exception as e:
                logger.error(f"Failed to save extracted user name: {e}")
            finally:
                conn.close()
                
    return False

def save_persistent_task(task_id: str, description: str, interval_hours: float, is_active: bool = True) -> bool:
    """Save or update a persistent recurring task in SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO persistent_tasks (task_id, task_description, schedule_interval_hours, is_active, next_run)
            VALUES (?, ?, ?, ?, datetime('now', '+' || ? || ' hour'))
            ON CONFLICT(task_id) DO UPDATE SET
                task_description = excluded.task_description,
                schedule_interval_hours = excluded.schedule_interval_hours,
                is_active = excluded.is_active,
                next_run = datetime('now', '+' || excluded.schedule_interval_hours || ' hour')
        """, (task_id, description, interval_hours, 1 if is_active else 0, interval_hours))
        conn.commit()
        logger.info(f"Saved persistent task '{task_id}' (interval: {interval_hours}h)")
        return True
    except Exception as e:
        logger.error(f"Failed to save persistent task: {e}")
        return False
    finally:
        conn.close()

def get_active_tasks() -> list:
    """Retrieve all active persistent tasks."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM persistent_tasks WHERE is_active = 1")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to retrieve active tasks: {e}")
        return []
    finally:
        conn.close()

def log_task_execution(task_id: str, status: str, log_text: str):
    """Record execution status and logs for persistent tasks."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO task_execution_history (task_id, status, output_log)
            VALUES (?, ?, ?)
        """, (task_id, status, log_text))
        cursor.execute("""
            UPDATE persistent_tasks 
            SET last_run = datetime('now'),
                next_run = datetime('now', '+' || schedule_interval_hours || ' hour')
            WHERE task_id = ?
        """, (task_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log task execution: {e}")
    finally:
        conn.close()

def save_recommendation_feedback(job_id: str, feedback_type: str, comments: str = None) -> bool:
    """Save feedback for job recommendations."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO recommendation_feedback (job_id, feedback_type, comments)
            VALUES (?, ?, ?)
        """, (job_id, feedback_type, comments))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save recommendation feedback: {e}")
        return False
    finally:
        conn.close()

def save_automation_rule(rule_name: str, rule_type: str, rule_value: str) -> bool:
    """Insert or update an automation rule."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO automation_rules (rule_name, rule_type, rule_value)
            VALUES (?, ?, ?)
            ON CONFLICT(rule_name) DO UPDATE SET
                rule_type = excluded.rule_type,
                rule_value = excluded.rule_value
        """, (rule_name, rule_type, rule_value))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save automation rule: {e}")
        return False
    finally:
        conn.close()

def log_preference_update(pref_key: str, old_value: str, new_value: str) -> bool:
    """Log preference changes over time."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO preference_updates (pref_key, old_value, new_value)
            VALUES (?, ?, ?)
        """, (pref_key, old_value, new_value))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to log preference update: {e}")
        return False
    finally:
        conn.close()

def save_user_instruction(instruction_text: str, is_processed: bool = False) -> bool:
    """Log a raw user instruction."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_instructions (instruction_text, is_processed)
            VALUES (?, ?)
        """, (instruction_text, 1 if is_processed else 0))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save user instruction: {e}")
        return False
    finally:
        conn.close()

def get_recurring_workflows() -> list:
    """Retrieve recurring workflow settings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM recurring_workflows")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to retrieve recurring workflows: {e}")
        return []
    finally:
        conn.close()

def save_recurring_workflow(workflow_name: str, task_id: str, status: str = 'pending') -> bool:
    """Save recurring workflow definitions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO recurring_workflows (workflow_name, task_id, status)
            VALUES (?, ?, ?)
        """, (workflow_name, task_id, status))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save recurring workflow: {e}")
        return False
    finally:
        conn.close()

def update_workflow_status(workflow_id: int, status: str) -> bool:
    """Update recurring workflow step status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE recurring_workflows
            SET status = ?, last_run = datetime('now')
            WHERE id = ?
        """, (status, workflow_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update workflow status: {e}")
        return False
    finally:
        conn.close()
