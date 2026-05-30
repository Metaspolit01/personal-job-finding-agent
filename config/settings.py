import os
import logging
from dotenv import load_dotenv

load_dotenv()

# General Settings
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# LLM Settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip()
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_JSON_MODE = os.getenv("OPENAI_JSON_MODE", "false").strip().lower() == "true"

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
