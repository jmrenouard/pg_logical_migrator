FROM python:3.11-slim

# Install system dependencies (pg_dump, psql)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and configuration
COPY src/ ./src/
COPY pg_migrator.py .
COPY config_migrator.sample.ini ./config_migrator.ini

# Make the CLI executable
RUN chmod +x pg_migrator.py

# Create RESULTS directory to avoid permission issues if pipeline runs inside
RUN mkdir -p /app/RESULTS

# By default, running the container executes the main CLI tool.
# You can mount a custom config file to /app/config_migrator.ini when running.
ENTRYPOINT ["python", "pg_migrator.py"]
CMD ["--help"]
