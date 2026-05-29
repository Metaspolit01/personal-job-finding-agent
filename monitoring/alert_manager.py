import logging
import requests
from config.settings import BOT_TOKEN, CHAT_ID
from monitoring.operational_memory import log_alert

logger = logging.getLogger(__name__)

def send_operational_alert(alert_name: str, message: str) -> bool:
    """Send an operational alert message to the user via Telegram bot."""
    formatted_msg = (
        f"🚨 **[AIOps Alert] {alert_name}**\n\n"
        f"{message}"
    )
    
    sent_to_telegram = False
    
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": formatted_msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            res.raise_for_status()
            sent_to_telegram = True
            logger.info(f"Sent AIOps Telegram alert: {alert_name}")
        except Exception as e:
            logger.error(f"Failed to transmit AIOps alert to Telegram: {e}")
    else:
        logger.warning("Telegram settings not fully configured. Skipping AIOps alert dispatch.")
        
    # Log alert in SQLite
    log_alert(alert_name, formatted_msg, sent_to_telegram)
    return sent_to_telegram
