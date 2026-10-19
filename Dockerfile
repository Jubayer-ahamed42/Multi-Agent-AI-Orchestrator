# Production Dockerfile for 24/7 Cloud Deployment (Google Cloud Run / Render / Hugging Face)
FROM python:3.12-slim

# Prevent Python from writing pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose standard Streamlit port
EXPOSE 8501

# Healthcheck to ensure agent stays alive 24/7
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Launch Dual Services (Streamlit Web Dashboard + Telegram Bot Worker)
CMD ["python", "run_services.py"]

