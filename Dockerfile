FROM python:3.11-slim

WORKDIR /app

# Copy and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Chromium and automatically install all required OS dependencies
RUN playwright install --with-deps chromium

# Copy remaining code files
COPY . .

# Expose Prometheus exporter port
EXPOSE 8000

CMD ["python", "main.py"]
