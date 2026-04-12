"""
Base de données PostgreSQL — pool de connexions + schéma + migrations.

Pool de connexions (ThreadedConnectionPool, 2-8 connexions) :
  - get_pg_conn() retourne un wrapper transparent _PooledConn
  - conn.close() remet la connexion dans le pool (pas de fermeture TCP)
  - Fallback automatique sur connexion directe si le pool est indisponible
  - Zéro changement requis dans les fichiers appelants
"""
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from app.config import DATABASE_URL


# ─── POOL DE CONNEXIONS ───

_pool: ThreadedConnectionPool = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """Initialise le pool une seule fois (lazy, thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = ThreadedConnectionPool(2, 8, DATABASE_URL)
                except Exception as e:
                    print(f"[DB] Pool non initialisé ({e}) — fallback connexions directes")
    return _pool


class _PooledConn:
    """
    Wrapper transparent autour d'une connexion psycopg2.
    close() retourne la connexion au pool au lieu de la fermer (TCP maintenu).
    """

    def __init__(self, conn, pool):
        self.__dict__["_conn"] = conn
        self.__dict__["_pool"] = pool

    def __getattr__(self, name):
        return getattr(self.__dict__["_conn"], name)

    def cursor(self, *args, **kwargs):
        return self.__dict__["_conn"].cursor(*args, **kwargs)

    def commit(self):
        return self.__dict__["_conn"].commit()

    def rollback(self):
        return self.__dict__["_conn"].rollback()

    def close(self):
        pool = self.__dict__.get("_pool")
        conn = self.__dict__.get("_conn")
        if pool and conn:
            try:
                pool.putconn(conn)
                return
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_pg_conn():
    pool = _get_pool()
    if pool:
        try:
            conn = pool.getconn()
            if conn:
                return _PooledConn(conn, pool)
        except Exception as e:
            print(f"[DB] Pool getconn() échoué ({e}) — connexion directe")
    return psycopg2.connect(DATABASE_URL)


def close_pool():
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
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            settings JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, email TEXT,
            scope TEXT DEFAULT 'user', tenant_id TEXT DEFAULT 'couffrant_solar',
            last_login TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT false, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL,
            subscription_id TEXT UNIQUE NOT NULL, resource TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL, client_state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS mail_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            message_id TEXT, thread_id TEXT, received_at TEXT,
            from_email TEXT, subject TEXT, display_title TEXT,
            category TEXT, priority TEXT, reason TEXT, suggested_action TEXT,
            short_summary TEXT, references_json TEXT, group_hints_json TEXT,
            confidence REAL, needs_review INTEGER, raw_body_preview TEXT,
            analysis_status TEXT, created_at TEXT, needs_reply INTEGER,
            reply_urgency TEXT, reply_reason TEXT, suggested_reply_subject TEXT,
            suggested_reply TEXT, response_type TEXT, missing_fields TEXT,
            confidence_level TEXT, reply_status TEXT DEFAULT 'pending',
            mailbox_source TEXT DEFAULT 'outlook', UNIQUE(message_id, username)
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
            tags TEXT, updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(email, tenant_id)
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
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, chat_id TEXT NOT NULL,
            chat_type TEXT DEFAULT 'chat', chat_label TEXT,
            last_message_id TEXT, last_synced_at TIMESTAMP DEFAULT NOW(),
            notes TEXT, UNIQUE(username, chat_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'couffrant_solar',
            username TEXT NOT NULL,
            conversation_id INTEGER,
            action_type TEXT NOT NULL,
            action_label TEXT,
            payload_json JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result_json JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            confirmed_at TIMESTAMP,
            executed_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '24 hours'),
            CONSTRAINT pending_actions_status_check CHECK (
                status IN ('pending', 'confirmed', 'executing', 'executed', 'failed', 'cancelled', 'expired')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions (username, status, created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_tenant ON pending_actions (tenant_id, status)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            username TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd_estimate NUMERIC(10, 6),
            purpose TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_tenant_date ON llm_usage (tenant_id, created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_username_date ON llm_usage (username, created_at DESC)")

    # Métadonnées de raisonnement + feedback 👍👎 (Phase 3b)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_response_metadata (
            id SERIAL PRIMARY KEY,
            aria_memory_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'couffrant_solar',
            model_tier TEXT NOT NULL,
            model_name TEXT NOT NULL,
            via_rag BOOLEAN DEFAULT false,
            rule_ids_injected JSONB DEFAULT '[]',
            feedback_type TEXT,
            feedback_comment TEXT,
            corrective_rule_id INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT feedback_type_check CHECK (
                feedback_type IS NULL OR feedback_type IN ('positive', 'negative')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_response_meta_memory ON aria_response_metadata (aria_memory_id, username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_response_meta_feedback ON aria_response_metadata (username, feedback_type, created_at DESC)")

    # Mode Dirigeant : accès multi-tenant par utilisateur (5D-1)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_tenant_access (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username, tenant_id),
            CONSTRAINT uta_role_check CHECK (role IN ('owner', 'admin', 'user'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_uta_username ON user_tenant_access (username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_uta_tenant ON user_tenant_access (tenant_id)")

    # Alertes proactives (5E-4a)
    c.execute("""
        CREATE TABLE IF NOT EXISTS proactive_alerts (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            tenant_id TEXT,
            alert_type TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            title TEXT NOT NULL,
            body TEXT,
            source_type TEXT,
            source_id TEXT,
            seen BOOLEAN DEFAULT false,
            dismissed BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours'),
            CONSTRAINT alert_type_check CHECK (
                alert_type IN ('mail_urgent', 'deadline', 'reminder', 'pattern', 'info')
            ),
            CONSTRAINT alert_priority_check CHECK (
                priority IN ('low', 'normal', 'high', 'critical')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user_active ON proactive_alerts (username, seen, dismissed, created_at DESC)")

    # Patterns comportementaux (5G-4)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_patterns (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            tenant_id TEXT,
            pattern_type TEXT NOT NULL,
            description TEXT NOT NULL,
            evidence TEXT,
            confidence REAL DEFAULT 0.5,
            occurrences INTEGER DEFAULT 1,
            last_seen_at TIMESTAMP DEFAULT NOW(),
            active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT pattern_type_check CHECK (
                pattern_type IN ('temporal', 'relational', 'thematic', 'workflow', 'preference')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_patterns_user ON aria_patterns (username, active, confidence DESC)")

    # Historique des versions de règles (5F-2)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_rules_history (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            tenant_id TEXT,
            category TEXT,
            rule TEXT NOT NULL,
            confidence REAL,
            reinforcements INTEGER,
            active BOOLEAN,
            change_type TEXT NOT NULL,
            changed_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT change_type_check CHECK (
                change_type IN ('created', 'updated', 'reinforced', 'deactivated', 'rollback')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_rules_history_rule ON aria_rules_history (rule_id, changed_at DESC)")

    conn.commit()
    conn.close()

    # ─── MIGRATIONS IDEMPOTENTES ───
    conn = get_pg_conn()
    c = conn.cursor()
    migrations = [
        # ── Migrations historiques ──
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
        """INSERT INTO tenants (id, name, settings) VALUES ('couffrant_solar', 'Couffrant Solar', '{"email_provider": "microsoft", "sharepoint_folder": "1_Photovoltaïque"}') ON CONFLICT (id) DO NOTHING""",
        "CREATE EXTENSION IF NOT EXISTS vector",
        "ALTER TABLE mail_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_insights ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE aria_contacts ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE teams_sync_state ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "CREATE INDEX IF NOT EXISTS idx_mail_embedding ON mail_memory USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_insights_embedding ON aria_insights USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_memory_embedding ON aria_memory USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS idx_contacts_embedding ON aria_contacts USING hnsw (embedding vector_cosine_ops)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_reset_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_locked BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_attempts_count INT DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_attempts_round INT DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_locked_until TIMESTAMP",
        """INSERT INTO oauth_tokens (provider, username, access_token, refresh_token, expires_at)
           SELECT 'google', g.username, g.access_token, g.refresh_token,
                  NOW() + INTERVAL '1 hour'
           FROM gmail_tokens g
           WHERE g.access_token IS NOT NULL
             AND NOT EXISTS (
               SELECT 1 FROM oauth_tokens o
               WHERE o.provider='google' AND o.username=g.username
             )""",
        # ── Phase 2 : tenant_id sur toutes les tables ──
        "ALTER TABLE aria_rules           ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_insights        ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_memory          ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE mail_memory          ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_hot_summary     ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_session_digests ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_style_examples  ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE aria_profile         ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE oauth_tokens         ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE reply_learning_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE sent_mail_memory     ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "ALTER TABLE teams_sync_state     ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "UPDATE aria_rules           a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_insights        a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_memory          a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE mail_memory          a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_hot_summary     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_session_digests a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_style_examples  a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_profile         a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE oauth_tokens         a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE reply_learning_memory a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE sent_mail_memory     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE teams_sync_state     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
        "UPDATE aria_rules            SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_insights         SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_memory           SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE mail_memory           SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_hot_summary      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_session_digests  SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_style_examples   SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE aria_profile          SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE oauth_tokens          SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE reply_learning_memory SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE sent_mail_memory      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "UPDATE teams_sync_state      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_aria_rules_tenant_user       ON aria_rules (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_aria_insights_tenant_user    ON aria_insights (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_aria_memory_tenant_user      ON aria_memory (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_mail_memory_tenant_user      ON mail_memory (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_style_examples_tenant_user   ON aria_style_examples (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_tenant_user     ON oauth_tokens (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_reply_learning_tenant_user   ON reply_learning_memory (tenant_id, username)",
        "CREATE INDEX IF NOT EXISTS idx_sent_mail_tenant_user        ON sent_mail_memory (tenant_id, username)",
        # ── Phase 3a : vectorisation des règles pour RAG ──
        "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "CREATE INDEX IF NOT EXISTS idx_rules_embedding ON aria_rules USING hnsw (embedding vector_cosine_ops)",
        "ALTER TABLE aria_hot_summary ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        # ── 5D-1 : peuplement user_tenant_access depuis données existantes ──
        "INSERT INTO user_tenant_access (username, tenant_id, role) SELECT username, tenant_id, CASE WHEN scope = 'super_admin' THEN 'owner' WHEN scope = 'admin' THEN 'admin' ELSE 'user' END FROM users WHERE tenant_id IS NOT NULL ON CONFLICT (username, tenant_id) DO NOTHING",
    ]
    for m in migrations:
        try:
            c.execute(m)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Migration] Skip ({str(e)[:60]})")
    conn.close()
