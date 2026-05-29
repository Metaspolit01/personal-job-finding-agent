import json
import logging
import sqlite3
import requests
from config.settings import OLLAMA_API_URL, OLLAMA_MODEL, DB_PATH
from security.audit_logger import log_audit_action
from monitoring.operational_memory import (
    log_operational_incident,
    resolve_operational_incident,
    get_successful_recovery_strategy,
    log_successful_recovery_strategy
)
from monitoring.recovery_actions import execute_recovery_action

logger = logging.getLogger(__name__)

def determine_fallback_action(anomalies: list, metrics: dict) -> dict:
    """Deterministic rule-based fallback decision when local LLM is unreachable."""
    logger.info("Executing rule-based AIOps fallback decision engine...")
    
    if not anomalies:
        return {
            "incident_detected": False,
            "severity": "low",
            "reasoning": "Metrics are within healthy thresholds. No action required.",
            "recovery_action": None
        }

    # Order of priority for recovery actions
    for anomaly in anomalies:
        if "Playwright" in anomaly or "scraper_failures" in anomaly:
            return {
                "incident_detected": True,
                "severity": "high",
                "reasoning": "Playwright crashes or repeated scraper failures detected. Purging lingering browser processes.",
                "recovery_action": "restart_playwright"
            }
        if "CPU" in anomaly or "RAM" in anomaly:
            return {
                "incident_detected": True,
                "severity": "high",
                "reasoning": "High CPU/RAM usage detected. Decreasing scraper concurrency constraints.",
                "recovery_action": "reduce_scraper_concurrency"
            }
        if "Telegram" in anomaly:
            return {
                "incident_detected": True,
                "severity": "medium",
                "reasoning": "Telegram message delivery failed. Attempting queue re-delivery.",
                "recovery_action": "retry_telegram_delivery"
            }
        if "stuck" in anomaly:
            return {
                "incident_detected": True,
                "severity": "medium",
                "reasoning": "Stuck workflows found in execution queue. Resetting pending queue states.",
                "recovery_action": "clear_stuck_task_queue"
            }

    # Catch-all default action
    return {
        "incident_detected": True,
        "severity": "low",
        "reasoning": "Undetermined anomalies triggered. Performing log rotation and directory cleanup.",
        "recovery_action": "cleanup_temp_files"
    }

def analyze_and_heal(metrics: dict, anomalies: list) -> dict:
    """
    Query local Ollama using the configured model to analyze anomalies, select recovery action,
    execute it, and log/alert outcomes.
    """
    if not anomalies:
        return {"healed": False, "action": None, "details": "No anomalies present."}

    anomalies_str = "\n".join(f"- {a}" for a in anomalies)
    
    # Check historical operational memory for successful recovery strategies
    historical_strategies = []
    for anomaly in anomalies:
        matched_action = get_successful_recovery_strategy(anomaly)
        if matched_action:
            historical_strategies.append(f"For '{anomaly}', action '{matched_action}' succeeded previously.")
            
    historical_context = "\n".join(historical_strategies) if historical_strategies else "None"

    prompt = (
        f"You are the autonomous self-healing AI Operations Decision Engine for a local AI job search assistant.\n"
        f"Analyze the current system metrics, active anomalies, and historical recovery memory to choose a recovery action.\n\n"
        f"CURRENT SYSTEM METRICS:\n"
        f"- CPU Usage: {metrics['system']['cpu_usage']}%\n"
        f"- RAM Usage: {metrics['system']['ram_usage']}%\n"
        f"- Disk Usage: {metrics['system']['disk_usage']}%\n"
        f"- Scraper runs/failures: {metrics['app']['scraper_runs']} / {metrics['app']['scraper_failures']}\n"
        f"- Playwright crashes: {metrics['app']['playwright_crashes']}\n"
        f"- Telegram sends/failures: {metrics['app']['telegram_sends']} / {metrics['app']['telegram_failures']}\n"
        f"- Task execution failures: {metrics['app']['task_failures']}\n"
        f"- Stuck workflows: {metrics['app']['stuck_workflows']}\n\n"
        f"ACTIVE ANOMALIES:\n"
        f"{anomalies_str}\n\n"
        f"HISTORICAL STRATEGY MEMORY:\n"
        f"{historical_context}\n\n"
        f"AVAILABLE RECOVERY ACTIONS:\n"
        f"- restart_scraper: Re-triggers scraping workflow.\n"
        f"- restart_playwright: Purges lingering browser processes and resets driver.\n"
        f"- restart_scheduler: Forces scheduler execution run.\n"
        f"- pause_recurring_tasks: Disables recurring job searches temporarily.\n"
        f"- resume_recurring_tasks: Re-enables paused tasks.\n"
        f"- reduce_scraper_concurrency: Decreases max jobs to fetch to lower system load.\n"
        f"- increase_retry_backoff: Increases API delay multipliers.\n"
        f"- cleanup_temp_files: Clears browser caches and temporary PDF/text assets.\n"
        f"- rotate_logs: Rotates log files when exceeding limit.\n"
        f"- restart_failed_workflows: Re-runs failed tasks.\n"
        f"- clear_stuck_task_queue: Resets running statuses of stuck executions.\n"
        f"- retry_telegram_delivery: Dispatches failed message recommendation cards.\n"
        f"- backup_database: Creates DB hot-backup copy.\n"
        f"- recover_memory_state: Reseeds default user settings.\n"
        f"- restart_docker_services: soft restarts worker execution threads.\n"
        f"- reinitialize_browser_sessions: purges Playwright browser process handlers.\n\n"
        f"RESPONSE FORMAT INSTRUCTIONS:\n"
        f"You must respond ONLY with a single valid JSON object. Do not wrap your response in markdown backticks or output extra characters. "
        f"The JSON object must match this schema exactly:\n"
        f"{{\n"
        f"  \"incident_detected\": true,\n"
        f"  \"severity\": \"low/medium/high\",\n"
        f"  \"reasoning\": \"Detailed rationale behind this choice.\",\n"
        f"  \"recovery_action\": \"action_name\"\n"
        f"}}\n"
    )

    decision = None
    
    # Try querying Ollama
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    logger.info(f"Querying Ollama AIOps Decision Engine ({OLLAMA_MODEL})...")
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=25)
        response.raise_for_status()
        data = response.json()
        response_text = data.get("response", "").strip()
        decision = json.loads(response_text)
        log_audit_action(tool="aiops_decision_engine", action="reasoning", result="SUCCESS")
    except Exception as e:
        logger.warning(f"Ollama AIOps reasoning failed or timed out: {e}. Falling back to deterministic rules.")
        decision = determine_fallback_action(anomalies, metrics)
        log_audit_action(tool="aiops_decision_engine", action="reasoning", result="FALLBACK", details=str(e))

    # Validate decision structure
    if not decision or not isinstance(decision, dict):
        decision = determine_fallback_action(anomalies, metrics)

    incident_detected = decision.get("incident_detected", False)
    severity = decision.get("severity", "low")
    reasoning = decision.get("reasoning", "")
    recovery_action = decision.get("recovery_action")

    if not incident_detected or not recovery_action:
        logger.info("AIOps Decision: Metrics are normal. No healing action taken.")
        return {"healed": False, "action": None, "details": "No healing action recommended."}

    # Log incident to SQLite and obtain incident ID
    incident_id = log_operational_incident(
        category=f"{severity.upper()}_SEVERITY_INCIDENT",
        description=f"Anomalies: {anomalies_str}. Reasoning: {reasoning}"
    )

    logger.warning(f"AIOps Incident #{incident_id} detected! Severity: {severity}. Reasoning: {reasoning}")

    # Trigger recovery action
    action_result = execute_recovery_action(recovery_action, incident_id)
    
    success = action_result.startswith("SUCCESS")
    if success:
        # Resolve incident
        resolve_operational_incident(incident_id)
        # Learn: Record successful action mapping for this anomaly pattern
        for anomaly in anomalies:
            log_successful_recovery_strategy(anomaly, recovery_action)
            
    # Send user notification
    from monitoring.alert_manager import send_operational_alert
    alert_msg = (
        f"⚠️ **Incident Detected** (#{incident_id})\n"
        f"**Severity:** {severity.upper()}\n"
        f"**Reasoning:** {reasoning}\n\n"
        f"🔧 **Recovery Action Triggered:** `{recovery_action}`\n"
        f"**Result:** {action_result}"
    )
    send_operational_alert("Self-Healing Triggered", alert_msg)
    
    return {
        "healed": success,
        "action": recovery_action,
        "result": action_result,
        "incident_id": incident_id
    }
