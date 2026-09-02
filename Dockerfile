FROM python:3.10-slim

WORKDIR /app

# Ensure we have system dependencies for audio processing if needed (like soundfile)
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Strictly installing dependencies without cache to save RAM during build
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# Strict 1 worker command to prevent RAM duplication
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000", "--workers", "1"]
