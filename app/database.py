"""
Base de données PostgreSQL — pool de connexions + schéma + migrations.

Pool de connexions (ThreadedConnectionPool, 2-8 connexions) :
  - get_pg_conn() retourne un wrapper transparent _PooledConn
  - conn.close() remet la connexion dans le pool (pas de fermeture TCP)
  - Fallback automatique sur connexion directe si le pool est indisponible
  - Zéro changement requis dans les fichiers appelants

Migrations SQL : voir app/database_migrations.py
Ajouter les nouvelles migrations dans ce fichier uniquement.
"""
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from app.config import DATABASE_URL
from app.logging_config import get_logger

logger = get_logger("raya.db")


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
                    logger.warning("[DB] Pool non initialisé (%s) — fallback connexions directes", e)
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
            logger.warning("[DB] Pool getconn() échoué (%s) — connexion directe", e)
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
            id SERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, username TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd_estimate NUMERIC(10, 6), purpose TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_tenant_date ON llm_usage (tenant_id, created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_username_date ON llm_usage (username, created_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_response_metadata (
            id SERIAL PRIMARY KEY, aria_memory_id INTEGER NOT NULL,
            username TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'couffrant_solar',
            model_tier TEXT NOT NULL, model_name TEXT NOT NULL,
            via_rag BOOLEAN DEFAULT false, rule_ids_injected JSONB DEFAULT '[]',
            feedback_type TEXT, feedback_comment TEXT, corrective_rule_id INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT feedback_type_check CHECK (
                feedback_type IS NULL OR feedback_type IN ('positive', 'negative')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_response_meta_memory ON aria_response_metadata (aria_memory_id, username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_response_meta_feedback ON aria_response_metadata (username, feedback_type, created_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_tenant_access (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username, tenant_id),
            CONSTRAINT uta_role_check CHECK (role IN ('owner', 'admin', 'user'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_uta_username ON user_tenant_access (username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_uta_tenant ON user_tenant_access (tenant_id)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS proactive_alerts (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            alert_type TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal',
            title TEXT NOT NULL, body TEXT, source_type TEXT, source_id TEXT,
            seen BOOLEAN DEFAULT false, dismissed BOOLEAN DEFAULT false,
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_patterns (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            pattern_type TEXT NOT NULL, description TEXT NOT NULL,
            evidence TEXT, confidence REAL DEFAULT 0.5, occurrences INTEGER DEFAULT 1,
            last_seen_at TIMESTAMP DEFAULT NOW(), active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT pattern_type_check CHECK (
                pattern_type IN ('temporal', 'relational', 'thematic', 'workflow', 'preference')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_patterns_user ON aria_patterns (username, active, confidence DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS aria_rules_history (
            id SERIAL PRIMARY KEY, rule_id INTEGER NOT NULL,
            username TEXT NOT NULL, tenant_id TEXT, category TEXT, rule TEXT NOT NULL,
            confidence REAL, reinforcements INTEGER, active BOOLEAN,
            change_type TEXT NOT NULL, changed_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT change_type_check CHECK (
                change_type IN ('created', 'updated', 'reinforced', 'deactivated', 'rollback')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_rules_history_rule ON aria_rules_history (rule_id, changed_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            action_type TEXT NOT NULL, action_target TEXT, action_detail TEXT,
            source TEXT DEFAULT 'raya', created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_date ON activity_log (username, created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log (username, action_type, created_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS dossier_narratives (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
            narrative TEXT NOT NULL, key_facts JSONB DEFAULT '[]',
            last_event_date TIMESTAMP, updated_at TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username, tenant_id, entity_type, entity_key),
            CONSTRAINT entity_type_check CHECK (
                entity_type IN ('contact', 'project', 'company', 'topic')
            )
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_narratives_user ON dossier_narratives (username, entity_type)")
    c.execute("ALTER TABLE dossier_narratives ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_narratives_embedding ON dossier_narratives USING hnsw (embedding vector_cosine_ops)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            report_date DATE DEFAULT CURRENT_DATE, content TEXT NOT NULL,
            sections JSONB DEFAULT '[]', delivered BOOLEAN DEFAULT false,
            delivered_via TEXT, delivered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(), UNIQUE(username, report_date)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_reports_user ON daily_reports (username, report_date DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS system_heartbeat (
            id SERIAL PRIMARY KEY, component TEXT NOT NULL,
            last_seen_at TIMESTAMP DEFAULT NOW(),
            status TEXT DEFAULT 'ok', details TEXT,
            UNIQUE(component)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_heartbeat_component ON system_heartbeat (component, last_seen_at DESC)")

    conn.commit()
    conn.close()

    # ─── MIGRATIONS IDEMPOTENTES ───
    # Définies dans app/database_migrations.py — ajouter les nouvelles là-bas.
    from app.database_migrations import MIGRATIONS
    conn = get_pg_conn()
    c = conn.cursor()
    for m in MIGRATIONS:
        try:
            c.execute(m)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.debug("[Migration] Skip (%s)", str(e)[:60])
    conn.close()
