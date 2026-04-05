import json
from datetime import datetime
from app.database import get_pg_conn


def init_mail_db():
    from app.database import init_postgres
    init_postgres()


def mail_exists(message_id: str) -> bool:
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
    result = c.fetchone()
    conn.close()
    return result is not None


def insert_mail(data: dict):
    conn = get_pg_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO mail_memory (
            message_id, thread_id, received_at, from_email, subject,
            display_title, category, priority, reason, suggested_action,
            short_summary, references_json, group_hints_json, confidence,
            needs_review, raw_body_preview, analysis_status, created_at,
            needs_reply, reply_urgency, reply_reason, suggested_reply_subject,
            suggested_reply, response_type, missing_fields, confidence_level
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (message_id) DO NOTHING
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
        data.get("response_type"),
        json.dumps(data.get("missing_fields", [])),
        data.get("confidence_level"),
    ))

    conn.commit()
    conn.close()