FROM python:3.13-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY relayx/ ./relayx/
COPY main.py check.py ./

RUN uv sync --no-dev --frozen

EXPOSE 8080

# Run the application
CMD ["uv", "run", "main.py"] 