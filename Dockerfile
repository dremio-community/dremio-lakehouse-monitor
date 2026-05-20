# ── Dremio Lakehouse Monitor — Production Docker Image ────────────────────────
# Usage:
#   docker build -t dremio-lakehouse-monitor .
#   docker run -p 8770:8770 -v monitor-data:/data dremio-lakehouse-monitor
#   Open http://localhost:8770

FROM python:3.11-slim
WORKDIR /app

# The application only uses Python standard libraries! No pip install needed.

# Copy application source
COPY . /app/

# Data directory for SQLite persistence
RUN mkdir -p /data
ENV DB_PATH=/data/monitor.db

EXPOSE 8770

# Run the monitor server
CMD ["python3", "monitor.py", "--host", "0.0.0.0", "--port", "8770"]
