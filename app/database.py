import psycopg2
import psycopg2.extras
from app.config import DATABASE_URL


def get_pg_conn():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_postgres():
    """Crée toutes les tables nécessaires.
    Les CREATE TABLE et les migrations sont dans des transactions séparées
    pour éviter qu'un rollback de migration annule les créations de tables.
    """

    # ── Transaction 1 : création de toutes les tables ──
    conn = get_pg_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS mail_memory (
            id SERIAL PRIMARY KEY,
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
            suggested_reply TEXT,
            response_type TEXT,
            missing_fields TEXT,
            confidence_level TEXT,
            reply_status TEXT DEFAULT 'pending',
            mailbox_source TEXT DEFAULT 'outlook'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_memory (
            id SERIAL PRIMARY KEY,
            user_input TEXT,
            aria_response TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reply_learning_memory (
            id SERIAL PRIMARY KEY,
            mail_subject TEXT,
            mail_from TEXT,
            mail_body_preview TEXT,
            category TEXT,
            ai_reply TEXT,
            final_reply TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_mail_memory (
            id SERIAL PRIMARY KEY,
            message_id TEXT UNIQUE,
            sent_at TEXT,
            to_email TEXT,
            subject TEXT,
            body_preview TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_profile (
            id SERIAL PRIMARY KEY,
            profile_type TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS global_instructions (
            id SERIAL PRIMARY KEY,
            instruction TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            id SERIAL PRIMARY KEY,
            email TEXT,
            access_token TEXT,
            refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY,
            provider TEXT UNIQUE,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # COUCHE 1 — Résumé chaud
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_hot_summary (
            id INTEGER PRIMARY KEY DEFAULT 1,
            content TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        INSERT INTO aria_hot_summary (id, content, updated_at)
        VALUES (1, '', NOW())
        ON CONFLICT (id) DO NOTHING
    """)

    # COUCHE 2 — Fiches contacts
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_contacts (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            company TEXT,
            role TEXT,
            summary TEXT,
            last_seen TEXT,
            last_subject TEXT,
            mail_count INTEGER DEFAULT 0,
            tags TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # STYLE — Exemples de rédaction
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_style_examples (
            id SERIAL PRIMARY KEY,
            situation TEXT,
            example_text TEXT,
            tags TEXT,
            quality_score REAL DEFAULT 1.0,
            used_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'sent_mail',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Commit transaction 1 — toutes les tables sont créées
    conn.commit()
    conn.close()

    # ── Transaction 2 : migrations (indépendantes) ──
    conn = get_pg_conn()
    c = conn.cursor()

    try:
        c.execute("ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS mailbox_source TEXT DEFAULT 'outlook'")
        conn.commit()
    except Exception:
        conn.rollback()

    try:
        c.execute("ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_provider_unique UNIQUE (provider)")
        conn.commit()
    except Exception:
        conn.rollback()

    conn.close()
