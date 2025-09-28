import os
import sqlite3
import json
import asyncio
from typing import Optional, List, Dict, Any

import redis.asyncio as aredis
import redis
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import google.generativeai as genai

# --- Environment & Config ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_PATH = os.getenv("DB_PATH", "/data/gastos.db")
API_KEY = os.getenv("API_KEY", "your-secret-key")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

REDIS_STREAM_NAME = "gastos:msgs"
REDIS_GROUP_NAME = "py-expense-workers"
REDIS_CONSUMER_NAME = "worker-1"

# --- GenAI Configuration ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- API Key Security ---
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- Database Setup ---
def get_db_connection():
    # Ensure the directory for the database exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
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
        """)
        conn.commit()

# --- Pydantic Models ---
class Message(BaseModel):
    wid: str
    chat_id: str
    chat_name: str
    sender_id: str
    sender_name: str
    ts: int
    type: str
    body: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    meta_json: Optional[str] = None

class StatsSummary(BaseModel):
    message_count: int
    total_amount: float
    last_message_ts: Optional[int] = None

# --- Expense Parsing (LLM) ---
async def parse_expense_with_llm(msg_body: str) -> Dict[str, Any]:
    """Parses expense details from a message body using Google Gemini."""
    if not genai.get_model("models/gemini-pro"):
        print("LLM model not available, returning stub.")
        return {"amount": None, "currency": None, "category": None, "meta_json": json.dumps({"error": "LLM not configured"})}

    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""
    Analyze the following text and extract expense information.
    Return a single, minified JSON object with these exact keys: "amount", "currency", "category", "meta_json".
    - "amount": A float representing the expense amount.
    - "currency": The currency code (e.g., "USD", "EUR", "CLP"). Default to "CLP" if not specified.
    - "category": A single, relevant category from this list: Food, Transport, Shopping, Utilities, Health, Entertainment, Other.
    - "meta_json": A JSON string containing any other relevant data you can extract.

    If the text is not an expense, return a JSON object with null values for all keys.

    Text to analyze: "{msg_body}"
    """
    try:
        response = await model.generate_content_async(prompt)
        
        # Clean the response to get only the JSON part
        text_response = response.text.strip()
        json_str = text_response[text_response.find('{'):text_response.rfind('}')+1]
        
        parsed = json.loads(json_str)
        
        # Ensure all keys are present
        return {
            "amount": parsed.get("amount"),
            "currency": parsed.get("currency"),
            "category": parsed.get("category"),
            "meta_json": json.dumps(parsed.get("meta_json", {}))
        }
    except Exception as e:
        print(f"Error parsing with LLM: {e}")
        return {"amount": None, "currency": None, "category": None, "meta_json": json.dumps({"error": str(e)})}


# --- FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.on_event("startup")
async def startup_event():
    setup_database()
    # Start the Redis consumer in the background
    asyncio.create_task(redis_consumer())

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/messages", response_model=List[Message], dependencies=[Depends(get_api_key)])
def get_messages(limit: int = 100):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages ORDER BY ts DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

@app.get("/messages/{wid}", response_model=Message, dependencies=[Depends(get_api_key)])
def get_message(wid: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE wid = ?", (wid,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Message not found")
        return dict(row)

@app.get("/stats/summary", response_model=StatsSummary, dependencies=[Depends(get_api_key)])
def get_stats_summary():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(amount), MAX(ts) FROM messages")
        count, total, last_ts = cursor.fetchone()
        return {
            "message_count": count or 0,
            "total_amount": total or 0.0,
            "last_message_ts": last_ts
        }

# --- Redis Stream Consumer ---
async def redis_consumer():
    print("Starting Redis stream consumer...")
    r = aredis.from_url(REDIS_URL, decode_responses=True)

    try:
        await r.xgroup_create(REDIS_STREAM_NAME, REDIS_GROUP_NAME, id='0', mkstream=True)
        print(f"Consumer group '{REDIS_GROUP_NAME}' created or already exists.")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            print(f"Error creating consumer group: {e}")
            return
        print(f"Consumer group '{REDIS_GROUP_NAME}' already exists.")

    async def process_and_ack(messages):
        if not messages:
            return
        print(f"Processing {len(messages)} messages...")
        for msg_id, msg_data in messages:
            print(f"-> Processing message {msg_id}: {msg_data.get('body', '')}")
            await process_message(msg_data, r)
            await r.xack(REDIS_STREAM_NAME, REDIS_GROUP_NAME, msg_id)

    while True:
        try:
            # First, check for any pending messages for this consumer (ID '0')
            # These are messages that were delivered to us but we never ACKed
            response = await r.xreadgroup(
                groupname=REDIS_GROUP_NAME,
                consumername=REDIS_CONSUMER_NAME,
                streams={REDIS_STREAM_NAME: '0'},
                count=10,
                block=1  # Don't block, just check
            )

            # If we had pending messages, process them
            if response:
                for stream, messages in response:
                    await process_and_ack(messages)

            # Now, wait for new messages ('>')
            response = await r.xreadgroup(
                groupname=REDIS_GROUP_NAME,
                consumername=REDIS_CONSUMER_NAME,
                streams={REDIS_STREAM_NAME: '>'},
                count=10,
                block=5000
            )

            if response:
                for stream, messages in response:
                    await process_and_ack(messages)

        except Exception as e:
            print(f"Error in Redis consumer loop: {e}")
            await asyncio.sleep(5)

async def process_message(msg_data: Dict[str, Any], r: redis.Redis):
    """Parses and upserts a message into the SQLite database using LLM."""
    try:
        parsed_expense = await parse_expense_with_llm(msg_data.get('body', ''))

        message = Message(
            wid=msg_data['wid'],
            chat_id=msg_data['chat_id'],
            chat_name=msg_data['chat_name'],
            sender_id=msg_data['sender_id'],
            sender_name=msg_data['sender_name'],
            ts=int(msg_data['timestamp']),
            type=msg_data['type'],
            body=msg_data['body'],
            amount=parsed_expense.get('amount'),
            currency=parsed_expense.get('currency'),
            category=parsed_expense.get('category'),
            meta_json=parsed_expense.get('meta_json')
        )

        # Run DB operations in a separate thread to avoid blocking asyncio loop
        await asyncio.to_thread(upsert_message_db, message)

        # If parsing was successful, send confirmation
        if parsed_expense.get('amount') is not None:
            confirmation_payload = json.dumps({
                "chat_id": message.chat_id,
                "original_wid": message.wid
            })
            await r.publish("gastos:confirmations", confirmation_payload)

    except Exception as e:
        print(f"Error processing message for DB: {e}")

def upsert_message_db(message: Message):
    """Function to perform the database upsert operation."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO messages (wid, chat_id, chat_name, sender_id, sender_name, ts, type, body, amount, currency, category, meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(wid) DO UPDATE SET
            ts=excluded.ts,
            body=excluded.body,
            amount=excluded.amount,
            currency=excluded.currency,
            category=excluded.category,
            meta_json=excluded.meta_json;
        """, (
            message.wid, message.chat_id, message.chat_name, message.sender_id, message.sender_name,
            message.ts, message.type, message.body, message.amount, message.currency,
            message.category, message.meta_json
        ))
        conn.commit()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)