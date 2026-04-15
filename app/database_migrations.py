"""
Liste ordonnee des migrations SQL idempotentes pour Raya.
Ajouter les nouvelles migrations ICI UNIQUEMENT — ne pas editer database.py.
Chaque migration est executee une par une via init_postgres().

Convention :
  - Toujours idempotente (IF NOT EXISTS, ON CONFLICT DO NOTHING, etc.)
  - Une migration = une action atomique
  - Regrouper les migrations par phase avec un commentaire # -- Phase X --
"""

MIGRATIONS = [
    # -- Migrations historiques --
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
    ("INSERT INTO tenants (id, name, settings) "
     "VALUES ('couffrant_solar', 'Couffrant Solar', "
     "'{\"email_provider\": \"microsoft\", \"sharepoint_folder\": \"1_Photovolta\u00efque\"}') "
     "ON CONFLICT (id) DO NOTHING"),
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
    ("INSERT INTO oauth_tokens (provider, username, access_token, refresh_token, expires_at)\n"
     "   SELECT 'google', g.username, g.access_token, g.refresh_token,\n"
     "          NOW() + INTERVAL '1 hour'\n"
     "   FROM gmail_tokens g\n"
     "   WHERE g.access_token IS NOT NULL\n"
     "     AND NOT EXISTS (\n"
     "       SELECT 1 FROM oauth_tokens o\n"
     "       WHERE o.provider='google' AND o.username=g.username\n"
     "     )"),
    # -- Phase 2 : tenant_id sur toutes les tables --
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
    # -- Phase 3a : vectorisation des regles pour RAG --
    "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS embedding vector(1536)",
    "CREATE INDEX IF NOT EXISTS idx_rules_embedding ON aria_rules USING hnsw (embedding vector_cosine_ops)",
    "ALTER TABLE aria_hot_summary ADD COLUMN IF NOT EXISTS embedding vector(1536)",
    # -- 5D-1 : peuplement user_tenant_access --
    ("INSERT INTO user_tenant_access (username, tenant_id, role) "
     "SELECT username, tenant_id, "
     "CASE WHEN scope = 'super_admin' THEN 'owner' WHEN scope = 'admin' THEN 'admin' ELSE 'user' END "
     "FROM users WHERE tenant_id IS NOT NULL ON CONFLICT (username, tenant_id) DO NOTHING"),
    # -- 7-10 : shadow mode --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS shadow_mode BOOLEAN DEFAULT true",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS shadow_mode_until TIMESTAMP DEFAULT (NOW() + INTERVAL '14 days')",
    # -- 7-5 : preferences de notification --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{}'",
    # -- 7-1a : Gmail OAuth2 --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_credentials JSONB DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_last_history_id TEXT DEFAULT NULL",
    # -- FIX-JARVIS --
    "UPDATE aria_rules SET rule = REPLACE(rule, 'Jarvis', 'Raya') WHERE rule ILIKE '%jarvis%'",
    "UPDATE aria_rules SET rule = REPLACE(rule, 'jarvis', 'Raya') WHERE rule ILIKE '%jarvis%'",
    "UPDATE aria_insights SET insight = REPLACE(insight, 'Jarvis', 'Raya') WHERE insight ILIKE '%jarvis%'",
    "UPDATE aria_insights SET insight = REPLACE(insight, 'jarvis', 'Raya') WHERE insight ILIKE '%jarvis%'",
    "UPDATE aria_patterns SET description = REPLACE(description, 'Jarvis', 'Raya') WHERE description ILIKE '%jarvis%'",
    "UPDATE aria_hot_summary SET content = REPLACE(content, 'Jarvis', 'Raya') WHERE content ILIKE '%jarvis%'",
    "UPDATE aria_hot_summary SET content = REPLACE(content, 'jarvis', 'Raya') WHERE content ILIKE '%jarvis%'",
    "UPDATE dossier_narratives SET narrative = REPLACE(narrative, 'Jarvis', 'Raya') WHERE narrative ILIKE '%jarvis%'",
    # -- HOTFIX-GMAIL-TOKENS --
    "ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
    # -- USER-PHONE --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
    # -- P1-1 : Bug reports SAV provisoire --
    """CREATE TABLE IF NOT EXISTS bug_reports (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'couffrant_solar',
    report_type TEXT NOT NULL CHECK (report_type IN ('bug', 'amelioration')),
    description TEXT NOT NULL,
    aria_memory_id INTEGER,
    user_input TEXT,
    raya_response TEXT,
    device_info TEXT,
    status TEXT NOT NULL DEFAULT 'nouveau' CHECK (status IN ('nouveau', 'en_cours', 'resolu', 'rejete')),
    created_at TIMESTAMP DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_bug_reports_status ON bug_reports (status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bug_reports_user ON bug_reports (username, created_at DESC)",
    # -- B3 : Signatures email dynamiques --
    """CREATE TABLE IF NOT EXISTS email_signatures (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'couffrant_solar',
    email_address TEXT,
    signature_html TEXT NOT NULL,
    extracted_from TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(username, email_address)
)""",
    # -- TOPICS : sujets utilisateur --
    """CREATE TABLE IF NOT EXISTS user_topics (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'couffrant_solar',
    title TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_user_topics_user ON user_topics (username, status, updated_at DESC)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'",
    # -- CLOISONNEMENT DRIVE : ajouter sharepoint_site au tenant couffrant_solar --
    """UPDATE tenants SET settings = settings || '{"sharepoint_site": "Commun"}'::jsonb
       WHERE id = 'couffrant_solar' AND NOT (settings ? 'sharepoint_site')""",
    # -- SUSPENSION : colonnes pour suspendre utilisateurs et tenants --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended_reason TEXT",
    # -- Ajouter les nouvelles migrations sous cette ligne --
]
