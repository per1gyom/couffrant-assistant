import psycopg2
from app.config import DATABASE_URL


def get_pg_conn():
    return psycopg2.connect(DATABASE_URL)


def init_postgres():
    """
    Crée toutes les tables nécessaires.
    Architecture multi-utilisateurs : chaque utilisateur a sa propre mémoire.
    Seuls aria_contacts et global_instructions sont partagés.
    """
    conn = get_pg_conn()
    c = conn.cursor()

    # ── mail_memory — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS mail_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            message_id TEXT,
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
            mailbox_source TEXT DEFAULT 'outlook',
            UNIQUE(message_id, username)
        )
    """)

    # ── aria_memory — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            user_input TEXT,
            aria_response TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_style_examples — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_style_examples (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            situation TEXT,
            example_text TEXT,
            tags TEXT,
            quality_score REAL DEFAULT 1.0,
            used_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'sent_mail',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_hot_summary — par utilisateur (username = clé) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_hot_summary (
            username TEXT PRIMARY KEY,
            content TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_contacts — PARTAGÉ (contacts entreprise) ──
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

    # ── aria_rules — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_rules (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            category TEXT DEFAULT 'général',
            rule TEXT NOT NULL,
            source TEXT DEFAULT 'auto',
            confidence REAL DEFAULT 0.7,
            reinforcements INTEGER DEFAULT 1,
            active BOOLEAN DEFAULT true,
            context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_insights — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_insights (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            topic TEXT,
            insight TEXT NOT NULL,
            source TEXT DEFAULT 'conversation',
            reinforcements INTEGER DEFAULT 1,
            context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_session_digests — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_session_digests (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            session_date DATE DEFAULT CURRENT_DATE,
            conversation_count INTEGER,
            summary TEXT,
            rules_learned JSONB DEFAULT '[]',
            topics JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── sent_mail_memory — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_mail_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            message_id TEXT,
            sent_at TEXT,
            to_email TEXT,
            subject TEXT,
            body_preview TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(message_id, username)
        )
    """)

    # ── aria_profile — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_profile (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            profile_type TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── users — auth + scope ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            scope TEXT DEFAULT 'couffrant_solar',
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── oauth_tokens — par utilisateur ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY,
            provider TEXT,
            username TEXT DEFAULT 'guillaume',
            access_token TEXT,
            refresh_token TEXT,
            expires_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(provider, username)
        )
    """)

    # ── Tables partagées ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS reply_learning_memory (
            id SERIAL PRIMARY KEY,
            mail_subject TEXT, mail_from TEXT, mail_body_preview TEXT,
            category TEXT, ai_reply TEXT, final_reply TEXT,
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
            email TEXT, access_token TEXT, refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    conn.close()

    # ── Migrations pour les bases existantes ──
    conn = get_pg_conn()
    c = conn.cursor()

    migrations = [
        # Ajout colonne username sur toutes les tables mémoire
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_style_examples ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_session_digests ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_profile ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE sent_mail_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE oauth_tokens ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        # Autres colonnes
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS mailbox_source TEXT DEFAULT 'outlook'",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS reinforcements INTEGER DEFAULT 1",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS reinforcements INTEGER DEFAULT 1",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS context TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS context TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS scope TEXT DEFAULT 'couffrant_solar'",
        # aria_hot_summary : ajout username + index unique
        "ALTER TABLE aria_hot_summary ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "CREATE UNIQUE INDEX IF NOT EXISTS aria_hot_summary_username_idx ON aria_hot_summary (username)",
        # oauth_tokens : nouvelle contrainte unique (provider, username)
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_unique",
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_username_unique",
        "ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_provider_username_unique UNIQUE (provider, username)",
        # mail_memory : nouvelle contrainte unique (message_id, username)
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_message_id_key",
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_msg_user_unique",
        "ALTER TABLE mail_memory ADD CONSTRAINT mail_memory_msg_user_unique UNIQUE (message_id, username)",
        # sent_mail_memory : nouvelle contrainte unique (message_id, username)
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_memory_message_id_key",
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_msg_user_unique",
        "ALTER TABLE sent_mail_memory ADD CONSTRAINT sent_mail_msg_user_unique UNIQUE (message_id, username)",
    ]

    for migration in migrations:
        try:
            c.execute(migration)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Migration] Skip ({str(e)[:60]})")

    conn.close()
