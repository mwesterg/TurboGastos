You are an expert full-stack/devops engineer. Generate a minimal, working WhatsApp group ingestor with this architecture, now fully containerized with Docker, and using uv for Python deps.

GOAL
- Node "ingestor": listen ONLY to WhatsApp group "GastosMyM" using whatsapp-web.js, publish JSON payloads to Redis Stream "gastos:msgs", and expose GET /groups + /health (API key protected).
- Python "worker": consume Redis Stream with consumer groups, parse (stub), upsert into SQLite, expose FastAPI read APIs. Use uv for dependency management.
- Run everything via docker-compose on a Raspberry Pi or x86. Keep images small, Pi-friendly, and include Chromium for puppeteer.

STRICT REQUIREMENTS (carry over from earlier prompt, plus Docker/uv changes)
- WhatsApp Node app (unchanged behavior):
  - Deps: whatsapp-web.js, qrcode-terminal, redis, express, dotenv, body-parser.
  - LocalAuth with sessions/ persisted (mounted volume).
  - Filter: exact group name "GastosMyM".
  - Payload fields: wid, chat_id, chat_name, sender_id, sender_name, timestamp (unix seconds), type, body.
  - Publish via Redis XADD to stream "gastos:msgs".
  - HTTP endpoints: GET /groups, GET /health; both require x-api-key or ?api_key= (keep /health open if you prefer).
  - Puppeteer config compatible with Pi: headless true; args ['--no-sandbox','--disable-setuid-sandbox']; support PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium.
  - Files: package.json, index.js, .env.example.

- Python worker (unchanged behavior) BUT use uv:
  - Tools/Deps: uv (for dependency management), FastAPI, uvicorn, redis (redis-py), pydantic. SQLite via stdlib.
  - Provide pyproject.toml and uv.lock (lock may be minimal or omit if not feasible, but wire commands for uv).
  - Redis Streams consumer group: GROUP="py-expense-workers", CONSUMER="worker-1". Create group if not exists (mkstream). Process pending first, then new (">"- Python worker (unchanged behavior) BUT use uv:
  - Tools/Deps: uv (for dependency management), FastAPI, uvicorn, redis (redis-py), pydantic. SQLite via stdlib.
  - Provide pyproject.toml and uv.lock (lock may be minimal or omit if not feasible, but wire commands for uv).
  - Redis Streams consumer group: GROUP="py-expense-workers", CONSUMER="worker-1". Create group if not exists (mkstream). Process pending first, then new ("> "). Ack on success.
  - SQLite table (exact):
      CREATE TABLE IF NOT EXISTS messages(
        wid TEXT PRIMARY KEY,
        chat_id TEXT,
        chat_name TEXT,
        sender_id TEXT,
        sender_name TEXT,
        ts INTEGER,
        type TEXT,
        body TEXT,
        amount REAL,
        currency TEXT,
        category TEXT,
        meta_json TEXT
      );
  - Idempotent upsert by wid.
  - parse_expense(msg_body) stub returns None fields for now.
  - FastAPI endpoints:
    - GET /health -> {"status":"ok"}
    - GET /messages?limit=100 -> last N by ts desc
    - GET /messages/{wid} -> single row
    - GET /stats/summary -> {count,total,last_ts}
  - Env via .env: REDIS_URL=redis://redis:6379, DB_PATH=/data/gastos.db, API_KEY (require x-api-key or ?api_key= for all endpoints except /health).
  - Files: worker.py, pyproject.toml, uv.lock (if possible), .env.example.

- Dockerization (NEW, REQUIRED):
  - Provide docker-compose.yml with services:
    1) redis: use official redis:7-alpine, persistent volume "redis-data", healthcheck.
    2) node: built from Dockerfile.node; env includes TZ, API_KEY, PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium, REDIS_URL=redis://redis:6379; mount volume "sessions" to persist WhatsApp session; depends_on redis (with condition service_healthy); exposes 3000.
    3) worker: built from Dockerfile.python; uses uv for deps install; env REDIS_URL, DB_PATH=/data/gastos.db, API_KEY; mount volume "data" for SQLite; depends_on redis healthy; exposes 8000.
  - Volumes: sessions, data, redis-data.
  - Healthchecks for node (curl /health), worker (curl /health), redis (redis-cli ping).
  - Ensure both node & python run as non-root where practical (create user in images).

- Dockerfile.node (Pi-friendly):
  - Base: node:20-bookworm-slim (works on arm64/x86).
  - Install chromium (apt-get install -y chromium) and minimal deps (fonts, ca-certificates).
  - Set PUPPETEER_SKIP_DOWNLOAD=1 to avoid bundling Chromium.
  - Set PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium.
  - Create app user, chown /app and sessions dir, run as that user.
  - Copy package.json/package-lock (or only package.json) then npm ci / npm install, copy source, set CMD ["node","index.js"].

- Dockerfile.python (uv usage):
  - Base: python:3.11-slim.
  - Install curl and required build tools only if needed; keep slim.
  - Install uv via official script:
      RUN curl -LsSf https://astral.sh/uv/install.sh | sh
    Ensure uv is on PATH (e.g., /root/.cargo/bin or /root/.local/bin); export PATH accordingly.
  - Create non-root user (e.g., appuser) and workdir /app, data dir /data (owned by appuser).
  - Copy pyproject.toml (and uv.lock if present), run:
      RUN uv pip install --system -r <(uv pip compile pyproject.toml)   // or `uv pip install --system -r requirements.txt` if you choose that route
    Alternatively, use `uv sync --frozen` if you generate a lock; final result: deps installed system-wide or within /app/.venv—pick one and be consistent.
  - Copy worker.py, set CMD to run uvicorn (e.g., `uv run uvicorn worker:app --host 0.0.0.0 --port 8000`) OR activate venv explicitly if you used `uv venv`. Keep it simple: system install + `python -m uvicorn ...` is acceptable if uv installed deps with `--system`.

- Security & Ops
  - All HTTP endpoints require x-api-key (or ?api_key=) except /health.
  - .dockerignore to keep node_modules, sessions, data, and build caches out of context where appropriate.
  - Minimal logs; no secrets in logs.

- Deliverables (FILENAMES + FULL CONTENTS)
  1) package.json
  2) index.js
  3) .env.example (Node) with API_KEY, PORT, REDIS_URL, PUPPETEER_EXECUTABLE_PATH
  4) worker.py
  5) pyproject.toml (Python; include fastapi, uvicorn[standard], redis>=5, pydantic>=2)
  6) uv.lock (generate or include a minimal placeholder with note; if omitted, ensure install works with uv)
  7) .env.example (Python) with REDIS_URL, DB_PATH, API_KEY
  8) Dockerfile.node
  9) Dockerfile.python
 10) docker-compose.yml
 11) .dockerignore
 12) README.md with run steps

- README.md must include:
  - Prereqs: Docker & Docker Compose installed on the Pi.
  - Env setup: copy .env.example to .env for node & python services (or pass via compose).
  - First run:
      docker compose up --build
      (scan QR shown in node logs once)
  - Health checks:
      curl http://localhost:3000/health
      curl http://localhost:8000/health
  - Example API calls (with API key):
      curl -H "x-api-key: KEY" http://localhost:3000/groups
      curl -H "x-api-key: KEY" "http://localhost:8000/messages?limit=50"
  - Volumes explained: sessions (WhatsApp session), data (SQLite), redis-data.
  - Troubleshooting:
      - If puppeteer can’t find Chromium: ensure PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium.
      - If BUSYGROUP error on group creation: it’s okay, group already exists.
      - For armv7/arm64 notes on Chromium package name.
  - Security note about unofficial WhatsApp approach.

STYLE
- Concise, production-like code; Pi-friendly comments where needed.
- Keep images small and commands deterministic.
- No LLM calls yet; the worker’s parse_expense remains a stub.
- Output each file with a clear filename header and its full contents. Do NOT include any other files. No extra chatter—just the files.

Now produce the files.