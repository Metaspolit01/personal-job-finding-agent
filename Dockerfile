FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

# Copy and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy remaining code files
COPY . .

# Expose Prometheus exporter port
EXPOSE 8000

CMD ["python", "main.py"]
