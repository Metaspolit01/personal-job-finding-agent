# Cloud VM Deployment Guide

This guide describes how to deploy the **Stateful AI Job Platform** to a Linux Cloud VM (e.g., AWS EC2, GCP Compute Engine, DigitalOcean Droplet) running **Ubuntu 22.04 LTS**.

---

## 1. System Requirements

* **Processor:** 2 vCPUs minimum
* **Memory:** 8 GB RAM minimum (necessary to run Ollama models like `qwen2.5:7b` locally)
* **Operating System:** Ubuntu 20.04 / 22.04 LTS

---

## 2. Server Installation Steps

### Step 1: Install Basic Dependencies
Connect to your VM via SSH and update package repositories:
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git curl
```

### Step 2: Clone Codebase & Setup Python Environment
Clone the project repository to your user's home folder, create a virtual environment, and install package dependencies:
```bash
git clone <your-repository-url>
cd job-finder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Install Playwright & Headless Browser Drivers
Since headless cloud servers do not run desktop environments, you must download the Chromium binary and install missing graphical/sound libraries for Linux:
```bash
# Download local Chromium browser driver
playwright install chromium

# Install system dependencies required for headless browser executions
sudo playwright install-deps
```

### Step 4: Install and Start Ollama Service
Download the Linux distribution script for Ollama, let it install as a system service, and download your target LLM model:
```bash
# Download and install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model (Qwen 2.5 7B is recommended for cloud CPU instances)
ollama pull qwen2.5:7b
```

### Step 5: Configure Environment Secrets
Create a `.env` file in the project root:
```bash
nano .env
```
Paste your Telegram API tokens and Ollama configuration:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b
```

---

## 3. Keep the Bot Running Forever (Systemd Service)

To make sure the script runs continuously in the background and automatically restarts if the server reboots, configure a Systemd Service:

### Step 1: Create a Service File
```bash
sudo nano /etc/systemd/system/jobfinder.service
```

### Step 2: Paste the Service Definition
*(Adjust paths and the `User` field if you are not using the default `ubuntu` user)*:
```ini
[Unit]
Description=Stateful Job Finder Agent
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/job-finder
ExecStart=/home/ubuntu/job-finder/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Step 3: Load and Enable the Service
```bash
# Reload systemd configs
sudo systemctl daemon-reload

# Enable service to run on boot
sudo systemctl enable jobfinder.service

# Start the bot
sudo systemctl start jobfinder.service
```

---

## 4. Monitoring & Troubleshooting

* **Check Service Status:**
  ```bash
  sudo systemctl status jobfinder.service
  ```
* **View Live Console Logs:**
  ```bash
  sudo journalctl -u jobfinder.service -f
  ```
* **Restart the Agent:**
  ```bash
  sudo systemctl restart jobfinder.service
  ```
* **Stop the Agent:**
  ```bash
  sudo systemctl stop jobfinder.service
  ```
