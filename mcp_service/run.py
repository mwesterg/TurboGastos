import os
from mcp_sqlite import run_server

db_path = os.getenv("DB_PATH", "/data/gastos.db")
run_server(db_path)
