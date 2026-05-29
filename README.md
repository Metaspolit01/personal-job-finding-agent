# AI-Powered Job Search Agent

A production-style AI-powered job search agent that continuously monitors LinkedIn Jobs and Indeed India for fresher, internship, and junior-level openings.

## Architecture

```
Scheduler (schedule)
↓
LinkedIn + Indeed Scraper (playwright)
↓
Job Extraction Engine
↓
Filtering Engine (exclude consultancies/senior roles)
↓
Resume Matcher (scikit-learn TF-IDF)
↓
Local LLM Intelligence Layer (Ollama - qwen2.5:7b)
↓
Final Score Generator (60% TF-IDF, 40% LLM)
↓
Duplicate Checker (SQLite)
↓
Top 10 Selector
↓
Telegram Sender (python-telegram-bot)
```

## Setup Instructions

### 1. Install Dependencies
Ensure you have Python 3.10+ installed.
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install Playwright Browsers
```bash
playwright install chromium
```

### 3. Install Ollama and the Model
Download and install [Ollama](https://ollama.com/download), then pull the required model:
```bash
ollama run qwen2.5:7b
```
Keep Ollama running in the background.

### 4. Setup Telegram Bot
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, choose a name and username.
3. Save the HTTP API Token.
4. Get your chat ID (you can use `@userinfobot`).
5. Create a `.env` file in the root of the project:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
OLLAMA_API_URL=http://localhost:11434/api/generate
```

### 5. Running the Agent
Run the main script to start the scheduler.
```bash
python main.py
```

## Docker / AWS EC2 Deployment (Future)
- **Docker:** A `Dockerfile` can be used to wrap the Python environment. Ensure you use the official playwright python image: `mcr.microsoft.com/playwright/python:v1.42.0-jammy`.
- **EC2:** Install Docker on EC2, run Ollama natively or inside another container with GPU/CPU provisioning, then run this agent container linking to the Ollama API local address. For long term scraping, consider residential proxies.
