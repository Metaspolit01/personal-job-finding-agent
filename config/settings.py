import os
import logging
from dotenv import load_dotenv

load_dotenv()

# General Settings
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Ollama Settings
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Database Settings
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "jobs.db")

# Scraping Settings
MAX_JOBS_PER_SITE = 50

LOG_CONFIG = {
    "level": logging.INFO,
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "handlers": [
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "agent.log"), mode="a"),
        logging.StreamHandler()
    ]
}
