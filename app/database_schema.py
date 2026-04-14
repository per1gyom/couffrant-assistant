"""
Schéma SQL Raya — toutes les tables CREATE TABLE IF NOT EXISTS.
Extrait de database.py — SPLIT-1.
Importé par init_postgres() dans database.py.
"""


def get_schema_statements() -> list[str]:
    """Retourne la liste ordonnée des CREATE TABLE / CREATE INDEX à exécuter."""
    return [
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            settings JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, email TEXT,
            scope TEXT DEFAULT 'user', tenant_id TEXT DEFAULT 'couffrant_solar',
            last_login TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT false, created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL,
            subscription_id TEXT UNIQUE NOT NULL, resource TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL, client_state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
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
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            user_input TEXT, aria_response TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_style_examples (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            situation TEXT, example_text TEXT, tags TEXT,
            quality_score REAL DEFAULT 1.0, used_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'sent_mail', created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_hot_summary (
            username TEXT PRIMARY KEY, content TEXT, updated_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_contacts (
            id SERIAL PRIMARY KEY, tenant_id TEXT DEFAULT 'couffrant_solar',
            email TEXT, name TEXT, company TEXT, role TEXT, summary TEXT,
            last_seen TEXT, last_subject TEXT, mail_count INTEGER DEFAULT 0,
            tags TEXT, updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(email, tenant_id)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_rules (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            category TEXT DEFAULT 'général', rule TEXT NOT NULL,
            source TEXT DEFAULT 'auto', confidence REAL DEFAULT 0.7,
            reinforcements INTEGER DEFAULT 1, active BOOLEAN DEFAULT true,
            context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_insights (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            topic TEXT, insight TEXT NOT NULL, source TEXT DEFAULT 'conversation',
            reinforcements INTEGER DEFAULT 1, context TEXT DEFAULT 'couffrant_solar',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_session_digests (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            session_date DATE DEFAULT CURRENT_DATE, conversation_count INTEGER,
            summary TEXT, rules_learned JSONB DEFAULT '[]',
            topics JSONB DEFAULT '[]', created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS sent_mail_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            message_id TEXT, sent_at TEXT, to_email TEXT, subject TEXT,
            body_preview TEXT, created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(message_id, username)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_profile (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            profile_type TEXT, content TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY, provider TEXT, username TEXT DEFAULT 'guillaume',
            access_token TEXT, refresh_token TEXT, expires_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(provider, username)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS user_tools (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tool TEXT NOT NULL,
            access_level TEXT DEFAULT 'read_only', enabled BOOLEAN DEFAULT true,
            config JSONB DEFAULT '{}', created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(), UNIQUE(username, tool)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS reply_learning_memory (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            mail_subject TEXT, mail_from TEXT, mail_body_preview TEXT,
            category TEXT, ai_reply TEXT, final_reply TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS global_instructions (
            id SERIAL PRIMARY KEY, tenant_id TEXT DEFAULT 'couffrant_solar',
            instruction TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            id SERIAL PRIMARY KEY, username TEXT DEFAULT 'guillaume',
            email TEXT, access_token TEXT, refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW(), UNIQUE(username)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS teams_sync_state (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, chat_id TEXT NOT NULL,
            chat_type TEXT DEFAULT 'chat', chat_label TEXT,
            last_message_id TEXT, last_synced_at TIMESTAMP DEFAULT NOW(),
            notes TEXT, UNIQUE(username, chat_id)
        )
    """,
        """
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
    """,
        """
        CREATE TABLE IF NOT EXISTS llm_usage (
            id SERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, username TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd_estimate NUMERIC(10, 6), purpose TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
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
    """,
        """
        CREATE TABLE IF NOT EXISTS user_tenant_access (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(username, tenant_id),
            CONSTRAINT uta_role_check CHECK (role IN ('owner', 'admin', 'user'))
        )
    """,
        """
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
    """,
        """
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
    """,
        """
        CREATE TABLE IF NOT EXISTS aria_rules_history (
            id SERIAL PRIMARY KEY, rule_id INTEGER NOT NULL,
            username TEXT NOT NULL, tenant_id TEXT, category TEXT, rule TEXT NOT NULL,
            confidence REAL, reinforcements INTEGER, active BOOLEAN,
            change_type TEXT NOT NULL, changed_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT change_type_check CHECK (
                change_type IN ('created', 'updated', 'reinforced', 'deactivated', 'rollback')
            )
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            action_type TEXT NOT NULL, action_target TEXT, action_detail TEXT,
            source TEXT DEFAULT 'raya', created_at TIMESTAMP DEFAULT NOW()
        )
    """,
        """
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
    """,
        """
        CREATE TABLE IF NOT EXISTS daily_reports (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL, tenant_id TEXT,
            report_date DATE DEFAULT CURRENT_DATE, content TEXT NOT NULL,
            sections JSONB DEFAULT '[]', delivered BOOLEAN DEFAULT false,
            delivered_via TEXT, delivered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(), UNIQUE(username, report_date)
        )
    """,
        """
        CREATE TABLE IF NOT EXISTS system_heartbeat (
            id SERIAL PRIMARY KEY, component TEXT NOT NULL,
            last_seen_at TIMESTAMP DEFAULT NOW(),
            status TEXT DEFAULT 'ok', details TEXT,
            UNIQUE(component)
        )
    """,
    ]
