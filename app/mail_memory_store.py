import sqlite3
import json
from datetime import datetime

from app.config import ASSISTANT_DB_PATH

DB_PATH = ASSISTANT_DB_PATH


def ensure_mail_memory_columns():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    columns_to_add = {
        "response_type": "TEXT",
        "missing_fields": "TEXT",
        "confidence_level": "TEXT",
        "reply_status": "TEXT DEFAULT 'pending'",
    }

    c.execute("PRAGMA table_info(mail_memory)")
    existing_columns = {row[1] for row in c.fetchall()}

    for column_name, column_type in columns_to_add.items():
        if column_name not in existing_columns:
            c.execute(
                f"ALTER TABLE mail_memory ADD COLUMN {column_name} {column_type}"
            )

    conn.commit()
    conn.close()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_mail_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS mail_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE,
        thread_id TEXT,
        received_at TEXT,
        from_email TEXT,
        subject TEXT,
        display_title TEXT,
        category TEXT,
        priority TEXT,
        reason TEXT,
        suggested_action TEXT,
        short_summary TEXT,
        references_json TEXT,
        group_hints_json TEXT,
        confidence REAL,
        needs_review INTEGER,
        raw_body_preview TEXT,
        analysis_status TEXT,
        created_at TEXT,

        needs_reply INTEGER,
        reply_urgency TEXT,
        reply_reason TEXT,
        suggested_reply_subject TEXT,
        suggested_reply TEXT
    )
    """)

    conn.commit()
    conn.close()

    ensure_mail_memory_columns()


def mail_exists(message_id: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM mail_memory WHERE message_id = ?", (message_id,))
    result = c.fetchone()
    conn.close()
    return result is not None


def insert_mail(data: dict):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    INSERT INTO mail_memory (
        message_id,
        thread_id,
        received_at,
        from_email,
        subject,
        display_title,
        category,
        priority,
        reason,
        suggested_action,
        short_summary,
        references_json,
        group_hints_json,
        confidence,
        needs_review,
        raw_body_preview,
        analysis_status,
        created_at,
        needs_reply,
        reply_urgency,
        reply_reason,
        suggested_reply_subject,
        suggested_reply
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["message_id"],
        data.get("thread_id"),
        data.get("received_at"),
        data.get("from_email"),
        data.get("subject"),
        data.get("display_title"),
        data.get("category"),
        data.get("priority"),
        data.get("reason"),
        data.get("suggested_action"),
        data.get("short_summary"),
        json.dumps(data.get("references", [])),
        json.dumps(data.get("group_hints", [])),
        data.get("confidence", 0.0),
        int(data.get("needs_review", False)),
        data.get("raw_body_preview"),
        data.get("analysis_status", "pending"),
        datetime.utcnow().isoformat(),
        int(data.get("needs_reply", False)),
        data.get("reply_urgency"),
        data.get("reply_reason"),
        data.get("suggested_reply_subject"),
        data.get("suggested_reply"),
    ))

    conn.commit()
    conn.close()