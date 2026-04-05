import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "assistant_memory.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS global_instructions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instruction TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def add_global_instruction(instruction: str):
    instruction = (instruction or "").strip()
    if not instruction:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO global_instructions (instruction) VALUES (?)",
        (instruction,),
    )
    conn.commit()
    conn.close()


def get_global_instructions(limit: int = 20) -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT instruction
        FROM global_instructions
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [row["instruction"] for row in rows]