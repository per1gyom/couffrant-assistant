import psycopg2
from app.config import DATABASE_URL


def get_pg_conn():
    return psycopg2.connect(DATABASE_URL)


def init_postgres():
    """
    Crée toutes les tables nécessaires.
    Architecture multi-tenants : tenant = société cliente.
    Chaque utilisateur appartient à un tenant.
    Données partagées (contacts, consignes) scopées par tenant.
    Données personnelles (mémoire, règles) isolées par username.
    """
    conn = get_pg_conn()
    c = conn.cursor()

    # ── tenants — sociétés clientes ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            settings JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            user_input TEXT,
            aria_response TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_hot_summary (
            username TEXT PRIMARY KEY,
            content TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── aria_contacts — partagés par tenant ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_contacts (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT DEFAULT 'couffrant_solar',
            email TEXT,
            name TEXT,
            company TEXT,
            role TEXT,
            summary TEXT,
            last_seen TEXT,
            last_subject TEXT,
            mail_count INTEGER DEFAULT 0,
            tags TEXT,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(email, tenant_id)
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_profile (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            profile_type TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            scope TEXT DEFAULT 'couffrant_solar',
            tenant_id TEXT DEFAULT 'couffrant_solar',
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS user_tools (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            tool TEXT NOT NULL,
            access_level TEXT DEFAULT 'read_only',
            enabled BOOLEAN DEFAULT true,
            config JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username, tool)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reply_learning_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            mail_subject TEXT, mail_from TEXT, mail_body_preview TEXT,
            category TEXT, ai_reply TEXT, final_reply TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── global_instructions — partagées par tenant ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS global_instructions (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT DEFAULT 'couffrant_solar',
            instruction TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── gmail_tokens — par username (priorité 2) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            email TEXT,
            access_token TEXT,
            refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username)
        )
    """)

    conn.commit()
    conn.close()

    # ── Migrations pour les bases existantes ──
    conn = get_pg_conn()
    c = conn.cursor()

    migrations = [
        # Colonnes username existantes
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_style_examples ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_session_digests ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_profile ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE sent_mail_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE oauth_tokens ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS mailbox_source TEXT DEFAULT 'outlook'",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS reinforcements INTEGER DEFAULT 1",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS reinforcements INTEGER DEFAULT 1",
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS context TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS context TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS scope TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE aria_hot_summary ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "CREATE UNIQUE INDEX IF NOT EXISTS aria_hot_summary_username_idx ON aria_hot_summary (username)",
        # Contraintes
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_unique",
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_username_unique",
        "ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_provider_username_unique UNIQUE (provider, username)",
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_message_id_key",
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_msg_user_unique",
        "ALTER TABLE mail_memory ADD CONSTRAINT mail_memory_msg_user_unique UNIQUE (message_id, username)",
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_memory_message_id_key",
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_msg_user_unique",
        "ALTER TABLE sent_mail_memory ADD CONSTRAINT sent_mail_msg_user_unique UNIQUE (message_id, username)",
        # Fix 1 — reply_learning_memory.username
        "ALTER TABLE reply_learning_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        # Priorité 3 — multi-tenant
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE aria_contacts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE global_instructions ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        # Priorité 2 — gmail_tokens par username
        "ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        # Contrainte email unique -> unique par tenant (aria_contacts)
        "ALTER TABLE aria_contacts DROP CONSTRAINT IF EXISTS aria_contacts_email_key",
        # user_tools
        """CREATE TABLE IF NOT EXISTS user_tools (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tool TEXT NOT NULL,
            access_level TEXT DEFAULT 'read_only', enabled BOOLEAN DEFAULT true,
            config JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(username, tool))""",
        # tenants
        """CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            settings JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW())""",
        # Seed tenant par défaut
        "INSERT INTO tenants (id, name, settings) VALUES ('couffrant_solar', 'Couffrant Solar', '{\"sharepoint_folder\": \"1_Photovolta\u00efque\"}') ON CONFLICT (id) DO NOTHING",
    ]

    for migration in migrations:
        try:
            c.execute(migration)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Migration] Skip ({str(e)[:60]})")

    conn.close()
