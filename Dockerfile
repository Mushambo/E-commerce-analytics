# Analytics container: Python 3.11 + Java 17 (for Spark) + all project libraries.
# Built and started by docker-compose.yml as the "app" service.
FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps \
 && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The project folder is mounted at /app by docker-compose (so outputs appear on your PC);
# copying it as well lets the image run on its own if needed.
COPY . .
CMD ["sleep", "infinity"]
