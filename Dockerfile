FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY web3_radar ./web3_radar
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 radar && mkdir -p /app/data && chown -R radar:radar /app
USER radar

CMD ["web3-radar", "run"]
