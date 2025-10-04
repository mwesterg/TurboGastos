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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-pro")

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
async def parse_expense_with_llm(msg_body: str, model_name: str) -> Dict[str, Any]:
    """Parses expense details and generates a conversational reply from a message body."""
    print("DEBUG: parse_expense_with_llm started.")
    if not GOOGLE_API_KEY:
        print("DEBUG: LLM parsing skipped: GOOGLE_API_KEY is not set.")
        return {"reply_message": "Error: El servicio de IA no está configurado.", "expense_data": None}

    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        print(f"DEBUG: Error initializing LLM model '{model_name}': {e}")
        return {"reply_message": "Error: No se pudo iniciar el modelo de IA.", "expense_data": None}

    prompt = f"""
    You are a helpful assistant in a WhatsApp group chat for tracking expenses. Your personality is friendly and concise.
    Analyze the following text. Your response MUST be a single, minified JSON object with two keys: "reply_message" and "expense_data".

    1.  "reply_message": A short, conversational reply in Spanish. If the message is an expense, confirm it. If it's a greeting or question, answer it. If it's nonsense, be politely confused.
    2.  "expense_data": An object with expense details. If the message is NOT an expense, this MUST be null.
        - If it IS an expense, the object must contain these keys: "amount" (float), "currency" (string, default "CLP"), "category" (string from list: Food, Transport, Shopping, Utilities, Health, Entertainment, Other), and "meta_json" (a JSON string for extra data).

    Examples:
    - Input: "hola"
      Output: {{\"reply_message\":\"¡Hola! ¿Cómo puedo ayudarte?\",\"expense_data\":null}}
    - Input: "supermercado 12.50 usd"
      Output: {{\"reply_message\":\"Ok, anotado: $12.50 USD en Shopping.\",\"expense_data\":{{\"amount\":12.50,\"currency\":\"USD\",\"category\":\"Shopping\",\"meta_json\":\"{{\\\"source\\\":\\\"supermercado\\\"}}\"}}}}
    - Input: "cuanto he gastado?"
      Output: {{\"reply_message\":\"Aún no puedo responder esa pregunta, ¡pero pronto lo haré!\",\"expense_data\":null}}

    Text to analyze: "{msg_body}"
    """
    try:
        print("DEBUG: Calling Google AI API...")
        response = await model.generate_content_async(prompt)
        print("DEBUG: Google AI API call returned.")
        text_response = response.text.strip()
        print(f"DEBUG: Raw LLM response: {text_response}")
        json_str = text_response[text_response.find('{'):text_response.rfind('}')+1]
        parsed = json.loads(json_str)
        return parsed # Return the full object { "reply_message": ..., "expense_data": ... }
    except Exception as e:
        print(f"DEBUG: Error parsing with LLM: {e}")
        return {"reply_message": "Lo siento, no entendí eso. ¿Puedes intentarlo de nuevo?", "expense_data": None}

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
    print(f"Using Gemini model: {GEMINI_MODEL}")
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

    while True:
        try:
            # Wait for new messages. '>' means messages that have never been delivered to any consumer.
            response = await r.xreadgroup(
                groupname=REDIS_GROUP_NAME,
                consumername=REDIS_CONSUMER_NAME,
                streams={REDIS_STREAM_NAME: '>'},
                count=10,
                block=5000
            )

            if not response:

                continue

            for stream, messages in response:
                for msg_id, msg_data in messages:
                    print(f"-> Processing message {msg_id}: {msg_data.get('body', '')}")
                    await process_message(msg_data, r)
                    await r.xack(REDIS_STREAM_NAME, REDIS_GROUP_NAME, msg_id)

        except Exception as e:
            print(f"Error in Redis consumer loop: {e}")
            await asyncio.sleep(5)

async def process_message(msg_data: Dict[str, Any], r: redis.Redis):
    """Parses, replies to, and upserts a message into the SQLite database using LLM."""
    print("DEBUG: process_message started.")
    try:
        print("DEBUG: Calling LLM for conversational parsing...")
        llm_result = await parse_expense_with_llm(msg_data.get('body', ''), GEMINI_MODEL)
        print(f"DEBUG: LLM result: {llm_result}")

        reply_message = llm_result.get("reply_message", "No pude procesar tu mensaje.")
        expense_data = llm_result.get("expense_data")

        # Always publish a reply back to the ingestor
        print("DEBUG: Publishing conversational reply to Redis...")
        confirmation_payload = json.dumps({
            "chat_id": msg_data['chat_id'],
            "original_wid": msg_data['wid'],
            "reply_message": reply_message
        })
        await r.publish("gastos:confirmations", confirmation_payload)
        print("DEBUG: Conversational reply published.")

        # Only save to database if the expense data is valid
        if expense_data and expense_data.get('amount') is not None:
            print("DEBUG: Valid expense data found. Upserting to database...")
            message = Message(
                wid=msg_data['wid'],
                chat_id=msg_data['chat_id'],
                chat_name=msg_data['chat_name'],
                sender_id=msg_data['sender_id'],
                sender_name=msg_data['sender_name'],
                ts=int(msg_data['timestamp']),
                type=msg_data['type'],
                body=msg_data['body'],
                amount=expense_data.get('amount'),
                currency=expense_data.get('currency'),
                category=expense_data.get('category'),
                meta_json=expense_data.get('meta_json')
            )
            await asyncio.to_thread(upsert_message_db, message)
            print("DEBUG: Database upsert complete.")
        else:
            print("DEBUG: No valid expense data found. Skipping database insert.")

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