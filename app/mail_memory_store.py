import json
from datetime import datetime
from app.database import get_pg_conn


def init_mail_db():
    from app.database import init_postgres
    init_postgres()


def mail_exists(message_id: str, username: str = 'guillaume') -> bool:
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s AND username = %s", (message_id, username))
    result = c.fetchone()
    conn.close()
    return result is not None


def insert_mail(data: dict):
    """
    Insère un mail en base.
    Génère automatiquement un vecteur sémantique si OPENAI_API_KEY est configuré.
    Le texte vectorisé est : sujet + résumé + aperçu corps.
    """
    # Texte à vectoriser : ce qui représente le mieux le contenu du mail
    subject = data.get("subject") or ""
    summary = data.get("short_summary") or ""
    preview = data.get("raw_body_preview") or ""
    from_email = data.get("from_email") or ""
    embed_text = f"De : {from_email}\nSujet : {subject}\n{summary}\n{preview}".strip()

    embedding = None
    try:
        from app.embedding import embed
        embedding = embed(embed_text)
    except Exception:
        pass

    conn = get_pg_conn()
    c = conn.cursor()

    if embedding is not None:
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        c.execute("""
            INSERT INTO mail_memory (
                username, message_id, thread_id, received_at, from_email, subject,
                display_title, category, priority, reason, suggested_action,
                short_summary, references_json, group_hints_json, confidence,
                needs_review, raw_body_preview, analysis_status, created_at,
                needs_reply, reply_urgency, reply_reason, suggested_reply_subject,
                suggested_reply, response_type, missing_fields, confidence_level,
                mailbox_source, embedding
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s::vector
            ) ON CONFLICT DO NOTHING
        """, (
            data.get("username", "guillaume"), data["message_id"],
            data.get("thread_id"), data.get("received_at"),
            data.get("from_email"), data.get("subject"),
            data.get("display_title"), data.get("category"),
            data.get("priority"), data.get("reason"),
            data.get("suggested_action"), data.get("short_summary"),
            json.dumps(data.get("references", [])),
            json.dumps(data.get("group_hints", [])),
            data.get("confidence", 0.0),
            int(data.get("needs_review", False)),
            data.get("raw_body_preview"),
            data.get("analysis_status", "pending"),
            datetime.utcnow().isoformat(),
            int(data.get("needs_reply", False)),
            data.get("reply_urgency"), data.get("reply_reason"),
            data.get("suggested_reply_subject"), data.get("suggested_reply"),
            data.get("response_type"),
            json.dumps(data.get("missing_fields", [])),
            data.get("confidence_level"),
            data.get("mailbox_source", "outlook"),
            vec_str,
        ))
    else:
        c.execute("""
            INSERT INTO mail_memory (
                username, message_id, thread_id, received_at, from_email, subject,
                display_title, category, priority, reason, suggested_action,
                short_summary, references_json, group_hints_json, confidence,
                needs_review, raw_body_preview, analysis_status, created_at,
                needs_reply, reply_urgency, reply_reason, suggested_reply_subject,
                suggested_reply, response_type, missing_fields, confidence_level, mailbox_source
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s
            ) ON CONFLICT DO NOTHING
        """, (
            data.get("username", "guillaume"), data["message_id"],
            data.get("thread_id"), data.get("received_at"),
            data.get("from_email"), data.get("subject"),
            data.get("display_title"), data.get("category"),
            data.get("priority"), data.get("reason"),
            data.get("suggested_action"), data.get("short_summary"),
            json.dumps(data.get("references", [])),
            json.dumps(data.get("group_hints", [])),
            data.get("confidence", 0.0),
            int(data.get("needs_review", False)),
            data.get("raw_body_preview"),
            data.get("analysis_status", "pending"),
            datetime.utcnow().isoformat(),
            int(data.get("needs_reply", False)),
            data.get("reply_urgency"), data.get("reply_reason"),
            data.get("suggested_reply_subject"), data.get("suggested_reply"),
            data.get("response_type"),
            json.dumps(data.get("missing_fields", [])),
            data.get("confidence_level"),
            data.get("mailbox_source", "outlook"),
        ))

    conn.commit()
    conn.close()
