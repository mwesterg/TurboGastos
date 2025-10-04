# TurboGastos - WhatsApp Ingestor

A minimal, containerized WhatsApp group ingestor for tracking expenses. It uses a Node.js service to listen to a specific WhatsApp group and a Python service to process and store the messages.

## Architecture

- **Node.js Ingestor (`ingestor` service)**: Connects to WhatsApp using `whatsapp-web.js`, listens for messages in the `GastosMyM` group, and publishes them to a Redis stream (`gastos:msgs`).
- **Python Worker (`worker` service)**: Consumes messages from the Redis stream, parses them (currently a stub), and upserts them into an SQLite database. It exposes a FastAPI for reading the data.
- **Redis (`redis` service)**: Acts as the message broker between the ingestor and the worker.
- **Frontend (`frontend` service)**: A React-based web application to visualize the expense data.
- **Docker Compose**: Orchestrates the entire application stack.

## Prerequisites

- Docker
- Docker Compose

This setup is designed to be compatible with both x86-64 and ARM64 (e.g., Raspberry Pi) architectures.

## Getting Started

### 1. Environment Setup

The application uses `.env` files located in the `ingestor` and `worker` directories.

First, create the `.env` files by copying the provided examples:

```bash
cp ingestor/.env.example ingestor/.env
cp worker/.env.example worker/.env
```

Now, edit the `.env` files and set your `API_KEY` in both files.

### 2. First Run

Build and start all the services using Docker Compose:

```bash
docker compose up --build
```

On the first run, the `ingestor` service will display a **QR code** in the logs. Scan this code with your WhatsApp mobile app (Link a device) to log in. The session will be saved in the `ingestor/sessions` volume, so you only need to do this once.

### 3. Health Checks

Once the services are running, you can check their health:

- **Web Interface**: Open your browser and navigate to `http://localhost:5173`

- **Backend Services**:
  ```bash
  # Check Node.js Ingestor
  curl http://localhost:3000/health

  # Check Python Worker
  curl http://localhost:8000/health
  ```

## Web Interface

A web-based dashboard is available at [http://localhost:5173](http://localhost:5173) to visualize the collected data. It provides statistics, charts, and a table of recent messages.

**Note**: The API key for the frontend is currently hardcoded in `frontend/src/App.js`. For any real-world use, you should replace it with a more secure method, such as environment variables.

## API Usage

All API endpoints (except `/health`) require an API key for authorization. Provide it in the `x-api-key` header.

**Example API Calls:**

- **Get list of WhatsApp groups:**
  ```bash
  curl -H "x-api-key: your-super-secret-and-long-api-key" http://localhost:3000/groups
  ```

- **Get the last 50 messages from the database:**
  ```bash
  curl -H "x-api-key: your-super-secret-and-long-api-key" "http://localhost:8000/messages?limit=50"
  ```

- **Get a single message by its ID:**
  ```bash
  curl -H "x-api-key: your-super-secret-and-long-api-key" http://localhost:8000/messages/some-message-wid
  ```

## Volumes Explained

This project uses Docker volumes to persist data:

- **`ingestor/sessions`**: Stores the WhatsApp session data, so you don't have to scan the QR code on every restart.
- **`data`**: Stores the `gastos.db` SQLite database file.
- **`redis-data`**: Persists Redis data across restarts.

## Troubleshooting

- **Puppeteer/Chromium Issues**: The `ingestor/Dockerfile.node` is configured to install and use Chromium from the distribution's package manager, which is the recommended approach for ARM-based devices like the Raspberry Pi. The `PUPPETEER_EXECUTABLE_PATH` is set to `/usr/bin/chromium`.
- **`BUSYGROUP` Error in Worker Logs**: If you see a `BUSYGROUP Consumer group ... already exists` error from the Python worker on startup, this is normal. It just means the Redis consumer group was already created on a previous run.
- **ARM Architecture Notes**: The base images (`node:20-bookworm-slim`, `python:3.11-slim`) are multi-architecture and should work correctly on Raspberry Pi (arm64). The Chromium package name (`chromium`) is also standard for Debian Bookworm.

## Security Note

Using `whatsapp-web.js` is an unofficial method of connecting to WhatsApp. Use this application at your own risk. It is not endorsed by WhatsApp and may violate their terms of service.