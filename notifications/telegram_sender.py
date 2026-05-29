import logging
from html import escape
import requests
from config.settings import BOT_TOKEN, CHAT_ID

logger = logging.getLogger(__name__)

def _format_job_message(idx: int, job: dict) -> str:
    title = escape(str(job.get("title") or "Untitled role"))
    company = escape(str(job.get("company") or "Unknown company"))
    url = escape(str(job.get("url") or ""))
    score = float(job.get("score") or 0)
    source = escape(str(job.get("source") or "LinkedIn"))
    
    apply_line = f'<a href="{url}">View Posting</a>' if url else "Apply link unavailable"

    return (
        f"<b>🎯 Recommendation #{idx}</b> (Score: {score:.1f}/100)\n\n"
        f"💼 <b>Role:</b> {title}\n"
        f"🏢 <b>Company:</b> {company}\n"
        f"🌐 <b>Source:</b> {source}\n\n"
        f"🔗 {apply_line}\n"
    )

def send_jobs_to_telegram(jobs: list, chat_id: str = None) -> bool:
    target_chat_id = chat_id or CHAT_ID
    if not BOT_TOKEN or not target_chat_id:
        logger.warning("Telegram Bot Token or Chat ID not configured. Skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # 1. Send each job as an individual card with inline action buttons
    all_success = True
    for idx, job in enumerate(jobs, start=1):
        job_id = job.get("job_id", "")
        message_text = _format_job_message(idx, job)
        
        payload = {
            "chat_id": target_chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "💼 Mark Applied", "callback_data": f"apply:{job_id}"},
                        {"text": "❌ Ignore Job", "callback_data": f"ignore:{job_id}"}
                    ]
                ]
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            
            # Increment Prometheus success metric
            from monitoring.metrics_collector import telegram_messages_sent_total
            telegram_messages_sent_total.inc()
            
            # Log successful Telegram dispatch
            from security.audit_logger import log_audit_action
            log_audit_action(
                action="telegram_send",
                tool="send_jobs_to_telegram",
                role="admin",
                result="SUCCESS",
                details=f"Dispatched card for job_id '{job_id}'"
            )
        except requests.exceptions.HTTPError as e:
            # Increment Prometheus failure metric
            from monitoring.metrics_collector import workflow_failures_total
            workflow_failures_total.inc()
            
            resp_body = ""
            try:
                resp_body = e.response.text
            except Exception:
                pass
            if e.response is not None and e.response.status_code == 400 and "chat not found" in resp_body:
                logger.error(
                    f"Failed to send job card {job_id}: 400 Bad Request - Chat not found. "
                    f"Your TELEGRAM_CHAT_ID in .env is likely invalid or the bot has not been started. "
                    f"Please send the /id command to your Telegram bot to get your Chat ID, update .env, and restart main.py."
                )
            else:
                logger.error(f"Failed to send job card {job_id}: HTTP error: {e} - Response: {resp_body}")
            all_success = False
        except Exception as e:
            # Increment Prometheus failure metric
            from monitoring.metrics_collector import workflow_failures_total
            workflow_failures_total.inc()
            
            logger.error(f"Failed to send job card {job_id}: {e}")
            all_success = False
            
    return all_success
