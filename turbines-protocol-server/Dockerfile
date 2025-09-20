# Runtime-only image: small, fast to pull.
FROM python:3.12-slim AS runtime

# Security & speed niceties
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create non-root user
RUN useradd -m runner
WORKDIR /srv

# Install only runtime deps (no compilers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy just the app
COPY app.py .

# Expose the HTTP port
EXPOSE 5555

# Drop privileges
USER runner

# Start the server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5555"]
