# TurboGastos - WhatsApp Ingestor

A minimal, containerized WhatsApp group ingestor for tracking expenses. It uses a Node.js service to listen to a specific WhatsApp group and a Python service to process and store the messages.

## Architecture

- **Node.js Ingestor (`ingestor` service)**: Connects to WhatsApp using `whatsapp-web.js`, listens for messages in the `GastosMyM` group, and publishes them to a Redis stream (`gastos:msgs`).
- **Gmail Reader (`gmail-reader` service)**: Connects to the Gmail API, searches for specific emails, and publishes them to the same Redis stream.
- **Python Worker (`worker` service)**: Consumes messages from the Redis stream, parses them using an LLM, and upserts them into an SQLite database. It exposes a FastAPI for reading the data.
- **Redis (`redis` service)**: Acts as the message broker between the ingestors and the worker.
- **Frontend (`frontend` service)**: A React-based web application to visualize the expense data.
- **MCP-SQLite (`mcp-sqlite` service)**: Exposes the SQLite database over a network connection, allowing AI agents to interact with the data.
- **Docker Compose**: Orchestrates the entire application stack.

## Prerequisites

- Docker
- Docker Compose

This setup is designed to be compatible with both x86-64 and ARM64 (e.g., Raspberry Pi) architectures.

## Getting Started

### 1. Environment Setup

The application uses `.env` files located in the `ingestor`, `worker` and `gmail_reader` directories.

First, create the `.env` files by copying the provided examples:

```bash
cp ingestor/.env.example ingestor/.env
cp worker/.env.example worker/.env
cp gmail_reader/.env.example gmail_reader/.env
```

Now, edit the `.env` files and set your `API_KEY` in the `ingestor` and `worker` `.env` files.

### 2. Gmail Reader Setup

The `gmail-reader` service requires Google API credentials to read your emails.

1.  **Enable the Gmail API**: Go to the [Google Cloud Console](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and enable the Gmail API for your project.
2.  **Create OAuth 2.0 Credentials**:
    *   Go to the [Credentials page](https://console.cloud.google.com/apis/credentials) in the Google Cloud Console.
    *   Click "Create Credentials" and choose "OAuth client ID".
    *   Select "Desktop app" as the application type.
    *   Click "Create".
    *   Click "Download JSON" to download your credentials file.
3.  **Place Credentials File**: Rename the downloaded file to `credentials.json` and place it in the `gmail_reader` directory.

### 3. First Run

Build and start all the services using Docker Compose:

```bash
docker compose up --build
```

On the first run, you will need to authorize the `gmail-reader` service to access your Gmail account.

Run the following command to start the authorization process:

```bash
docker compose run --service-ports gmail-reader
```

1.  Look for a URL in the logs of the `gmail-reader` service.
2.  Copy and paste the URL into your browser.
3.  Log in to your Google account and grant the requested permissions.
4.  You will be given a code. Copy the code.
5.  Paste the code back into the terminal where the `gmail-reader` service is running.

The service will then create a `token.json` file in the `gmail_reader` directory, which will be used for future runs. After the `token.json` file is created, you can stop the interactive session (with `Ctrl+C`) and run `docker compose up` to start all the services in the background.

The `ingestor` service will also display a **QR code** in the logs. Scan this code with your WhatsApp mobile app (Link a device) to log in. The session will be saved in the `ingestor/sessions` volume, so you only need to do this once.

### 4. Health Checks

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

## MCP-SQLite Service

The `mcp-sqlite` service runs a server that allows AI agents (like the Gemini CLI) to interact with the SQLite database. It exposes a port (8080) that can be used to send queries to the database.

This allows you to ask questions about your data in natural language, and the AI agent will be able to query the database and give you an answer.

## Volumes Explained

This project uses Docker volumes to persist data:

- **`ingestor/sessions`**: Stores the WhatsApp session data.
- **`gmail_reader/token.json`**: Stores the Gmail API access token.
- **`data`**: Stores the `gastos.db` SQLite database file.
- **`redis-data`**: Persists Redis data across restarts.

## Troubleshooting

- **Puppeteer/Chromium Issues**: The `ingestor/Dockerfile.node` is configured to install and use Chromium from the distribution's package manager.
- **`BUSYGROUP` Error in Worker Logs**: This is normal and means the Redis consumer group already exists.
- **ARM Architecture Notes**: The base images are multi-architecture and should work on Raspberry Pi (arm64).

## Security Note

Using `whatsapp-web.js` is an unofficial method of connecting to WhatsApp. Use this application at your own risk.
This application also requires access to your Gmail account. Grant access only if you trust the application and understand the risks.