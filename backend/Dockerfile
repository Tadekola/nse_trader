# Stage 1: Build environment with Poetry
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Pin Poetry version for consistency
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VENV_PATH="/opt/poetry-venvs"
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install Poetry
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get remove -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create a non-root user
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Configure Poetry to create virtual envs in the project directory
RUN poetry config virtualenvs.in-project true

# Copy dependency definition files
COPY pyproject.toml poetry.lock* ./

# Install dependencies - excluding dev dependencies
# Use --no-root to avoid installing the project itself, we copy it later
RUN poetry install --no-dev --no-interaction --no-ansi --no-root

# Stage 2: Production image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Create the same non-root user as in the builder stage
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Copy the virtual environment with dependencies from the builder stage
COPY --from=builder /app/.venv .venv

# Activate the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY ./app ./app

# Ensure the non-root user owns the application files
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Run the application using Uvicorn
# Use --host 0.0.0.0 to be accessible from outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
