# Cloud VM Deployment Guide

This guide details how to deploy the **AI-Powered Job Search Agent** on a Linux Cloud Virtual Machine (e.g., AWS EC2, GCP Compute Engine, DigitalOcean Droplet) running **Ubuntu 22.04 LTS**.

---

## 🖥️ System Requirements

Running a local Large Language Model (LLM) requires decent system resources:
* **Processor:** 2 vCPUs minimum (Intel/AMD or AWS Graviton)
* **Memory:** 8 GB RAM minimum (necessary to load and run the `qwen2.5:7b` model locally via Ollama)
* **Disk Space:** 15 GB minimum (to accommodate OS, Docker/Python dependencies, and LLM weights)

---

## 🛠️ Step-by-Step Server Installation

### Step 1: Update System & Install Dependencies
SSH into your cloud instance and install Git, Curl, Python 3, and virtual environment utilities:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl
```

### Step 2: Clone the Project
Clone your repository to your user's home folder, create a virtual environment, and install dependencies:
```bash
git clone https://github.com/Metaspolit01/personal-job-finding-agent.git
cd personal-job-finding-agent

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Install Playwright & Headless Browser Drivers
Since cloud VMs do not have a graphical desktop interface, you must download the headless Chromium engine and install its required Linux system dependencies (libraries for fonts, media, and windowing):
```bash
# Download local Chromium browser driver
playwright install chromium

# Install system dependencies required by Playwright (requires sudo privileges)
sudo playwright install-deps
```

### Step 4: Install and Start Ollama Service
Ollama runs the local AI model used to score job postings. Install it via the official Linux installation script:
```bash
# Download and install Ollama as a system service
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model (Qwen 2.5 7B is highly recommended for job extraction & scoring)
ollama pull qwen2.5:7b
```
Verify that the service is running:
```bash
sudo systemctl status ollama
```

### Step 5: Configure Environment Settings
Create a `.env` file in your project root folder:
```bash
nano .env
```
Paste your production settings:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b
```
*(Save and exit nano: Press `Ctrl+O`, `Enter`, then `Ctrl+X`)*

---

## ⚙️ Running the Agent continuously (Systemd)

To ensure the job search agent runs continuously in the background, starts on system boot, and automatically restarts if it crashes, you should configure a **Systemd service**.

### Step 1: Create a Service File
```bash
sudo nano /etc/systemd/system/jobfinder.service
```

### Step 2: Paste the Service Definition
*(Note: If your SSH user is not `ubuntu` or your repository folder path is different, modify the `User` and path definitions below accordingly)*:
```ini
[Unit]
Description=Stateful Job Finder Agent
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/personal-job-finding-agent
ExecStart=/home/ubuntu/personal-job-finding-agent/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Step 3: Enable and Start the Service
```bash
# Reload systemd configuration to register the new service
sudo systemctl daemon-reload

# Enable service to run automatically on system boot
sudo systemctl enable jobfinder.service

# Start the agent
sudo systemctl start jobfinder.service
```

---

## 📊 Management & Troubleshooting

Use these standard commands to manage your running agent:

* **Check Service Status:**
  ```bash
  sudo systemctl status jobfinder.service
  ```
* **View Live Application Logs:**
  ```bash
  sudo journalctl -u jobfinder.service -f -n 100
  ```
* **Restart the Agent:**
  ```bash
  sudo systemctl restart jobfinder.service
  ```
* **Stop the Agent:**
  ```bash
  sudo systemctl stop jobfinder.service
  ```
