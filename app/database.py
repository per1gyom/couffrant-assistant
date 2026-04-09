"""
Base de données PostgreSQL — pool de connexions + schéma + migrations.

Pool de connexions (ThreadedConnectionPool, 2-8 connexions) :
  - get_pg_conn() retourne un wrapper transparent
  - conn.close() remet la connexion dans le pool (pas de fermeture TCP)
  - Zéro changement requis dans les fichiers appelants
  - Gain : élimination de 9-12 connexions TCP par conversation (~100-200ms)
"""
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from app.config import DATABASE_URL


# ─── POOL DE CONNEXIONS ───

_pool: ThreadedConnectionPool = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """Initialise et retourne le pool (lazy, thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(2, 8, DATABASE_URL)
    return _pool


class _PooledConn:
    """
    Wrapper transparent autour d'une connexion psycopg2.
    close() retourne la connexion au pool au lieu de la fermer (TCP maintenu).
    Tous les autres attributs sont délégués à la connexion sous-jacente.
    """
    __slots__ = ("_conn", "_pool")

    def __init__(self, conn, pool: ThreadedConnectionPool):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_pool", pool)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def cursor(self, *args, **kwargs):
        return object.__getattribute__(self, "_conn").cursor(*args, **kwargs)

    def commit(self):
        return object.__getattribute__(self, "_conn").commit()

    def rollback(self):
        return object.__getattribute__(self, "_conn").rollback()

    def close(self):
        """Retourne la connexion au pool — ne ferme PAS le socket TCP."""
        pool = object.__getattribute__(self, "_pool")
        conn = object.__getattribute__(self, "_conn")
        try:
            pool.putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def get_pg_conn() -> _PooledConn:
    """
    Retourne une connexion depuis le pool.
    Fallback sur connexion directe si le pool est épuisé.
    Utilisation identique à psycopg2.connect() — conn.close() remet en pool.
    """
    try:
        pool = _get_pool()
        conn = pool.getconn()
        return _PooledConn(conn, pool)
    except Exception:
        # Fallback : connexion directe si pool saturé ou non initialisé
        return psycopg2.connect(DATABASE_URL)


def close_pool():
    """Ferme proprement toutes les connexions du pool (arrêt de l'app)."""
    global _pool
    if _pool:
        try:
            _pool.closeall()
        except Exception:
            pass
        _pool = None


# ─── SCHÉMA ───

def init_postgres():
    conn = get_pg_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            settings JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            scope TEXT DEFAULT 'user',
            tenant_id TEXT DEFAULT 'couffrant_solar',
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            subscription_id TEXT UNIQUE NOT NULL,
            resource TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            client_state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS mail_memory (
            id SERIAL PRIMARY KEY,
            username TEXT DEFAULT 'guillaume',
            message_id TEXT, thread_id TEXT, received_at TEXT,
            from_email TEXT, subject TEXT, display_title TEXT,
            category TEXT, priority TEXT, reason TEXT, suggested_action TEXT,
            short_summary TEXT, references_json TEXT, group_hints_json TEXT,
            confidence REAL, needs_review INTEGER, raw_body_preview TEXT,
            analysis_status TEXT, created_at TEXT, needs_reply INTEGER,
            reply_urgency TEXT, reply_reason TEXT, suggested_reply_subject TEXT,
            suggested_reply TEXT, response_type TEXT, missing_fields TEXT,
            confidence_level TEXT, reply_status TEXT DEFAULT 'pending',
            mailbox_source TEXT DEFAULT 'outlook',
            UNIQUE(message_id, username)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            user_input TEXT, aria_response TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_style_examples (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            situation TEXT, example_text TEXT, tags TEXT,
            quality_score REAL DEFAULT 1.0, used_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'sent_mail', created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_hot_summary (
            username TEXT PRIMARY KEY, content TEXT, updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_contacts (
            id SERIAL PRIMARY KEY, tenant_id TEXT DEFAULT 'couffrant_solar',
            email TEXT, name TEXT, company TEXT, role TEXT, summary TEXT,
            last_seen TEXT, last_subject TEXT, mail_count INTEGER DEFAULT 0,
            tags TEXT, updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(email, tenant_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_rules (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            category TEXT DEFAULT 'général', rule TEXT NOT NULL,
            source TEXT DEFAULT 'auto', confidence REAL DEFAULT 0.7,
            reinforcements INTEGER DEFAULT 1, active BOOLEAN DEFAULT true,
            context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_insights (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            topic TEXT, insight TEXT NOT NULL, source TEXT DEFAULT 'conversation',
            reinforcements INTEGER DEFAULT 1, context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_session_digests (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            session_date DATE DEFAULT CURRENT_DATE, conversation_count INTEGER,
            summary TEXT, rules_learned JSONB DEFAULT '[]',
            topics JSONB DEFAULT '[]', created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_mail_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            message_id TEXT, sent_at TEXT, to_email TEXT, subject TEXT,
            body_preview TEXT, created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(message_id, username)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_profile (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            profile_type TEXT, content TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY, provider TEXT, username TEXT DEFAULT 'guillaume',
            access_token TEXT, refresh_token TEXT, expires_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(provider, username)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_tools (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tool TEXT NOT NULL,
            access_level TEXT DEFAULT 'read_only', enabled BOOLEAN DEFAULT true,
            config JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(username, tool)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reply_learning_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            mail_subject TEXT, mail_from TEXT, mail_body_preview TEXT,
            category TEXT, ai_reply TEXT, final_reply TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS global_instructions (
            id SERIAL PRIMARY KEY, tenant_id TEXT DEFAULT 'couffrant_solar',
            instruction TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            email TEXT, access_token TEXT, refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW(), UNIQUE(username)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS teams_sync_state (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_type TEXT DEFAULT 'chat',
            chat_label TEXT,
            last_message_id TEXT,
            last_synced_at TIMESTAMP DEFAULT NOW(),
            notes TEXT,
            UNIQUE(username, chat_id)
        )
    """)

    conn.commit()
    conn.close()

    # ─── MIGRATIONS IDEMPOTENTES ───
    # Uniquement les ALTER TABLE et correctifs — pas de CREATE TABLE (déjà fait ci-dessus)
    conn = get_pg_conn()
    c = conn.cursor()
    migrations = [
        # Colonnes ajoutées progressivement
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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS scope TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
        "ALTER TABLE aria_hot_summary ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE reply_learning_memory ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        "ALTER TABLE aria_contacts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE global_instructions ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'couffrant_solar'",
        "ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS username TEXT DEFAULT 'guillaume'",
        # Contraintes et index
        "CREATE UNIQUE INDEX IF NOT EXISTS aria_hot_summary_username_idx ON aria_hot_summary (username)",
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_unique",
        "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_username_unique",
        "ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_provider_username_unique UNIQUE (provider, username)",
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_message_id_key",
        "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_msg_user_unique",
        "ALTER TABLE mail_memory ADD CONSTRAINT mail_memory_msg_user_unique UNIQUE (message_id, username)",
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_memory_message_id_key",
        "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_msg_user_unique",
        "ALTER TABLE sent_mail_memory ADD CONSTRAINT sent_mail_msg_user_unique UNIQUE (message_id, username)",
        "ALTER TABLE aria_contacts DROP CONSTRAINT IF EXISTS aria_contacts_email_key",
        # Tenant par défaut
        "INSERT INTO tenants (id, name, settings) VALUES ('couffrant_solar', 'Couffrant Solar', '{\"email_provider\": \"microsoft\", \"sharepoint_folder\": \"1_Photovoltaïque\"}') ON CONFLICT (id) DO NOTHING",
        # Vectorisation pgvector
        "CREATE EXTENSION IF NOT EXISTS vector",
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_contacts ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE teams_sync_state ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        # Index HNSW
        "CREATE INDEX IF NOT EXISTS idx_mail_embedding ON mail_memory USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_insights_embedding ON aria_insights USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_memory_embedding ON aria_memory USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_contacts_embedding ON aria_contacts USING hnsw (embedding vector_cosine_ops)",
        # Sécurité : colonnes must_reset_password et account_locked
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_reset_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_locked BOOLEAN DEFAULT FALSE",
    ]
    for m in migrations:
        try:
            c.execute(m)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Migration] Skip ({str(e)[:60]})")
    conn.close()
