FROM python:3.13-slim

# Install git and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY relayx/ ./relayx/
COPY main.py check.py ./

RUN uv sync --no-dev --frozen

EXPOSE 8080

# Run the application
ENTRYPOINT ["uv", "run", "main.py"]

CMD ["--bind", "127.0.0.1"]