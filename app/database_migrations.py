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
    # -- CLOISONNEMENT DRIVE --
    """UPDATE tenants SET settings = settings || '{"sharepoint_site": "Commun"}'::jsonb
       WHERE id = 'couffrant_solar' AND NOT (settings ? 'sharepoint_site')""",
    # -- SUSPENSION --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended_reason TEXT",
    # -- Connecteurs V2 --
    """CREATE TABLE IF NOT EXISTS tenant_connections (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        tool_type TEXT NOT NULL, label TEXT NOT NULL,
        auth_type TEXT NOT NULL DEFAULT 'manual',
        credentials JSONB DEFAULT '{}', config JSONB DEFAULT '{}',
        status TEXT DEFAULT 'not_configured', created_by TEXT,
        created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS connection_assignments (
        id SERIAL PRIMARY KEY,
        connection_id INTEGER NOT NULL REFERENCES tenant_connections(id) ON DELETE CASCADE,
        username TEXT NOT NULL, access_level TEXT NOT NULL DEFAULT 'read_only',
        enabled BOOLEAN DEFAULT TRUE, UNIQUE(connection_id, username)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tc_tenant ON tenant_connections(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_ca_username ON connection_assignments(username)",
    # -- DISPLAY NAME : nom d'affichage personnalise --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT",
    # -- SUPPRESSION COMPTE : workflow validation admin --
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMP DEFAULT NULL",
    # -- Ajouter les nouvelles migrations sous cette ligne --
    # -- SIGNATURES v2 : nom + multi-boites + defaut --
    "ALTER TABLE email_signatures ADD COLUMN IF NOT EXISTS name TEXT",
    "ALTER TABLE email_signatures ADD COLUMN IF NOT EXISTS apply_to_emails TEXT[] DEFAULT '{}'",
    "ALTER TABLE email_signatures ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT false",
    "ALTER TABLE email_signatures ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
    # -- CONNECTEURS V2 : email + oauth_state sur tenant_connections --
    "ALTER TABLE tenant_connections ADD COLUMN IF NOT EXISTS connected_email TEXT",
    "ALTER TABLE tenant_connections ADD COLUMN IF NOT EXISTS oauth_state TEXT",
    # -- PENDING_ACTIONS : conversation_id (lien avec aria_memory) --
    "ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS conversation_id INTEGER",
    # -- GMAIL_TOKENS : colonne email pour affichage bandeau --
    "ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS email TEXT",
    # -- PERFORMANCE : index manquants identifiés par audit --
    # aria_memory : tri par id DESC pour l'historique (croît avec le temps)
    "CREATE INDEX IF NOT EXISTS idx_aria_memory_username_id ON aria_memory (username, id DESC)",
    # pending_actions : filtre status + expiry le plus fréquent
    "CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions (username, tenant_id, status, expires_at)",
    # llm_usage : filtre par date pour l'onglet Utilisation
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage (created_at DESC, tenant_id)",
    # aria_rules : filtre active + category (les 2 champs absents de l'index existant)
    "CREATE INDEX IF NOT EXISTS idx_aria_rules_active_cat ON aria_rules (username, active, category, confidence DESC)",
    # -- SOFT-DELETE synthèse : colonne archived sur aria_memory --
    "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT false",
    "CREATE INDEX IF NOT EXISTS idx_aria_memory_archived ON aria_memory (username, archived) WHERE archived = false",
    # -- AUTO-DÉCOUVERTE : connaissance vectorisée des outils connectés --
    """CREATE TABLE IF NOT EXISTS tool_schemas (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        connection_id INTEGER,
        tool_type TEXT NOT NULL,
        schema_type TEXT NOT NULL DEFAULT 'model',
        entity_key TEXT NOT NULL,
        display_name TEXT,
        description TEXT NOT NULL,
        fields_json JSONB DEFAULT '{}',
        relationships_json JSONB DEFAULT '[]',
        embedding vector(1536),
        discovered_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, tool_type, entity_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tool_schemas_embedding ON tool_schemas USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_tool_schemas_tenant ON tool_schemas (tenant_id, tool_type)",
    # -- GRAPHE DE RELATIONS : liens cross-source entre entités --
    """CREATE TABLE IF NOT EXISTS entity_links (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_key TEXT NOT NULL,
        entity_name TEXT,
        resource_type TEXT NOT NULL,
        resource_id TEXT,
        resource_source TEXT NOT NULL,
        resource_label TEXT,
        resource_data JSONB DEFAULT '{}',
        linked_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, entity_key, resource_source, resource_type, resource_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_entity_links_lookup ON entity_links (tenant_id, entity_key)",
    "CREATE INDEX IF NOT EXISTS idx_entity_links_resource ON entity_links (tenant_id, resource_source, resource_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_links_type ON entity_links (tenant_id, entity_type)",
    # -- GRAPHE SEMANTIQUE TYPE : noeuds + aretes typees avec confidence (v1.0 18/04/2026) --
    # Voir docs/raya_memory_architecture.md couche 2.
    # Table unifiee (pas par source) pour permettre traversee multi-hop cross-sources.
    """CREATE TABLE IF NOT EXISTS semantic_graph_nodes (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        node_key TEXT NOT NULL,
        node_label TEXT,
        node_properties JSONB DEFAULT '{}',
        source TEXT NOT NULL,
        source_record_id TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, node_type, node_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sg_nodes_lookup ON semantic_graph_nodes (tenant_id, node_type, node_key)",
    "CREATE INDEX IF NOT EXISTS idx_sg_nodes_source ON semantic_graph_nodes (tenant_id, source, source_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_sg_nodes_label ON semantic_graph_nodes (tenant_id, node_label)",
    """CREATE TABLE IF NOT EXISTS semantic_graph_edges (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        edge_from INT NOT NULL REFERENCES semantic_graph_nodes(id) ON DELETE CASCADE,
        edge_to INT NOT NULL REFERENCES semantic_graph_nodes(id) ON DELETE CASCADE,
        edge_type TEXT NOT NULL,
        edge_confidence REAL DEFAULT 1.0,
        edge_source TEXT NOT NULL DEFAULT 'explicit_source',
        edge_metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, edge_from, edge_to, edge_type)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sg_edges_from ON semantic_graph_edges (tenant_id, edge_from, edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_sg_edges_to ON semantic_graph_edges (tenant_id, edge_to, edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_sg_edges_type ON semantic_graph_edges (tenant_id, edge_type, edge_confidence)",
    # -- VECTORISATION SEMANTIQUE ODOO (v1.0 18/04/2026) --
    # Voir docs/raya_memory_architecture.md couche 3.
    # Table unique pour tous les types de contenu Odoo (sale.order, sale.order.line,
    # crm.lead, calendar.event, project.task, res.partner.comment, etc.). Permet
    # la recherche hybrid dense+sparse sur TOUT le contenu Odoo en une seule requete.
    """CREATE TABLE IF NOT EXISTS odoo_semantic_content (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        source_model TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        content_type TEXT NOT NULL,
        text_content TEXT NOT NULL,
        embedding vector(1536),
        content_tsv tsvector,
        related_partner_id TEXT,
        metadata JSONB DEFAULT '{}',
        odoo_write_date TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, source_model, source_record_id, content_type)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_odoo_sem_embedding ON odoo_semantic_content USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_odoo_sem_tsv ON odoo_semantic_content USING gin (content_tsv)",
    "CREATE INDEX IF NOT EXISTS idx_odoo_sem_tenant_model ON odoo_semantic_content (tenant_id, source_model)",
    "CREATE INDEX IF NOT EXISTS idx_odoo_sem_partner ON odoo_semantic_content (tenant_id, related_partner_id)",
    "CREATE INDEX IF NOT EXISTS idx_odoo_sem_write_date ON odoo_semantic_content (tenant_id, source_model, odoo_write_date)",
    # -- ALERTES SYSTEME (v1.0 18/04/2026) --
    # Voir docs/raya_memory_architecture.md. Table generique pour toutes les
    # alertes systeme remontees a l'admin : limites approchees, erreurs
    # recurrentes, modules Odoo manquants, quotas API atteints, etc.
    """CREATE TABLE IF NOT EXISTS system_alerts (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'warning',
        component TEXT NOT NULL,
        message TEXT NOT NULL,
        details JSONB DEFAULT '{}',
        acknowledged BOOLEAN DEFAULT FALSE,
        acknowledged_by TEXT,
        acknowledged_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, alert_type, component)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_alerts_active ON system_alerts (tenant_id, acknowledged, severity)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_component ON system_alerts (tenant_id, component, alert_type)",
    # -- SCANNER UNIVERSEL PHASE 1 FONDATIONS (v1.0 18/04/2026) --
    # Voir docs/raya_scanner_universel_plan.md Section 4 & 5 Phase 1.
    # Table scanner_runs : trace chaque execution du scanner (init, delta,
    # rebuild, audit) avec checkpointing pour reprise apres interruption.
    """CREATE TABLE IF NOT EXISTS scanner_runs (
        id SERIAL PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        tenant_id TEXT NOT NULL,
        source TEXT NOT NULL,
        run_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        started_at TIMESTAMP DEFAULT NOW(),
        finished_at TIMESTAMP,
        params JSONB DEFAULT '{}',
        progress JSONB DEFAULT '{}',
        stats JSONB DEFAULT '{}',
        error TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_scanner_runs_tenant_status ON scanner_runs (tenant_id, status, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_scanner_runs_source ON scanner_runs (tenant_id, source, started_at DESC)",
    # Flag stop_requested : permet a l admin de demander l arret propre d un run
    # en cours via le bouton Stop du panel. Le worker verifie ce flag apres
    # chaque modele termine (option A : laisser finir le modele en cours).
    "ALTER TABLE scanner_runs ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN DEFAULT FALSE",
    # Table connector_schemas : manifest de vectorisation par modele et par
    # source. JSON decrit quels champs vectoriser, quelles aretes creer, etc.
    # Genere automatiquement par introspection, editable via panel admin.
    """CREATE TABLE IF NOT EXISTS connector_schemas (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        source TEXT NOT NULL,
        model_name TEXT NOT NULL,
        priority INT NOT NULL DEFAULT 3,
        enabled BOOLEAN DEFAULT TRUE,
        manifest JSONB NOT NULL,
        last_scanned_at TIMESTAMP,
        records_count_odoo INT,
        records_count_raya INT,
        integrity_pct FLOAT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, source, model_name)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_schemas_enabled ON connector_schemas (tenant_id, source, enabled, priority)",
    # Table vectorization_queue : queue des records a (re)vectoriser suite aux
    # webhooks ou au delta incremental. Un worker depile toutes les 5s et
    # traite un record a la fois avec idempotence (INSERT ON CONFLICT).
    """CREATE TABLE IF NOT EXISTS vectorization_queue (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        source TEXT NOT NULL,
        model_name TEXT NOT NULL,
        record_id INT NOT NULL,
        action TEXT NOT NULL DEFAULT 'upsert',
        priority INT DEFAULT 5,
        attempts INT DEFAULT 0,
        last_error TEXT,
        scheduled_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        source_info JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_queue_pending ON vectorization_queue (tenant_id, completed_at, scheduled_at) WHERE completed_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_queue_record ON vectorization_queue (tenant_id, source, model_name, record_id)",
    # Anti-rejeu des webhooks (Q6 valide 19/04/2026) : chaque webhook entrant
    # est signe par un identifiant unique (nonce) genere cote Odoo. Raya
    # rejette tout webhook dont le nonce a deja ete vu pour ce tenant.
    # L index UNIQUE partiel permet un rejet en O(log n).
    "ALTER TABLE vectorization_queue ADD COLUMN IF NOT EXISTS nonce TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_nonce ON vectorization_queue (tenant_id, nonce) WHERE nonce IS NOT NULL",
    # Soft delete sur semantic_graph_nodes (Q7=A : tracabilite totale).
    # Quand un record Odoo est supprime, on marque deleted_at mais on garde
    # le noeud et ses aretes. Les recherches filtrent sur deleted_at IS NULL.
    "ALTER TABLE semantic_graph_nodes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "ALTER TABLE semantic_graph_edges ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "ALTER TABLE odoo_semantic_content ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS idx_sg_nodes_active ON semantic_graph_nodes (tenant_id, node_type) WHERE deleted_at IS NULL",
    # -- Phase Permissions tenant Read/Write/Delete (18/04/2026 soir) --
    # Plan : docs/raya_permissions_plan.md
    # Hierarchie : super_admin > tenant_admin > user (v2)
    # En v1 : super_admin_permission_level plafonne tenant_admin_permission_level
    "ALTER TABLE tenant_connections ADD COLUMN IF NOT EXISTS super_admin_permission_level TEXT DEFAULT 'read_write_delete'",
    "ALTER TABLE tenant_connections ADD COLUMN IF NOT EXISTS tenant_admin_permission_level TEXT DEFAULT 'read'",
    "ALTER TABLE tenant_connections ADD COLUMN IF NOT EXISTS previous_permission_level TEXT",
    # Contrainte soft : valeur autorisee
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tenant_connections_super_admin_perm_check') THEN
            ALTER TABLE tenant_connections ADD CONSTRAINT tenant_connections_super_admin_perm_check
                CHECK (super_admin_permission_level IN ('read', 'read_write', 'read_write_delete'));
        END IF;
    END $$""",
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tenant_connections_tenant_admin_perm_check') THEN
            ALTER TABLE tenant_connections ADD CONSTRAINT tenant_connections_tenant_admin_perm_check
                CHECK (tenant_admin_permission_level IN ('read', 'read_write', 'read_write_delete'));
        END IF;
    END $$""",
    # Table d audit : log chaque tentative d action avec resultat (allowed/denied)
    """CREATE TABLE IF NOT EXISTS permission_audit_log (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        username TEXT NOT NULL,
        connection_id INTEGER,
        action_tag TEXT NOT NULL,
        current_permission_level TEXT NOT NULL,
        required_permission_level TEXT NOT NULL,
        allowed BOOLEAN NOT NULL,
        user_input_excerpt TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_perm_audit_tenant ON permission_audit_log (tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_perm_audit_denied ON permission_audit_log (tenant_id, created_at DESC) WHERE allowed = FALSE",
    # -- Phase D Drive SharePoint (20/04/2026) --
    # Voir docs/audit_drive_sharepoint_20avril.md et
    # docs/raya_principe_memoire_3_niveaux.md
    # Permet aux webhooks et au scan Drive d utiliser des identifiants
    # externes non-numeriques (file_id SharePoint type '01ABCD...')
    "ALTER TABLE vectorization_queue ADD COLUMN IF NOT EXISTS record_external_id TEXT",
    "ALTER TABLE vectorization_queue ALTER COLUMN record_id DROP NOT NULL",
    # Liste des dossiers Drive surveilles par tenant. Chaque dossier peut
    # etre scanne initialement et surveille en temps-reel via webhook.
    """CREATE TABLE IF NOT EXISTS drive_folders (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'sharepoint',
        folder_name TEXT NOT NULL,
        site_name TEXT,
        drive_id TEXT,
        folder_id TEXT,
        folder_path TEXT,
        enabled BOOLEAN DEFAULT TRUE,
        last_full_scan_at TIMESTAMP,
        last_scan_stats JSONB DEFAULT '{}',
        subscription_id TEXT,
        subscription_expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, provider, folder_name)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_drive_folders_enabled ON drive_folders (tenant_id, enabled)",
    # Table de stockage du contenu vectorise Drive.
    # Applique le principe universel memoire 3 niveaux :
    #   level = 1 : resume meta (1 phrase, toujours stocke, tres leger)
    #   level = 2 : detail vectorise (chunks de contenu pour recherche precise)
    # Le niveau 3 (re-fetch live) ne necessite pas de stockage - utilise
    # directement l API Drive au moment de la question.
    """CREATE TABLE IF NOT EXISTS drive_semantic_content (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        folder_id INT,
        file_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT,
        web_url TEXT,
        mime_type TEXT,
        file_ext TEXT,
        file_size_bytes BIGINT,
        level INT NOT NULL DEFAULT 1,
        chunk_index INT DEFAULT 0,
        content_type TEXT NOT NULL DEFAULT 'document',
        text_content TEXT NOT NULL,
        embedding vector(1536),
        content_tsv tsvector,
        metadata JSONB DEFAULT '{}',
        drive_modified_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        deleted_at TIMESTAMP,
        UNIQUE (tenant_id, file_id, level, chunk_index)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_drive_sem_embedding ON drive_semantic_content USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_drive_sem_tsv ON drive_semantic_content USING gin (content_tsv)",
    "CREATE INDEX IF NOT EXISTS idx_drive_sem_tenant_level ON drive_semantic_content (tenant_id, level) WHERE deleted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_drive_sem_file ON drive_semantic_content (tenant_id, file_id) WHERE deleted_at IS NULL",
    # -- Phase Dashboards Nettoyes (20/04/2026) --
    # Voir docs/raya_principe_memoire_3_niveaux.md pour la philosophie.
    # Permet de classifier les erreurs en :
    #   - reelles (a investiguer)
    #   - fantomes (sur modele desactive, sans impact)
    #   - suspens connus (droits Odoo manquants, documentes)
    # Affiche un verdict clair au lieu d'alarmer le super-admin non-dev.
    """CREATE TABLE IF NOT EXISTS deactivated_models (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        model_name TEXT NOT NULL,
        reason TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'deactivated',
        doc_link TEXT,
        deactivated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (source, model_name)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_deact_models_source ON deactivated_models (source)",
    # Seed initial : modeles desactives connus au 20/04/2026.
    # Les ON CONFLICT DO NOTHING permettent d ajouter des seeds sans
    # ecraser des modifs manuelles futures.
    """INSERT INTO deactivated_models (source, model_name, reason, category, doc_link) VALUES
        ('odoo', 'of.survey.answers',
         'Manifest reference le champ name qui n existe pas sur ce modele chez Couffrant',
         'deactivated', 'docs/raya_scanner_suspens.md'),
        ('odoo', 'of.survey.user_input.line',
         'Manifest reference le champ name qui n existe pas sur ce modele chez Couffrant',
         'deactivated', 'docs/raya_scanner_suspens.md'),
        ('odoo', 'mail.message',
         'Droits Odoo - le user API ne voit que ses propres messages. En attente ouverture droits chez OpenFire',
         'pending_rights', 'docs/demande_openfire_droits_produits_lignes.md'),
        ('odoo', 'account.payment.line',
         'Droit Extra Rights/Accounting/Payments manquant. En attente ouverture chez OpenFire',
         'pending_rights', 'docs/demande_openfire_droits_produits_lignes.md'),
        ('odoo', 'stock.valuation.layer',
         'Droit Inventory/Administrator manquant. Pas utilise metier = pas de resolution prevue',
         'ignored', 'docs/raya_scanner_suspens.md')
       ON CONFLICT (source, model_name) DO NOTHING""",
    # -- Phase Continuation P2/P3 (22/04/2026 aprem) --
    # Permet a Raya de sauvegarder son etat (messages, tokens, iterations)
    # quand un garde-fou saute (P1 atteint), pour reprise par clic 'Etendre'
    # cote utilisateur. Pas de redemarrage : vraie continuation depuis
    # l etat precedent. TTL 1h (pas d interet a reprendre plus tard).
    #
    # Paliers :
    #   P1=150k (defaut) -> si garde-fou, on sauvegarde
    #   P2=300k (+150k)  -> 1ere extension
    #   P3+=+200k par clic (repetable a l infini, user decide)
    #
    # extension_count :
    #   0 = reponse P1 sauvegardee, pas encore d extension
    #   1 = 1ere extension faite (on est en P2)
    #   2+ = extensions P3+ successives
    #
    # palier :
    #   CHECK contrainte garde-fou : valeurs connues seulement.
    """CREATE TABLE IF NOT EXISTS agent_continuations (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        messages JSONB NOT NULL,
        tools_snapshot JSONB,
        tokens_used INTEGER NOT NULL DEFAULT 0,
        iterations_used INTEGER NOT NULL DEFAULT 0,
        duration_seconds REAL NOT NULL DEFAULT 0,
        extension_count INTEGER NOT NULL DEFAULT 0,
        palier TEXT NOT NULL DEFAULT 'P1',
        stopped_by TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '1 hour'),
        consumed BOOLEAN NOT NULL DEFAULT false,
        CONSTRAINT agent_cont_palier_check CHECK (palier IN ('P1','P2','P3'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agent_cont_user ON agent_continuations (username, tenant_id, expires_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agent_cont_cleanup ON agent_continuations (expires_at) WHERE consumed = false",
]
