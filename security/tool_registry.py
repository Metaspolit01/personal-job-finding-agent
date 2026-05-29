import os
import sqlite3
import logging
from typing import Callable, Any, Dict, List
from config.settings import DB_PATH, BOT_TOKEN, CHAT_ID
from security.audit_logger import log_audit_action

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name: str, description: str, parameters: dict):
        """Decorator to register a tool with metadata."""
        def decorator(func: Callable[..., Any]):
            self.tools[name] = {
                "name": name,
                "description": description,
                "parameters": parameters,
                "func": func
            }
            return func
        return decorator

    def get_tools_metadata(self) -> list:
        """Return schema metadata for all registered tools."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"]
            }
            for t in self.tools.values()
        ]

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Invoke a tool by name with arguments, auditing the call."""
        if name not in self.tools:
            log_audit_action(name, "tool_invocation", "FAILED", f"Tool not found. Args: {arguments}")
            raise ValueError(f"Tool '{name}' is not registered.")
        
        log_audit_action(name, "tool_invocation", "RUNNING", f"Arguments: {arguments}")
        try:
            # Check for missing required arguments or resolve keyword defaults
            result = self.tools[name]["func"](**arguments)
            log_audit_action(name, "tool_invocation", "SUCCESS", f"Execution successful.")
            return result
        except Exception as e:
            log_audit_action(name, "tool_invocation", "FAILED", f"Error: {e}")
            logger.error(f"Error executing tool '{name}': {e}")
            return f"Error executing tool '{name}': {e}"

# Global Tool Registry Instance
registry = ToolRegistry()

# ==================================================
# APPROVED SAFE AUTOMATION TOOLS
# ==================================================

@registry.register(
    name="search_jobs",
    description="Crawl and scrape job boards (LinkedIn) for internships, freshers, or junior roles matching specified keywords.",
    parameters={
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keywords to search for, e.g. ['DevOps Intern', 'Cloud Intern']."
            },
            "location": {
                "type": "string",
                "description": "Location to search in. Defaults to 'India'."
            },
            "max_jobs": {
                "type": "integer",
                "description": "Maximum number of jobs to fetch. Defaults to 15."
            }
        },
        "required": ["keywords"]
    }
)
def tool_search_jobs(keywords: list, location: str = "India", max_jobs: int = 15) -> list:
    from scraper.scraper import scrape_linkedin_jobs
    logger.info(f"Tool search_jobs called: keywords={keywords}, location={location}, max={max_jobs}")
    return scrape_linkedin_jobs(keywords, location=location, max_jobs=max_jobs)


@registry.register(
    name="rank_jobs",
    description="Evaluate and rank a list of job listings against the user's active resume text using hybrid scoring.",
    parameters={
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "title": {"type": "string"},
                        "company": {"type": "string"},
                        "description": {"type": "string"},
                        "url": {"type": "string"},
                        "source": {"type": "string"}
                    },
                    "required": ["job_id", "title", "company", "description"]
                },
                "description": "List of raw job dictionaries to score."
            }
        },
        "required": ["jobs"]
    }
)
def tool_rank_jobs(jobs: list) -> list:
    from matching.scorer import calculate_final_score
    from resumes.resume_parser import load_resume_text
    from database.db_manager import save_job
    
    resume_text = load_resume_text()
    ranked_jobs = []
    
    for job in jobs:
        score = calculate_final_score(
            job_desc=job.get("description", ""),
            resume_text=resume_text,
            job_title=job.get("title", ""),
            job_company=job.get("company", ""),
            job_id=job.get("job_id", "")
        )
        job_copy = job.copy()
        job_copy["score"] = round(score, 2)
        save_job(job_copy, score)
        ranked_jobs.append(job_copy)
        
    return sorted(ranked_jobs, key=lambda x: x.get("score", 0.0), reverse=True)


@registry.register(
    name="update_memory",
    description="Update or save persistent memory items (roles, technologies, or rejected companies) in SQLite.",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["preferred_roles", "preferred_technologies", "rejected_companies", "user_profile"],
                "description": "Memory category to modify."
            },
            "key": {
                "type": "string",
                "description": "Key identifier or rule description."
            },
            "value": {
                "type": "string",
                "description": "The value or values to set. If updating preference lists, format as a comma-separated string."
            }
        },
        "required": ["category", "key", "value"]
    }
)
def tool_update_memory(category: str, key: str, value: str) -> bool:
    from database.memory_manager import save_preference, get_preferences
    
    if category in ["preferred_roles", "preferred_technologies", "rejected_companies"]:
        # Update preference lists
        prefs = get_preferences()
        current_list = prefs.get(category, [])
        new_items = [v.strip() for v in value.split(",") if v.strip()]
        for item in new_items:
            if item not in current_list:
                current_list.append(item)
        save_preference(category, current_list)
        logger.info(f"Updated preferences list '{category}': {current_list}")
        return True
    else:
        # Save custom semantic key-value rule in memory_entries
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO memory_entries (category, key, value, confidence)
                VALUES (?, ?, ?, 1.0)
            """, (category, key, value))
            conn.commit()
            logger.info(f"Saved memory entry: category={category}, key={key}, value={value}")
            return True
        except Exception as e:
            logger.error(f"Failed to update memory_entries: {e}")
            return False
        finally:
            conn.close()


@registry.register(
    name="read_memory",
    description="Retrieve dynamic memory entries or preference profiles from the SQLite database by category.",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["preferred_roles", "preferred_technologies", "rejected_companies", "user_profile", "all"],
                "description": "Category of memory to fetch."
            }
        },
        "required": ["category"]
    }
)
def tool_read_memory(category: str) -> dict:
    from database.memory_manager import get_preferences
    
    if category == "all":
        prefs = get_preferences()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT category, key, value FROM memory_entries")
        entries = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"preferences": prefs, "memory_entries": entries}
    elif category in ["preferred_roles", "preferred_technologies", "rejected_companies"]:
        prefs = get_preferences()
        return {category: prefs.get(category, [])}
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM memory_entries WHERE category = ?", (category,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {category: rows}


@registry.register(
    name="create_recurring_task",
    description="Create a persistent recurring monitoring task or search workflow that triggers automatically.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Unique task slug, e.g. 'monitor_devops_daily'."
            },
            "task_description": {
                "type": "string",
                "description": "Human-readable description of what this task does."
            },
            "schedule_interval_hours": {
                "type": "number",
                "description": "Interval between executions in hours (e.g. 24 for daily, 12 for semi-daily)."
            }
        },
        "required": ["task_id", "task_description", "schedule_interval_hours"]
    }
)
def tool_create_recurring_task(task_id: str, task_description: str, schedule_interval_hours: float) -> bool:
    from database.memory_manager import save_persistent_task
    logger.info(f"Creating recurring task '{task_id}': '{task_description}' every {schedule_interval_hours} hours.")
    return save_persistent_task(task_id, task_description, schedule_interval_hours)


@registry.register(
    name="execute_workflow",
    description="Orchestrate and execute a specified job search or data processing workflow chain immediately.",
    parameters={
        "type": "object",
        "properties": {
            "workflow_name": {
                "type": "string",
                "enum": ["scrape_and_notify", "database_cleanup"],
                "description": "Name of the workflow sequence to execute."
            }
        },
        "required": ["workflow_name"]
    }
)
def tool_execute_workflow(workflow_name: str) -> str:
    if workflow_name == "scrape_and_notify":
        from scheduler.scheduler import run_job_search
        logger.info("Executing scraping and notification workflow...")
        success = run_job_search()
        return f"Scrape and notify workflow finished. New jobs dispatched: {success}"
    elif workflow_name == "database_cleanup":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM jobs WHERE created_at < datetime('now', '-30 days')")
        deleted = c.rowcount
        conn.commit()
        conn.close()
        return f"Cleaned up {deleted} jobs older than 30 days."
    return f"Workflow '{workflow_name}' is not recognized."


@registry.register(
    name="send_telegram",
    description="Send a direct message or alert to the user's Telegram chat.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Markdown formatted message text to transmit."
            }
        },
        "required": ["message"]
    }
)
def tool_send_telegram(message: str) -> bool:
    import requests
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram Bot Token or Chat ID not configured.")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send direct telegram alert: {e}")
        return False


@registry.register(
    name="summarize_jobs",
    description="Create a human-readable summary digest of job list dictionaries.",
    parameters={
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "company": {"type": "string"},
                        "score": {"type": "number"}
                    }
                },
                "description": "List of job dictionaries containing 'title', 'company', and 'score'."
            }
        },
        "required": ["jobs"]
    }
)
def tool_summarize_jobs(jobs: list) -> str:
    if not jobs:
        return "No job postings matched or provided for summary."
        
    summary = "📋 **AI Recommended Jobs Summary:**\n\n"
    for idx, job in enumerate(jobs, start=1):
        summary += f"{idx}. **{job.get('title')}** at *{job.get('company')}* (Score: {job.get('score')}/100)\n"
    return summary


@registry.register(
    name="analyze_resume",
    description="Retrieve and read the active text contents of the user's resume.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def tool_analyze_resume() -> str:
    from resumes.resume_parser import load_resume_text
    return load_resume_text()


@registry.register(
    name="retrieve_preferences",
    description="Retrieve the configured preferences profile (preferred roles, target tech stack, suppressed list) directly.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def tool_retrieve_preferences() -> dict:
    from database.memory_manager import get_preferences
    return get_preferences()


@registry.register(
    name="log_action",
    description="Log a custom operational action directly into the agent audit trail.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Name of the custom action or event."
            },
            "details": {
                "type": "string",
                "description": "Detailed description or payload associated with the action."
            }
        },
        "required": ["action", "details"]
    }
)
def tool_log_action(action: str, details: str) -> bool:
    log_audit_action(tool="agent_custom", action=action, result="SUCCESS", details=details)
    return True
