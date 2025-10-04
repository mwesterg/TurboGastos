You are an expert full-stack/devops engineer. Generate a minimal, working WhatsApp group ingestor with this architecture, now fully containerized with Docker, and using uv for Python deps.

GOAL
- Node "ingestor": listen ONLY to WhatsApp group "GastosMyM" using whatsapp-web.js, publish JSON payloads to Redis Stream "gastos:msgs", and expose GET /groups + /health (API key protected).
- Python "worker": consume Redis Stream with consumer groups, parse expenses using an LLM to categorize them as "personal" or "household", upsert into SQLite, and expose FastAPI read APIs. Use uv for dependency management.
- `mcp-sqlite` "database agent": Expose the SQLite database over a network connection, allowing AI agents to interact with the data.
- Run everything via docker-compose on a Raspberry Pi or x86. Keep images small, Pi-friendly, and include Chromium for puppeteer.

STRICT REQUIREMENTS (carry over from earlier prompt, plus Docker/uv changes)
- WhatsApp Node app (`ingestor` service):
  - Resides in the `ingestor/` directory.
  - Deps: whatsapp-web.js, qrcode-terminal, redis, express, dotenv, body-parser.
  - LocalAuth with sessions/ persisted (mounted volume).
  - Filter: exact group name "GastosMyM".
  - Payload fields: wid, chat_id, chat_name, sender_id, sender_name, timestamp (unix seconds), type, body.
  - Publish via Redis XADD to stream "gastos:msgs".
  - HTTP endpoints: GET /groups, GET /health; both require x-api-key or ?api_key=.
  - Puppeteer config compatible with Pi: headless true; args ['--no-sandbox','--disable-setuid-sandbox']; support PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium.
  - Files: `ingestor/package.json`, `ingestor/index.js`, `ingestor/.env.example`.

- Python worker (`worker` service):
  - Resides in the `worker/` directory.
  - Tools/Deps: uv, FastAPI, uvicorn, redis-py, pydantic, google-generativeai. SQLite via stdlib.
  - Uses an LLM to classify expenses as "personal" or "household". If the category is "unknown", the message is stored in a `pending_clarification` table.
  - Provides endpoints for retrieving and clarifying messages pending classification.
  - Redis Streams consumer group: GROUP="py-expense-workers", CONSUMER="worker-1".
  - SQLite tables: `messages` and `pending_clarification`.
  - FastAPI endpoints:
    - GET /health -> {"status":"ok"}
    - GET /messages?limit=100 -> last N by ts desc
    - GET /messages/{wid} -> single row
    - GET /stats/summary -> {count,total,last_ts}
    - GET /messages/pending_clarification -> list of messages needing clarification
    - POST /messages/clarify/{wid} -> clarify a message's category
  - Env via .env: REDIS_URL, DB_PATH, API_KEY, GOOGLE_API_KEY, GEMINI_MODEL.
  - Files: `worker/worker.py`, `worker/pyproject.toml`, `worker/.env.example`.

- `mcp-sqlite` service (`mcp-sqlite` service):
    - Resides in the `mcp_service/` directory.
    - Exposes the SQLite database over port 8080 for AI agent interaction.
    - Files: `mcp_service/run.py`, `mcp_service/pyproject.toml`, `mcp_service/Dockerfile`.

- Dockerization:
  - Provide docker-compose.yml with services:
    1) redis: official redis:7-alpine, persistent volume "redis-data", healthcheck.
    2) ingestor: built from `ingestor/Dockerfile.node`.
    3) worker: built from `worker/Dockerfile.python`.
    4) mcp-sqlite: built from `mcp_service/Dockerfile`.
    5) frontend: built from `frontend/Dockerfile`.
  - Volumes: sessions, data, redis-data.

- Dockerfile.node (Pi-friendly):
  - Base: node:20-bookworm-slim.
  - Installs chromium.
  - Sets PUPPETEER_SKIP_DOWNLOAD=1 and PUPPETEER_EXECUTABLE_PATH.

- Dockerfile.python (uv usage):
  - Base: python:3.11-slim.
  - Installs uv.
  - Installs dependencies from `pyproject.toml` using uv.

- Security & Ops
  - All HTTP endpoints require x-api-key (or ?api_key=) except /health.
  - .dockerignore to keep artifacts out of build contexts.

- Deliverables (FILENAMES + FULL CONTENTS)
  1) `ingestor/package.json`
  2) `ingestor/index.js`
  3) `ingestor/.env.example`
  4) `worker/worker.py`
  5) `worker/pyproject.toml`
  6) `worker/.env.example`
  7) `mcp_service/run.py`
  8) `mcp_service/pyproject.toml`
  9) `mcp_service/Dockerfile`
  10) `docker-compose.yml`
  11) `.dockerignore`
  12) `README.md` with run steps

- README.md must include:
  - Env setup for all services.
  - `docker compose up --build` command.
  - Health check examples.
  - API call examples.
  - Explanation of the new `mcp-sqlite` service.

STYLE
- Concise, production-like code.
- Keep images small and commands deterministic.