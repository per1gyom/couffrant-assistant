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
    # -- SIGNATURES v3 : defaut PAR BOITE MAIL (avril 2026) --
    # Une signature peut etre 'par defaut' pour plusieurs boites mail differentes.
    # Ex: signature_id=42 -> default_for_emails=['guillaume@couffrant-solar.fr'] => Raya l'utilise auto pour cette boite
    # Remplace progressivement is_default (qui etait global, devient deprecie).
    "ALTER TABLE email_signatures ADD COLUMN IF NOT EXISTS default_for_emails TEXT[] DEFAULT '{}'",
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
    # -- AUDIT-ISOLATION-24AVRIL : ajout tenant_id aux 4 tables restantes --
    # Ces tables n avaient pas de tenant_id alors qu elles contiennent des
    # donnees utilisateur. Ajoute pour eviter toute fuite cross-tenant future.
    "ALTER TABLE gmail_tokens           ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "ALTER TABLE user_tools             ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "ALTER TABLE connection_assignments ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "ALTER TABLE webhook_subscriptions  ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    # Backfill depuis users.tenant_id via username
    "UPDATE gmail_tokens           a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
    "UPDATE user_tools             a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
    "UPDATE connection_assignments a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
    "UPDATE webhook_subscriptions  a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL",
    # Fallback pour anciennes donnees orphelines
    "UPDATE gmail_tokens           SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
    "UPDATE user_tools             SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
    "UPDATE connection_assignments SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
    "UPDATE webhook_subscriptions  SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",
    # Index pour performances des filtres (username, tenant_id)
    "CREATE INDEX IF NOT EXISTS idx_gmail_tokens_tenant_user        ON gmail_tokens (tenant_id, username)",
    "CREATE INDEX IF NOT EXISTS idx_user_tools_tenant_user          ON user_tools (tenant_id, username)",
    "CREATE INDEX IF NOT EXISTS idx_conn_assignments_tenant_user    ON connection_assignments (tenant_id, username)",
    "CREATE INDEX IF NOT EXISTS idx_webhook_subs_tenant_user        ON webhook_subscriptions (tenant_id, username)",
    # -- SYSTEME DE REGLES V2 (25 avril 2026) : niveaux + nettoyage doublons --
    # 1. Ajout du niveau de regle (immuable / moyenne / faible)
    "ALTER TABLE aria_rules ADD COLUMN IF NOT EXISTS level TEXT DEFAULT 'moyenne'",
    "UPDATE aria_rules SET level = 'moyenne' WHERE level IS NULL",
    # 2. Journal des optimisations hebdo
    """CREATE TABLE IF NOT EXISTS rules_optimization_log (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        run_at TIMESTAMP DEFAULT NOW(),
        run_type TEXT NOT NULL DEFAULT 'weekly',
        rules_before INT NOT NULL DEFAULT 0,
        rules_after INT NOT NULL DEFAULT 0,
        merged_count INT NOT NULL DEFAULT 0,
        contradictions_resolved INT NOT NULL DEFAULT 0,
        contradictions_pending INT NOT NULL DEFAULT 0,
        forgotten_count INT NOT NULL DEFAULT 0,
        summary_text TEXT,
        details_json JSONB DEFAULT '{}'::jsonb,
        tokens_used INT DEFAULT 0,
        duration_seconds REAL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_rules_optim_user ON rules_optimization_log (username, tenant_id, run_at DESC)",
    # 3. Table des contradictions en attente de decision utilisateur
    """CREATE TABLE IF NOT EXISTS rules_pending_decisions (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        decision_type TEXT NOT NULL,
        rule_ids INT[] NOT NULL,
        context_text TEXT,
        question_text TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        resolved_at TIMESTAMP,
        resolved_by TEXT,
        resolution TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_rules_pending_user ON rules_pending_decisions (username, tenant_id, status, created_at DESC)",
    # 4. Nettoyage one-shot des 11 doublons avec/sans accents
    # Snapshot dans history avant archivage
    """INSERT INTO aria_rules_history
       (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active,
              'merged_duplicate_accents_24avril'
       FROM aria_rules
       WHERE id BETWEEN 43 AND 53
         AND active = true
         AND NOT EXISTS (
           SELECT 1 FROM aria_rules_history h
           WHERE h.rule_id = aria_rules.id
             AND h.change_type = 'merged_duplicate_accents_24avril'
         )""",
    # Archivage des losers (43-53)
    "UPDATE aria_rules SET active = false, source = 'merged_duplicate_accents', updated_at = NOW() WHERE id BETWEEN 43 AND 53 AND active = true",
    # Bonus renforcement sur les winners (166-176)
    "UPDATE aria_rules SET reinforcements = reinforcements + 1, updated_at = NOW() WHERE id BETWEEN 166 AND 176 AND active = true",
    # -- FUSION MANUELLE PAIRE COSINE 130/134 (25 avril 2026) --
    # Detectee par le preview du rules_optimizer : similarite 0.9622
    # Meme contenu (Pierre Couffrant associe/chef equipe), la 134 a juste un prefixe [equipe]
    # Winner = 130 (conf 0.7 > 0.5), loser = 134 (conf 0.5)
    # Snapshot avant fusion (idempotent via NOT EXISTS)
    """INSERT INTO aria_rules_history
       (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'merged_preview_pierre'
       FROM aria_rules
       WHERE id IN (130, 134) AND active = true
         AND NOT EXISTS (
           SELECT 1 FROM aria_rules_history h
           WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_preview_pierre'
         )""",
    # Winner 130 : confidence = max(0.7, 0.5) + 0.03 = 0.73, reinforcements += 1 (du loser), updated_at
    "UPDATE aria_rules SET confidence = LEAST(1.0, 0.73), reinforcements = reinforcements + 1, updated_at = NOW() WHERE id = 130 AND active = true AND confidence < 0.73",
    # Loser 134 : active=false avec tracabilite
    "UPDATE aria_rules SET active = false, source = 'merged_into_130', updated_at = NOW() WHERE id = 134 AND active = true",
    # -- APPLICATION RUN #2 AGENT (25 avril 2026) : Option B validee par Guillaume --
    # Issue du preview Raya auto-reflexive mode agent :
    #   4 suppressions + 2 simplifications + 5 nouvelles regles + 1 pending
    # Faux positifs ignores : 7 fusions (trop risquees) + 2 contradictions (redondantes)
    #
    # Snapshot des regles supprimees/modifiees avant changement (idempotent)
    """INSERT INTO aria_rules_history
       (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'run2_agent_applied'
       FROM aria_rules
       WHERE id IN (10, 28, 31, 83, 11, 67) AND active = true
         AND NOT EXISTS (
           SELECT 1 FROM aria_rules_history h
           WHERE h.rule_id = aria_rules.id AND h.change_type = 'run2_agent_applied'
         )""",
    # 4 SUPPRESSIONS (active=false, tracabilite)
    "UPDATE aria_rules SET active = false, source = 'deprecated_run2_agent', updated_at = NOW() WHERE id = 83 AND active = true",
    "UPDATE aria_rules SET active = false, source = 'redundant_with_57', updated_at = NOW() WHERE id = 31 AND active = true",
    "UPDATE aria_rules SET active = false, source = 'redundant_with_71_76', updated_at = NOW() WHERE id = 10 AND active = true",
    "UPDATE aria_rules SET active = false, source = 'redundant_with_68', updated_at = NOW() WHERE id = 28 AND active = true",
    # 2 SIMPLIFICATIONS (reecriture du texte)
    """UPDATE aria_rules SET
         rule = 'Entités dirigées par Guillaume : SARL Couffrant Solar (activité PV/électricité/couverture), SAS GPLH, SCI Gaucherie, SCI Romagui, + holding en cours de création. Attention orthographe : Couffrant Solar (pas Coupfranc).',
         updated_at = NOW()
       WHERE id = 67 AND rule NOT LIKE '%SARL Couffrant Solar%'""",
    """UPDATE aria_rules SET
         rule = 'Mails envoyés : courts (1 à 3 phrases), directs, sans fioritures. Formule ouverture Bonjour, clôture Merci ou Cordialement selon formalité.',
         updated_at = NOW()
       WHERE id = 11 AND rule NOT LIKE '%ouverture Bonjour%'""",
    # 5 NOUVELLES REGLES (INSERT avec ON CONFLICT DO NOTHING pour idempotence)
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'structures',
         'Orthographe Couffrant Solar : vigilance sur transcription vocale — le nom peut être mal retranscrit en Coupfranc Solar ou variantes phonétiques. Toujours écrire Couffrant Solar.',
         'run2_agent', 0.9, 'moyenne', 1
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE rule LIKE '%vigilance sur transcription vocale%' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'ux',
         'Format de présentation standard validé : 🟢 **texte** en gras pour faire ressortir les résultats clés (fichiers, statuts, confirmations).',
         'run2_agent', 0.8, 'moyenne', 1
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE rule LIKE '%Format de présentation standard validé%' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'Comportement',
         'Guillaume a double casquette (dirigeant utilisateur + super-admin/dev Raya). Identifier la casquette active avant de répondre : contexte métier = ton concis opérationnel ; contexte dev/audit = ton technique transparent sur les limites.',
         'run2_agent', 0.8, 'moyenne', 1
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE rule LIKE '%double casquette%' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'limites',
         'Ne jamais générer de liens cliquables vers Drive/SharePoint : limite technique actuelle. Afficher uniquement 🟢 **nom_fichier.ext**.',
         'run2_agent', 0.8, 'moyenne', 1
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE rule LIKE '%liens cliquables vers Drive%' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'ux',
         'Raccourcis oui/non acceptés : Guillaume préfère répondre oui/non/ok aux propositions. Ne pas exiger de formulation complète.',
         'run2_agent', 0.7, 'moyenne', 1
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE rule LIKE '%Raccourcis oui/non%' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    # 1 QUESTION EN PENDING (Arlene/contact@couffrant-solar.fr)
    """INSERT INTO rules_pending_decisions
         (username, tenant_id, decision_type, rule_ids, question_text, status)
       SELECT 'guillaume', 'couffrant_solar', 'ambiguous_rule',
         ARRAY[17, 15, 124],
         'Règle 17 dit qu''Arlène transfère les mails à Guillaume. Vérification mails : Arlène envoie depuis contact@couffrant-solar.fr (boîte non encore connectée selon règle 124). Une fois contact@ connecté, les règles de tri devront peut-être évoluer. À trancher : garder tel quel, ou adapter la règle 17 ?',
         'pending'
       WHERE NOT EXISTS (SELECT 1 FROM rules_pending_decisions WHERE rule_ids @> ARRAY[17, 15, 124] AND status='pending')""",
    # Log dans rules_optimization_log pour tracabilite
    """INSERT INTO rules_optimization_log
         (username, tenant_id, run_type, rules_before, rules_after,
          merged_count, contradictions_resolved, contradictions_pending,
          forgotten_count, summary_text, details_json, tokens_used, duration_seconds)
       SELECT 'guillaume', 'couffrant_solar', 'manual_run2_agent', 100, 101,
         0, 0, 1, 0,
         'Run #2 agent applied (Option B): 4 supp + 2 simpl + 5 new + 1 pending. 7 fusions skipped (too risky).',
         '{"applied": ["suppressions:83,31,10,28", "simplifications:67,11", "new_rules:5", "pending:17/15/124"], "skipped_fusions": 7}'::jsonb,
         4253, 79
       WHERE NOT EXISTS (SELECT 1 FROM rules_optimization_log WHERE run_type = 'manual_run2_agent' AND username = 'guillaume')""",
    # -- FUSIONS SUPPLEMENTAIRES RUN #2 (25 avril 2026) --
    # Re-analyse apres remarque Guillaume : on etait trop prudents.
    # 5 fusions sures (aucune regle critique conf>=0.9 + user_explicit).
    # 2 fusions gardees en pending (touchent regles 163 user_explicit et 104 seed conf=1.0).
    #
    # FUSION 1 : Archiver/corbeille (IDs 69, 74, 2 -> nouvelle regle)
    """INSERT INTO aria_rules_history
         (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active,
              'merged_run2_fusion_archiver'
       FROM aria_rules
       WHERE id IN (69, 74, 2) AND active = true
         AND NOT EXISTS (SELECT 1 FROM aria_rules_history h WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_run2_fusion_archiver')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'tri-mails',
         'Gestion suppression mails : archiver = déplacer vers dossier Archives. Corbeille = uniquement sur demande explicite ou bruit identifié avec Guillaume. Suppression définitive = jamais.',
         'merged_from_69_74_2', 0.9, 'moyenne', 10
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE source = 'merged_from_69_74_2' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    "UPDATE aria_rules SET active = false, source = 'merged_into_fusion_archiver', updated_at = NOW() WHERE id IN (69, 74, 2) AND active = true",
    # FUSION 2 : Tagger memoire (IDs 9, 18 -> nouvelle regle)
    """INSERT INTO aria_rules_history
         (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'merged_run2_fusion_tagger'
       FROM aria_rules WHERE id IN (9, 18) AND active = true
         AND NOT EXISTS (SELECT 1 FROM aria_rules_history h WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_run2_fusion_tagger')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'Mémoire',
         'Tagger mémoire et apprentissage par entité : [couffrant-solar], [sci-gaucherie], [sci-romagui], [sas-gplh], [holding].',
         'merged_from_9_18', 0.8, 'moyenne', 4
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE source = 'merged_from_9_18' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    "UPDATE aria_rules SET active = false, source = 'merged_into_fusion_tagger', updated_at = NOW() WHERE id IN (9, 18) AND active = true",
    # FUSION 3 : Attestation Consuel (IDs 24, 27, 29 -> nouvelle regle)
    """INSERT INTO aria_rules_history
         (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'merged_run2_fusion_consuel'
       FROM aria_rules WHERE id IN (24, 27, 29) AND active = true
         AND NOT EXISTS (SELECT 1 FROM aria_rules_history h WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_run2_fusion_consuel')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'drive_pv',
         'Attestation Consuel : variantes acceptées = attestation visée, attestation Consuel, Consuel visé. Document délivré par le Consuel après examen du dossier technique SC-144A.',
         'merged_from_24_27_29', 0.8, 'moyenne', 6
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE source = 'merged_from_24_27_29' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    "UPDATE aria_rules SET active = false, source = 'merged_into_fusion_consuel', updated_at = NOW() WHERE id IN (24, 27, 29) AND active = true",
    # FUSION 4 : Transparence limites API (IDs 20, 22, 30 -> nouvelle regle)
    """INSERT INTO aria_rules_history
         (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'merged_run2_fusion_transparence'
       FROM aria_rules WHERE id IN (20, 22, 30) AND active = true
         AND NOT EXISTS (SELECT 1 FROM aria_rules_history h WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_run2_fusion_transparence')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'Comportement',
         'Transparence totale sur les limites techniques : jamais prétendre à un accès sans confirmation technique explicite (API, permissions, génération liens).',
         'merged_from_20_22_30', 0.85, 'moyenne', 6
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE source = 'merged_from_20_22_30' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    "UPDATE aria_rules SET active = false, source = 'merged_into_fusion_transparence', updated_at = NOW() WHERE id IN (20, 22, 30) AND active = true",
    # FUSION 5 : Tri mails priorite (IDs 12, 13, 14, 19 -> nouvelle regle)
    """INSERT INTO aria_rules_history
         (rule_id, username, tenant_id, category, rule, confidence, reinforcements, active, change_type)
       SELECT id, username, tenant_id, category, rule, confidence, reinforcements, active, 'merged_run2_fusion_priorite'
       FROM aria_rules WHERE id IN (12, 13, 14, 19) AND active = true
         AND NOT EXISTS (SELECT 1 FROM aria_rules_history h WHERE h.rule_id = aria_rules.id AND h.change_type = 'merged_run2_fusion_priorite')""",
    """INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, level, reinforcements)
       SELECT 'guillaume', 'couffrant_solar', 'tri-mails',
         'Tri mails priorité : rouge immédiat = Microsoft 365/infra expirée, contrats à signer, alertes sécurité comptes. Orange = rapports SOCOTEC/vérif électrique. Jaune = mails transférés par Arlène. Archiver direct = newsletters Studeria, LinkedIn notifs, pubs.',
         'merged_from_12_13_14_19', 0.85, 'moyenne', 8
       WHERE NOT EXISTS (SELECT 1 FROM aria_rules WHERE source = 'merged_from_12_13_14_19' AND username='guillaume' AND tenant_id='couffrant_solar')""",
    "UPDATE aria_rules SET active = false, source = 'merged_into_fusion_priorite', updated_at = NOW() WHERE id IN (12, 13, 14, 19) AND active = true",
    # 2 FUSIONS GARDEES EN PENDING (touchent regles critiques)
    """INSERT INTO rules_pending_decisions
         (username, tenant_id, decision_type, rule_ids, question_text, status)
       SELECT 'guillaume', 'couffrant_solar', 'fusion_proposal',
         ARRAY[71, 76, 104],
         'Raya propose de fusionner 3 règles sur les actions récupérables (71, 76, 104). Mais la règle 104 est un seed à confidence=1.0 et reinforcements=15 (très critique). Validation nécessaire avant fusion. Nouveau texte proposé : Actions récupérables (corbeille mail) = exécution directe sans confirmation, regrouper si plusieurs items. Confirmation uniquement pour actions irréversibles (envoi mail/Teams, création événement, déplacement/copie Drive).',
         'pending'
       WHERE NOT EXISTS (SELECT 1 FROM rules_pending_decisions WHERE rule_ids @> ARRAY[71, 76, 104] AND status='pending')""",
    """INSERT INTO rules_pending_decisions
         (username, tenant_id, decision_type, rule_ids, question_text, status)
       SELECT 'guillaume', 'couffrant_solar', 'fusion_proposal',
         ARRAY[70, 73, 102, 103, 163],
         'Raya propose de fusionner 5 règles sur les boîtes mail (70, 73, 102, 103, 163). Mais la règle 163 est source user_explicit + confidence=1.0 (critique, ne pas diluer). De plus, la règle perd le provider=outlook important pour le code. Validation nécessaire avant fusion.',
         'pending'
       WHERE NOT EXISTS (SELECT 1 FROM rules_pending_decisions WHERE rule_ids @> ARRAY[70, 73, 102, 103, 163] AND status='pending')""",
    # Log dans rules_optimization_log
    """INSERT INTO rules_optimization_log
         (username, tenant_id, run_type, rules_before, rules_after,
          merged_count, contradictions_resolved, contradictions_pending,
          forgotten_count, summary_text, details_json, tokens_used, duration_seconds)
       SELECT 'guillaume', 'couffrant_solar', 'manual_run2_fusions', 144, 134,
         5, 0, 2, 0,
         'Run #2 fusions sures : 15 regles fusionnees en 5 nouvelles. 2 fusions en pending (critiques).',
         '{"fusions": [[69,74,2],[9,18],[24,27,29],[20,22,30],[12,13,14,19]], "pending": [[71,76,104],[70,73,102,103,163]]}'::jsonb,
         0, 0
       WHERE NOT EXISTS (SELECT 1 FROM rules_optimization_log WHERE run_type = 'manual_run2_fusions' AND username = 'guillaume')""",

    # -- Phase quota & isolation schema (26/04/2026, modele SaaS) --
    # Decision Guillaume 26/04 : modele SaaS avec quota par tenant.
    # Le tenant_admin gere ses users dans la limite du quota fixe par
    # le super_admin a la creation du tenant. Demande de seat
    # supplementaire = acte de facturation (modification quota = super_admin).
    # Voir docs/decision_roles_utilisateurs_a_trancher.md pour le contexte.

    # M-Q01 : ajouter colonne max_users sur tenants
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS max_users INTEGER NOT NULL DEFAULT 1",

    # M-Q02 : backfill des quotas initiaux pour les tenants existants
    # Idempotent : on UPDATE seulement si on est encore sur le default
    # (ne re-ecrase pas un quota deja modifie manuellement)
    "UPDATE tenants SET max_users = 5 WHERE id = 'couffrant_solar' AND max_users = 1",
    "UPDATE tenants SET max_users = 1 WHERE id = 'juillet' AND max_users = 1",

    # M-S01 : users.tenant_id NOT NULL (anti-orphelin)
    # Prerequis verifie le 26/04 : 0 user avec tenant_id NULL
    "ALTER TABLE users ALTER COLUMN tenant_id SET NOT NULL",

    # M-S02 : retirer le default 'couffrant_solar' sur users.tenant_id
    # Force les futurs INSERT a fournir tenant_id explicitement (sinon
    # un user etait silencieusement rattache a couffrant_solar)
    "ALTER TABLE users ALTER COLUMN tenant_id DROP DEFAULT",

    # M-S03 : fix BUG default users.scope = 'couffrant_solar' -> 'user'
    # Avant cette migration, un INSERT sans scope donnait scope = un tenant_id
    # (n'importe quoi). Le default correct pour un nouveau user est 'user'.
    "ALTER TABLE users ALTER COLUMN scope SET DEFAULT 'user'",

    # -- Phase isolation oauth_tokens (26/04, etape A.1) --
    # Probleme identifie : la contrainte UNIQUE (provider, username) etait
    # trop laxe. Si demain Pierre du tenant 'juillet' connecte Outlook alors
    # qu'un Pierre/microsoft de 'couffrant_solar' existe deja, l'INSERT ON
    # CONFLICT ecraserait silencieusement le token de l'autre Pierre.
    # On la remplace par UNIQUE (provider, username, tenant_id).

    # M-O01 : securite defensive avant de mettre tenant_id NOT NULL
    "UPDATE oauth_tokens SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL",

    # M-O02 : tenant_id NOT NULL sur oauth_tokens (anti-orphelin)
    "ALTER TABLE oauth_tokens ALTER COLUMN tenant_id SET NOT NULL",

    # M-O03 : remplacer la contrainte UNIQUE (provider, username) par
    # UNIQUE (provider, username, tenant_id) pour autoriser les homonymes
    # cross-tenant a avoir chacun leur propre token.
    "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_username_unique",
    "ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_provider_username_tenant_unique",
    "ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_provider_username_tenant_unique UNIQUE (provider, username, tenant_id)",

    # -- Phase soft-delete users (26/04/2026, etape B.1a-1) --
    # Decision Guillaume 26/04 : on passe en soft-delete pour permettre
    # de "remplacer" Marc par Sophie en gardant l'historique de Marc
    # accessible. La purge definitive devient un workflow a 2 etapes :
    # tenant_admin demande, super_admin valide.

    # M-D01 : soft-delete (par tenant_admin ou super_admin)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_by TEXT NULL",

    # M-D02 : workflow purge definitive
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS permanent_deletion_requested_at TIMESTAMP NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS permanent_deletion_requested_by TEXT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS permanent_deletion_reason TEXT NULL",

    # -- Phase graph_indexer (26/04/2026, fix etape Audit-3-points) --
    # Le job graph_indexer (cree le 21/04, commit 0c11904) avait sa
    # propre fonction ensure_schema() qui ajoutait ces 2 colonnes a
    # aria_memory + 1 index. Mais cette fonction n'etait appelee que
    # depuis run_batch(), lui-meme bloque par should_run_batch() qui
    # plantait sur la colonne manquante (cycle ferme).
    # Resultat : depuis le 21/04, le job plantait toutes les 3 min
    # avec "column am.indexed_in_graph does not exist" et 209
    # conversations attendaient d'etre indexees dans le graphe semantique.
    # Fix : creer les colonnes ici, supprimer ensure_schema() du job.

    # M-G01 : flag d indexation (defaut false = pas encore indexe)
    "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS indexed_in_graph BOOLEAN DEFAULT false",
    "ALTER TABLE aria_memory ADD COLUMN IF NOT EXISTS graph_indexed_at TIMESTAMP",

    # M-G02 : index partiel pour scanner rapidement les conversations
    # non encore indexees (le job tourne toutes les 3 min, l'index
    # evite un seq scan a chaque iteration)
    "CREATE INDEX IF NOT EXISTS idx_aria_memory_not_indexed "
    "ON aria_memory (indexed_in_graph, id) "
    "WHERE indexed_in_graph = false",

    # -- Phase webhooks Microsoft multi-boites (28/04 soir) --
    # Decision Guillaume 28/04 : chaque chose qu on connecte est
    # multipliable par defaut. Outlook ne fait pas exception : il faut
    # autant d abonnements webhook que de boites Outlook connectees.
    # Avant cette migration, ensure_all_subscriptions iterait sur 1 token
    # par user et creait 1 subscription par user. Avec 2 Outlook (Guillaume
    # + contact@couffrant-solar.fr), seule la derniere connectee recevait
    # les notifications de nouveaux mails. Bug invisible mais critique.

    # M-W01 : ajouter connection_id pour lier chaque webhook a sa connexion
    # FK avec ON DELETE CASCADE : si la connexion est supprimee, le
    # webhook l est aussi (coherent). Nullable au depart pour ne pas
    # casser la ligne existante.
    "ALTER TABLE webhook_subscriptions ADD COLUMN IF NOT EXISTS connection_id INTEGER",
    """DO $$ BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint
          WHERE conname = 'webhook_subs_connection_id_fkey'
        ) THEN
          ALTER TABLE webhook_subscriptions
            ADD CONSTRAINT webhook_subs_connection_id_fkey
            FOREIGN KEY (connection_id) REFERENCES tenant_connections(id) ON DELETE CASCADE;
        END IF;
    END $$""",
    "CREATE INDEX IF NOT EXISTS idx_webhook_subs_user_conn "
    "ON webhook_subscriptions (username, connection_id) "
    "WHERE connection_id IS NOT NULL",

    # M-W02 : backfill connection_id pour les abonnements existants en
    # remontant via username + tenant_id la connexion microsoft/outlook
    # active la plus recente. Heuristique mais c est la seule info qu on
    # a (le subscription_id Microsoft ne contient pas de ref a notre
    # connection_id en base).
    """UPDATE webhook_subscriptions ws
       SET connection_id = (
         SELECT tc.id FROM tenant_connections tc
         JOIN connection_assignments ca ON ca.connection_id = tc.id
         WHERE ca.username = ws.username
           AND tc.tenant_id = ws.tenant_id
           AND tc.tool_type IN ('microsoft', 'outlook')
           AND tc.status = 'connected'
           AND ca.enabled = true
         ORDER BY tc.updated_at DESC
         LIMIT 1
       )
       WHERE ws.connection_id IS NULL""",

    # -- Phase audit isolation user-user LOT 2 (28/04 soir) --
    # Cf. docs/audit_isolation_user_user_phase2_et_plan.md
    # Findings U.3-U.6 : 4 contraintes UNIQUE sans tenant_id, pas
    # multi-tenant safe en cas d homonyme cross-tenant futur.
    # Verification 28/04 : 0 duplicata sur les 4 tables (mail_memory,
    # sent_mail_memory, email_signatures, teams_sync_state).
    # Migration prudente : DROP IF EXISTS puis ADD CONSTRAINT,
    # idempotente. Ordre du commit : code Python (ON CONFLICT mis a
    # jour avec tenant_id) + migrations DB. Les 2 sont deployes
    # ensemble par Railway, l app ne sert pas de requetes pendant
    # init_postgres() donc pas de fenetre de risque.

    # M-U01 : mail_memory UNIQUE (message_id, username) -> + tenant_id
    "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_msg_user_unique",
    "ALTER TABLE mail_memory DROP CONSTRAINT IF EXISTS mail_memory_msg_user_tenant_unique",
    "ALTER TABLE mail_memory ADD CONSTRAINT mail_memory_msg_user_tenant_unique UNIQUE (message_id, username, tenant_id)",

    # M-U02 : sent_mail_memory idem
    "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_msg_user_unique",
    "ALTER TABLE sent_mail_memory DROP CONSTRAINT IF EXISTS sent_mail_msg_user_tenant_unique",
    "ALTER TABLE sent_mail_memory ADD CONSTRAINT sent_mail_msg_user_tenant_unique UNIQUE (message_id, username, tenant_id)",

    # M-U03 : email_signatures UNIQUE (username, email_address) -> + tenant_id
    "ALTER TABLE email_signatures DROP CONSTRAINT IF EXISTS email_signatures_username_email_address_key",
    "ALTER TABLE email_signatures DROP CONSTRAINT IF EXISTS email_signatures_user_email_tenant_unique",
    "ALTER TABLE email_signatures ADD CONSTRAINT email_signatures_user_email_tenant_unique UNIQUE (username, email_address, tenant_id)",

    # M-U04 : teams_sync_state UNIQUE (username, chat_id) -> + tenant_id
    "ALTER TABLE teams_sync_state DROP CONSTRAINT IF EXISTS teams_sync_state_username_chat_id_key",
    "ALTER TABLE teams_sync_state DROP CONSTRAINT IF EXISTS teams_sync_state_user_chat_tenant_unique",
    "ALTER TABLE teams_sync_state ADD CONSTRAINT teams_sync_state_user_chat_tenant_unique UNIQUE (username, chat_id, tenant_id)",

    # -- Phase 2FA Niveau 2 — LOT 0 (29/04/2026 minuit) --
    # Cf. plan d'attaque 2FA en 7 LOTs valide par Guillaume.
    # Decisions Q1-Q7 actees : super_admin + tenant_admin obligatoires,
    # 8 codes recup, fenetre TOTP +-1 (90s), session admin 4h, super 1h.
    # Ce LOT 0 est purement additif : aucun code Python ne lit encore
    # ces colonnes/tables, le login continue de marcher comme avant.

    # M-2FA-01 : 4 colonnes 2FA sur users
    # totp_secret_encrypted : secret base32 chiffre via ENCRYPTION_KEY
    # (utilise app/crypto.py, pas crypto_backup.py qui est pour les backups)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret_encrypted TEXT",
    # totp_enabled_at : NULL = 2FA pas encore activee. Date = activation reussie
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled_at TIMESTAMP",
    # recovery_codes_hashes : array de 8 hashes pbkdf2-sha256 des codes recup
    # (jamais stocker les codes en clair). Quand un code est utilise, on le retire.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_codes_hashes JSONB DEFAULT '[]'::jsonb",
    # recovery_codes_used_count : compteur d'utilisations (info pour le user
    # type "il vous reste 5 codes sur 8")
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_codes_used_count INTEGER DEFAULT 0",

    # M-2FA-02 : table user_devices (appareils connus pour skip 2FA)
    # Permet d eviter de redemander 2FA a chaque login si :
    #  - le navigateur a deja un cookie raya_device_id signe
    #  - last_2fa_validated_at est < 30 jours
    #  - l IP de connexion est dans known_ips
    # known_ips est un array JSONB de {ip, country?, first_seen, last_seen}
    # pour Q4 et Q7 declencheur 3 (IP suspecte/pays different).
    """CREATE TABLE IF NOT EXISTS user_devices (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        device_fingerprint TEXT NOT NULL,
        device_label TEXT,
        ip_first_seen TEXT,
        ip_last_seen TEXT,
        country TEXT,
        known_ips JSONB DEFAULT '[]'::jsonb,
        last_2fa_validated_at TIMESTAMP,
        expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (username, tenant_id, device_fingerprint)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_user_devices_lookup ON user_devices (username, tenant_id, expires_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_devices_cleanup ON user_devices (expires_at) WHERE expires_at < NOW()",

    # M-2FA-03 : table auth_events (audit log des events 2FA)
    # event_type :
    #   login_success, login_failure
    #   2fa_setup_started, 2fa_setup_completed
    #   2fa_success, 2fa_failure
    #   recovery_code_used, recovery_codes_regenerated
    #   2fa_reset_by_admin, 2fa_disabled
    #   device_trusted, device_revoked
    # metadata : payload libre (raison echec, qui a reset, etc.)
    """CREATE TABLE IF NOT EXISTS auth_events (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        tenant_id TEXT,
        event_type TEXT NOT NULL,
        ip TEXT,
        user_agent TEXT,
        country TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_auth_events_user_time ON auth_events (username, tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_events_type_time ON auth_events (event_type, created_at DESC)",

    # -- LOT 5 du chantier 2FA (30/04/2026) --
    # PIN court (4-6 chiffres) demande a chaque entree dans /admin et
    # /super_admin. Different du mot de passe principal et des codes 2FA.
    # Decision Guillaume : protege contre session laissee ouverte sans
    # surveillance. 3 essais rates -> escalade vers 2FA Authenticator
    # complete pour debloquer.

    # M-2FA-04 : 3 colonnes PIN sur users
    # pin_hash : pbkdf2-sha256 + salt 16B (meme pattern que password_hash)
    # pin_attempts_count : compteur essais rates dans la fenetre courante
    # pin_locked_until : timestamp fin de blocage (NULL = pas bloque)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_hash TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_attempts_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_locked_until TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_set_at TIMESTAMP",

    # -- Phase Feature Flags Phase 1 (30/04/2026 nuit) --
    # Decision Guillaume : permettre d activer/desactiver des features
    # logicielles (capture audio, moteur regles, insights, vesta, page
    # accueil, etc.) tenant par tenant. La granularite est tenant-level
    # uniquement (pas user-level) car les fonctionnalites s appliquent
    # a tout le tenant. Pour les CONNEXIONS (outils tiers), c est gere
    # separement par connection_assignments qui a deja la granularite
    # par user.
    #
    # Garantie zero regression : toutes les features sont activees par
    # defaut sur les tenants existants (couffrant_solar et juillet).
    # Phase 2 = UI super_admin pour toggle. Phase 3 = application aux
    # endpoints existants. Phase 4 = packages/forfaits prets a l emploi.

    # M-FF-01 : feature_registry — catalogue des features disponibles
    """CREATE TABLE IF NOT EXISTS feature_registry (
        feature_key TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL DEFAULT 'core',
        default_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        deprecated BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_feature_registry_category ON feature_registry (category, deprecated)",

    # M-FF-02 : tenant_features — overrides par tenant
    # Si pas de ligne pour (tenant_id, feature_key) -> on prend le
    # default_enabled du registry. Si ligne presente -> sa valeur enabled.
    # CASCADE : si on supprime une feature du registry, les overrides tombent.
    # CASCADE : si on supprime un tenant, ses overrides tombent aussi.
    """CREATE TABLE IF NOT EXISTS tenant_features (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        feature_key TEXT NOT NULL REFERENCES feature_registry(feature_key) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMP DEFAULT NOW(),
        updated_by TEXT,
        notes TEXT,
        UNIQUE (tenant_id, feature_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tenant_features_lookup ON tenant_features (tenant_id, feature_key)",

    # M-FF-03 : seed du catalogue ~20 features actuelles de Raya
    # Toutes activees par defaut. Categories : core / mail / outils / ux / ai
    # Les features seront utilisees par require_feature() / is_feature_enabled().
    """INSERT INTO feature_registry (feature_key, label, description, category, default_enabled) VALUES
        ('chat_basic', 'Chat Raya', 'Conversation de base avec Raya', 'core', TRUE),
        ('chat_voice', 'Voix (TTS)', 'Lecture audio des reponses Raya', 'core', TRUE),
        ('memory_rules', 'Regles apprises', 'Apprentissage et stockage des regles personnelles (aria_rules)', 'ai', TRUE),
        ('memory_insights', 'Insights', 'Insights et synthesis automatiques (aria_insights)', 'ai', TRUE),
        ('memory_topics', 'Mes sujets', 'Sujets parallels (user_topics)', 'ai', TRUE),
        ('feedback_learning', 'Apprentissage par feedback 👍/👎', 'Renforcement des regles via feedback utilisateur', 'ai', TRUE),
        ('audio_capture', 'Capture audio Plaud/TapeACall', 'Transcription audio + extraction structuree', 'ai', TRUE),
        ('mail_outlook', 'Outlook / Microsoft 365', 'Connexion mail Outlook + lecture/envoi', 'mail', TRUE),
        ('mail_gmail', 'Gmail / Google Workspace', 'Connexion mail Gmail + lecture/envoi', 'mail', TRUE),
        ('mail_signatures', 'Signatures email multi-boites', 'Editeur WYSIWYG + signature par defaut par boite', 'mail', TRUE),
        ('drive_sharepoint', 'SharePoint / OneDrive', 'Connexion Drive Microsoft + scan documents', 'outils', TRUE),
        ('drive_google', 'Google Drive', 'Connexion Drive Google + scan documents', 'outils', TRUE),
        ('odoo_connector', 'Odoo (CRM/ERP)', 'Connexion Odoo lecture + ecriture', 'outils', TRUE),
        ('vesta_connector', 'Vesta (devis PV)', 'Connexion Vesta lecture devis et clients', 'outils', TRUE),
        ('event_rules', 'Regles d evenement', 'Regles automatiques sur evenements externes', 'ai', TRUE),
        ('proactive_alerts', 'Alertes proactives', 'Notifications Raya proactives a l utilisateur', 'ai', TRUE),
        ('homepage_dynamic', 'Page accueil dynamique', 'Vitrine quotidienne personnalisable', 'ux', TRUE),
        ('topics_continuation', 'Reprise contextuelle Mes Sujets', 'Click sur sujet -> reprise fil au lieu de topo', 'ux', TRUE),
        ('admin_audit_panel', 'Panel audit super_admin', 'Acces aux logs d audit + connexions detaillees', 'core', TRUE),
        ('mail_diff_learning', 'Apprentissage par diff mails', 'Capture des modifs utilisateur sur brouillons mails', 'ai', TRUE)
       ON CONFLICT (feature_key) DO NOTHING""",

    # M-FF-04 : backfill - toutes les features activees pour les tenants existants
    # On insere une ligne par (tenant, feature) avec enabled=true.
    # ON CONFLICT DO NOTHING : si l override existe deja, on ne touche pas.
    # Ca permet de relancer la migration sans casser les configurations
    # eventuellement deja modifiees par le super_admin via l UI Phase 2.
    """INSERT INTO tenant_features (tenant_id, feature_key, enabled, updated_by, notes)
       SELECT t.id, f.feature_key, TRUE, 'system_backfill_30avril', 'Backfill initial - toutes les features activees par defaut'
       FROM tenants t
       CROSS JOIN feature_registry f
       ON CONFLICT (tenant_id, feature_key) DO NOTHING""",

    # M-FF-05 (30/04 nuit) : NETTOYAGE CATALOGUE FEATURES
    # Decision Guillaume : 18 features initiales etaient mal pensees.
    # Ce sont en fait soit des comportements coeur de Raya (toujours actifs),
    # soit des connexions (gerees via tenant_connections), soit de l UX.
    # On les marque deprecated=TRUE pour qu elles disparaissent de l UI.
    """UPDATE feature_registry SET deprecated = TRUE, updated_at = NOW()
       WHERE feature_key IN (
         'chat_basic', 'chat_voice',
         'memory_rules', 'memory_insights', 'memory_topics', 'feedback_learning',
         'event_rules', 'proactive_alerts', 'mail_diff_learning',
         'mail_outlook', 'mail_gmail', 'mail_signatures',
         'drive_sharepoint', 'drive_google',
         'odoo_connector', 'vesta_connector',
         'homepage_dynamic', 'topics_continuation',
         'admin_audit_panel'
       )""",

    # M-FF-06 : ajout des 4 vraies features modules optionnels
    # Ces features sont des fonctionnalites logicielles independantes des
    # connexions, qui peuvent etre incluses ou non dans le forfait.
    # Toutes activees par defaut (zero impact retrocompat).
    """INSERT INTO feature_registry (feature_key, label, description, category, default_enabled) VALUES
        ('audio_capture', 'Capture audio',
         'Module de capture et transcription audio (Plaud, TapeACall). Permet d uploader des enregistrements de RDV/visites pour transcription automatique et extraction de donnees structurees.',
         'modules', TRUE),
        ('pdf_editor', 'Editeur PDF',
         'Creation, modification et signature de PDF directement depuis Raya. Pratique pour devis, contrats, attestations.',
         'modules', TRUE),
        ('image_editor', 'Editeur d images',
         'Creation et modification d images (annotations, redimensionnement, signatures, watermarks). Pratique pour photos chantier, schemas, plans.',
         'modules', TRUE),
        ('accounting_engine', 'Base de comptabilite',
         'Module de comptabilite integre (a definir avec Guillaume). Saisie factures/depenses, classement, exports comptable.',
         'modules', TRUE)
       ON CONFLICT (feature_key) DO NOTHING""",

    # M-FF-07 : backfill des nouvelles features pour tenants existants
    # Toutes activees par defaut (les tenants Couffrant Solar et Juillet
    # auront les 4 modules ON, modifiable ensuite via le panel par tenant).
    """INSERT INTO tenant_features (tenant_id, feature_key, enabled, updated_by, notes)
       SELECT t.id, f.feature_key, TRUE, 'system_backfill_30avril_nuit',
              'Backfill modules - 4 vraies features ajoutees au catalogue'
       FROM tenants t
       CROSS JOIN feature_registry f
       WHERE f.feature_key IN ('audio_capture', 'pdf_editor', 'image_editor', 'accounting_engine')
       ON CONFLICT (tenant_id, feature_key) DO NOTHING""",

    # -- Phase Connexions Universelles (1er mai 2026) --
    # Voir docs/vision_connexions_universelles_01mai.md
    #
    # Cette phase pose les FONDATIONS de l architecture commune a TOUTES
    # les connexions Raya (mails, drive, odoo, whatsapp, vesta, teams).
    # 18 questions ont ete tranchees avec Guillaume + 9 enrichissements
    # techniques issus de l audit standards industriels.
    #
    # 7 nouvelles tables creees ici. Les modules Python (connection_health,
    # connection_resilience, alert_dispatcher, couche comprehension) seront
    # ajoutes dans les commits suivants (Etapes 1.2 a 1.5).
    #
    # NOTE : on REUTILISE les tables system_heartbeat et system_alerts qui
    # existent deja (depuis 18/04/2026). connection_health complete sans
    # remplacer (granularite par connection_id, pas par component string).

    # M-CU01 : connection_health
    # Une ligne par connexion (mail, drive, odoo, whatsapp, vesta, teams...)
    # Mise a jour a CHAQUE poll, succes ou echec. La regle d alerte est :
    # "Si last_successful_poll_at est plus vieux que alert_threshold_seconds,
    #  emettre une alerte." (= liveness check, decision Q15-D Guillaume)
    """CREATE TABLE IF NOT EXISTS connection_health (
        id SERIAL PRIMARY KEY,
        connection_id INTEGER NOT NULL REFERENCES tenant_connections(id) ON DELETE CASCADE,
        tenant_id TEXT NOT NULL,
        username TEXT NOT NULL,
        connection_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'unknown',
        last_successful_poll_at TIMESTAMP,
        last_poll_attempt_at TIMESTAMP,
        consecutive_failures INT DEFAULT 0,
        current_delta_token TEXT,
        expected_poll_interval_seconds INT,
        alert_threshold_seconds INT,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (connection_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conn_health_status ON connection_health (status) WHERE status != 'healthy'",
    "CREATE INDEX IF NOT EXISTS idx_conn_health_tenant ON connection_health (tenant_id, connection_type)",

    # M-CU02 : connection_health_events
    # Log de chaque tentative de poll. C est la SOURCE DE VERITE pour le
    # liveness check : "le dernier event ok est-il assez recent ?"
    # Garde l historique des 90 derniers jours par connexion (purge prevue
    # dans un job nocturne ulterieur). Volume estime : ~30k events / jour
    # toutes connexions confondues.
    """CREATE TABLE IF NOT EXISTS connection_health_events (
        id BIGSERIAL PRIMARY KEY,
        connection_id INTEGER NOT NULL,
        poll_started_at TIMESTAMP NOT NULL,
        poll_ended_at TIMESTAMP,
        status TEXT NOT NULL,
        items_seen INT DEFAULT 0,
        items_new INT DEFAULT 0,
        next_delta_token TEXT,
        duration_ms INT,
        error_detail TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conn_events_lookup ON connection_health_events (connection_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_conn_events_failures ON connection_health_events (connection_id, status, created_at DESC) WHERE status != 'ok'",

    # M-CU03 : attachment_index
    # Index unifie de toutes les pieces jointes (mail) + fichiers (drive).
    # Source unique de verite pour la recherche de documents par contenu.
    # Le pipeline de comprehension (extraction + Vision IA + tagging) ecrit
    # ici. Cf decisions Q2 (texte par defaut + Vision si pertinent), Q14
    # (texte + resume + tags structures).
    """CREATE TABLE IF NOT EXISTS attachment_index (
        id BIGSERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        username TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        connection_id INTEGER,
        file_name TEXT,
        file_size BIGINT,
        mime_type TEXT,
        text_content TEXT,
        summary_content TEXT,
        tags JSONB,
        embedding_global vector(1536),
        vision_processed BOOLEAN DEFAULT FALSE,
        deleted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (source_type, source_ref)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_attachment_tenant ON attachment_index (tenant_id, deleted_at) WHERE deleted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_attachment_tags ON attachment_index USING gin (tags)",
    "CREATE INDEX IF NOT EXISTS idx_attachment_embedding ON attachment_index USING hnsw (embedding_global vector_cosine_ops)",

    # M-CU04 : attachment_chunks
    # Embeddings 2 niveaux (ENRICHISSEMENT Q14) : un embedding par
    # paragraphe en plus de l embedding global. Permet la recherche fine
    # ("trouve la phrase qui mentionne 9 kWc") en plus de la recherche
    # large ("trouve tous les devis solaires").
    """CREATE TABLE IF NOT EXISTS attachment_chunks (
        id BIGSERIAL PRIMARY KEY,
        attachment_id BIGINT NOT NULL REFERENCES attachment_index(id) ON DELETE CASCADE,
        chunk_index INT NOT NULL,
        content TEXT NOT NULL,
        embedding vector(1536),
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (attachment_id, chunk_index)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_chunks_attachment ON attachment_chunks (attachment_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON attachment_chunks USING hnsw (embedding vector_cosine_ops)",

    # M-CU05 : tenant_drive_blacklist
    # Dossiers Drive/SharePoint exclus de l indexation par tenant.
    # Decision Q8 : tout par defaut + blacklist. La table drive_folders
    # existante (depuis 20/04) liste les dossiers SURVEILLES, ici on liste
    # les dossiers EXCLUS (deux concepts complementaires).
    """CREATE TABLE IF NOT EXISTS tenant_drive_blacklist (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        connection_id INTEGER NOT NULL,
        folder_path TEXT NOT NULL,
        reason TEXT,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (connection_id, folder_path)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_drive_blacklist_tenant ON tenant_drive_blacklist (tenant_id, connection_id)",

    # M-CU06 : tenant_whatsapp_whitelist
    # Conversations WhatsApp autorisees a l indexation. Inverse logique
    # par rapport a Drive : sur WhatsApp on est en LISTE BLANCHE par defaut
    # (decision Q6, principe de souverainete). Aucun message non-whitelist
    # n est jamais indexe.
    """CREATE TABLE IF NOT EXISTS tenant_whatsapp_whitelist (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        connection_id INTEGER NOT NULL,
        conversation_type TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        conversation_label TEXT,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (connection_id, conversation_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_whitelist_tenant ON tenant_whatsapp_whitelist (tenant_id, connection_id)",

    # M-CU07 : tenant_attachment_rules
    # Regles metier paramatrables par tenant pour la couche comprehension.
    # Permet a chaque tenant d AJOUTER des regles specifiques a son metier
    # sans modifier le code (ex: un commerçant ajoute "force_vision si nom
    # contient 'commande_fournisseur'"). Note Guillaume Q13 : regles
    # universelles dans le code, regles metier ici.
    """CREATE TABLE IF NOT EXISTS tenant_attachment_rules (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        rule_name TEXT NOT NULL,
        rule_pattern TEXT,
        rule_action TEXT NOT NULL,
        rule_priority INT DEFAULT 0,
        enabled BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_attach_rules_tenant ON tenant_attachment_rules (tenant_id, enabled, rule_priority)",

    # M-S3-CLEANUP : nettoyage des doublons mail_memory crees par le polling
    # delta Outlook (Etape 3.4) avant le fix des bugs mail_exists/insert_mail
    # (commit 2aba00d, 01/05/2026).
    #
    # Contexte : entre 14h et 14h20 le 01/05, le polling delta Outlook actif
    # avec un mail_exists() bugge (filtre tenant_id casse en SQL) et un
    # insert_mail() qui n inserait pas tenant_id, a re-insere des mails deja
    # presents. Les doublons sont identifiables sans ambiguite : meme
    # (message_id, username) avec tenant_id NULL d un cote et tenant_id
    # rempli de l autre.
    #
    # Cette migration supprime les doublons NULL et garde les originaux qui
    # ont tenant_id rempli. Idempotente : si pas de doublon (cas normal),
    # le DELETE ne fait rien.
    """DELETE FROM mail_memory m1
       WHERE m1.tenant_id IS NULL
         AND EXISTS (
             SELECT 1 FROM mail_memory m2
             WHERE m2.message_id = m1.message_id
               AND m2.username = m1.username
               AND m2.tenant_id IS NOT NULL
               AND m2.id != m1.id
         )""",

    # -- Phase Drive multi-racines (02/05/2026 matin) --
    # Voir docs/journal_02mai_2026_drive_multi_racines.md
    #
    # Decision Guillaume 02/05 : permettre a chaque tenant de configurer
    # MULTIPLES racines de scan (cas typique : Drive Commun + Drive Direction
    # chez Couffrant) avec exclusions/inclusions granulaires a n importe
    # quelle profondeur de l arborescence.
    #
    # Regle universelle : "le chemin le plus long gagne" (logique .gitignore).
    # Heritage par defaut : un dossier inclus/exclu se propage a ses sous-
    # dossiers, sauf override explicite plus profond.
    #
    # Architecture :
    #   - drive_folders (existante) : liste des RACINES surveillees
    #   - tenant_drive_blacklist (existante, etendue) : regles d EXCEPTION
    #       rule_type = 'include' : inclus meme si parent exclu
    #       rule_type = 'exclude' : exclus (cas legacy, default backward compat)
    #
    # Backward compat : les regles existantes (sans rule_type) deviennent
    # automatiquement rule_type='exclude' grace au DEFAULT de la migration.

    # M-DMR01 : ajout colonne rule_type (include/exclude)
    # Default 'exclude' preserve le comportement actuel des regles existantes.
    "ALTER TABLE tenant_drive_blacklist ADD COLUMN IF NOT EXISTS rule_type TEXT NOT NULL DEFAULT 'exclude'",
    # Contrainte de validation : seulement include ou exclude
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tdb_rule_type_check') THEN
            ALTER TABLE tenant_drive_blacklist ADD CONSTRAINT tdb_rule_type_check
                CHECK (rule_type IN ('include', 'exclude'));
        END IF;
    END $$""",

    # M-DMR02 : ajout colonne scope (tenant/user) pour preparer les drives prives
    # tenant = regle geree par admin du tenant (cas standard, defaut)
    # user   = regle geree par le user proprietaire du drive prive (V2 future)
    "ALTER TABLE tenant_drive_blacklist ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'tenant'",
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tdb_scope_check') THEN
            ALTER TABLE tenant_drive_blacklist ADD CONSTRAINT tdb_scope_check
                CHECK (scope IN ('tenant', 'user'));
        END IF;
    END $$""",

    # M-DMR03 : colonne owner_username (qui possede la regle si scope=user)
    # NULL si scope=tenant (la regle appartient a tout le tenant).
    # Defini si scope=user (la regle appartient a un user specifique pour son drive prive).
    "ALTER TABLE tenant_drive_blacklist ADD COLUMN IF NOT EXISTS owner_username TEXT",

    # M-DMR04 : index pour les requetes is_path_indexable (par connexion + path)
    "CREATE INDEX IF NOT EXISTS idx_drive_rules_lookup ON tenant_drive_blacklist (connection_id, folder_path)",

    # M-DMR05 : index sur tenant pour vue admin
    "CREATE INDEX IF NOT EXISTS idx_drive_rules_tenant_scope ON tenant_drive_blacklist (tenant_id, scope, connection_id)",

    # M-RH01 : elargir la contrainte CHECK sur aria_rules_history.change_type
    # pour autoriser les nouveaux types ecrits par le job rules_optimizer du
    # dimanche soir : 'merged_optimizer' (Layer A fusion doublons) et
    # 'recategorized_optimizer' (Layer A0 canonisation des categories).
    # Avant cette migration, le job catchait silencieusement la CHECK violation
    # et concluait '0 doublon fusionne' alors qu il en avait trouve. Bug
    # diagnostique le 03/05/2026 apres run nocturne.
    """DO $$ BEGIN
        ALTER TABLE aria_rules_history DROP CONSTRAINT IF EXISTS change_type_check;
        ALTER TABLE aria_rules_history ADD CONSTRAINT change_type_check
            CHECK (change_type IN (
                'created', 'updated', 'reinforced', 'deactivated', 'rollback',
                'merged_optimizer', 'recategorized_optimizer'
            ));
    END $$""",
]
