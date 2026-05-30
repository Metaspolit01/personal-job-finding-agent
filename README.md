# AI-Powered Job Search Agent

A production-grade, stateful, AI-powered job search agent that automatically monitors LinkedIn Jobs and Indeed India for junior-level, fresher, or internship positions. It filters out staffing/consultancy noise, scores matches against your resume using a hybrid TF-IDF + Local LLM scoring engine, and delivers the top recommendations directly to your Telegram channel.

---

## 🏗️ Architecture & Flow

```
   [ Scheduler (Schedule Module) ]
                  │
                  ▼
  [ LinkedIn + Indeed Scrapers (Playwright) ]
                  │
                  ▼
    [ Job Extraction Engine ]
                  │
                  ▼
   [ Static / Preference Filters ] ─── (Excludes recruiters, senior roles, etc.)
                  │
                  ▼
      [ Resume Matcher (TF-IDF) ] ─── (Matches tech stack, projects, skills)
                  │
                  ▼
   [ Ollama Qwen2.5 Local Matcher ] ── (Performs semantic analysis & role evaluation)
                  │
                  ▼
  [ Scoring & Deduplication Engine ] ─ (Weighted Score & SQLite Duplicate Check)
                  │
                  ▼
     [ Telegram Sender / Bot ] ────── (Sends summary + handles interactive commands)
```

---

## ⚡ Features

- **Multi-Source Scraping:** Robust headless browser automation using Playwright to scrape LinkedIn and Indeed.
- **Smart Filtering:** Built-in blacklists for company types (agencies, consultancies) and seniority (senior, principal, director).
- **Hybrid Scoring:** Evaluates relevance using TF-IDF (60% weight) and local LLM semantic evaluation (40% weight).
- **Self-Healing & Monitoring:** Operational memory, self-monitoring agent with recovery actions, and Prometheus metrics exporter.
- **CI/CD Pipeline:** Fully configured GitHub Actions workflow that automatically lints your code and builds/pushes a ready-to-use Docker image to the **GitHub Container Registry (GHCR)**.

---

## 🛠️ Local Setup & Usage

### 1. Prerequisites
- **Python 3.10+**
- **Docker** (Optional, for running inside containers)
- **Ollama** (For local AI capability)

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/Metaspolit01/personal-job-finding-agent.git
cd job-finder
python -m venv venv

# Activate Virtual Environment
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Install Playwright Web Drivers
Playwright requires browser binaries to execute scraping:
```bash
playwright install chromium
```

### 4. Install Ollama and Download the Model
Download [Ollama](https://ollama.com/) and run the default model locally to spin up the API:
```bash
ollama run qwen2.5:7b
```
*Keep Ollama running in the background while the agent is running.*

### 5. Configure Settings
Create a `.env` file in the root directory:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Choose LLM Provider: 'ollama' or 'openai' (for any OpenAI-compatible API)
LLM_PROVIDER=ollama

# Option A: Local Ollama Settings (default)
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b

# Option B: External LLM API Settings (e.g. OpenAI, DeepSeek, Groq, OpenRouter)
# (Required only if LLM_PROVIDER=openai)
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### 6. Run the Application
Start the main scheduler loop:
```bash
python main.py
```

---

## 🧹 Code Quality & Linting

We use **Ruff** for fast Python linting and code quality checks. 

To run the checks locally:
```bash
# Install Ruff (if not already installed)
pip install ruff

# Run check
ruff check .
```

Configuration rules (e.g. line length limits and exclusions) are defined in [ruff.toml](file:///d:/job-finder/ruff.toml).

---

## 🐳 Docker & Production Deployment

Because of our CI/CD pipeline, every commit pushed to `main` automatically builds a Docker container and publishes it to GHCR.

### Option A: Minimal Run (Single Container via Docker)
Use this option if you want to run only the job-finder agent without the monitoring dashboard to save RAM and CPU resources. You do not need to clone the repository or set up Python.

#### Step 1: Create your Environment Configuration
On your server, create a file named `.env` in your working directory containing your configuration settings:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Choose LLM Provider: 'ollama' or 'openai' (for any OpenAI-compatible API)
LLM_PROVIDER=ollama

# Option A: Local Ollama Settings (default)
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b

# Option B: External LLM API Settings (e.g. OpenAI, DeepSeek, Groq, OpenRouter)
# (Required only if LLM_PROVIDER=openai)
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

#### Step 2: Log in to GitHub Container Registry (GHCR)
*(Required if your package registry is set to private. You will need a GitHub Personal Access Token (PAT) with `read:packages` scope)*:
```bash
echo "THEIR_PERSONAL_ACCESS_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

#### Step 3: Run the Container
Execute the following command to download (pull) and run the container in the background:
```bash
docker run -d \
  --name job-finder \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  ghcr.io/metaspolit01/personal-job-finding-agent:latest
```

#### Step 4: Verify & Monitor
You can view the logs of your running agent to ensure it is scraping and running checks correctly:
```bash
docker logs -f job-finder
```

### Option B: Full Stack Run (Multi-Container via Docker Compose)
Use this option if you want to run the job-finder agent along with Prometheus and Grafana for monitoring dashboards. Since it pulls the pre-built image from GHCR, it starts immediately without compiling code locally:
```bash
docker-compose up -d
```

### Option C: Traditional Cloud VM Deployment (Systemd)
If you prefer running without Docker directly on a Linux VM (Ubuntu 22.04), see the step-by-step [VM Deployment Guide](file:///d:/job-finder/README-cloud.md) which sets up a Systemd service to run the app continuously in the background.

---

## 📁 Repository Tour
- `scraper/` - Contains the Playwright engines for job boards.
- `filtering/` - Code filtering out blacklist roles and recruiters.
- `matching/` - TF-IDF calculations and Ollama LLM prompting mechanisms.
- `notifications/` - Telegram bot integration.
- `monitoring/` - Prometheus telemetry and self-healing engine.
- `database/` - SQLite schema and database manager.
- `.github/workflows/` - GitHub Actions CI/CD pipeline definitions.
