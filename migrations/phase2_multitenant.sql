-- Phase 2 — Migration multi-tenant
-- Ajoute tenant_id sur toutes les tables, backfill depuis users,
-- puis rend tenant_id NOT NULL et crée les index composites.
--
-- Ce script est IDEMPOTENT (IF NOT EXISTS / ON CONFLICT).
-- À exécuter UNE SEULE FOIS sur la PG production après backup.
-- Railway init_postgres() fait la même chose via les migrations Python,
-- mais ce script permet un run manuel si besoin.

BEGIN;

-- 1. Ajout de tenant_id (nullable d'abord pour le backfill)
ALTER TABLE aria_rules           ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_insights        ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_memory          ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE mail_memory          ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_hot_summary     ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_session_digests ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_style_examples  ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE aria_profile         ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE oauth_tokens         ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE reply_learning_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE sent_mail_memory     ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE teams_sync_state     ADD COLUMN IF NOT EXISTS tenant_id TEXT;

-- 2. Backfill depuis la table users (join sur username)
UPDATE aria_rules           a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_insights        a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_memory          a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE mail_memory          a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_hot_summary     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_session_digests a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_style_examples  a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE aria_profile         a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE oauth_tokens         a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE reply_learning_memory a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE sent_mail_memory     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;
UPDATE teams_sync_state     a SET tenant_id = u.tenant_id FROM users u WHERE a.username = u.username AND a.tenant_id IS NULL;

-- 3. Fallback pour les lignes orphelines (pas de correspondance users)
UPDATE aria_rules            SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_insights         SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_memory           SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE mail_memory           SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_hot_summary      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_session_digests  SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_style_examples   SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE aria_profile          SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE oauth_tokens          SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE reply_learning_memory SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE sent_mail_memory      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;
UPDATE teams_sync_state      SET tenant_id = 'couffrant_solar' WHERE tenant_id IS NULL;

-- 4. Index composites pour les requêtes scopées (tenant_id + username)
CREATE INDEX IF NOT EXISTS idx_aria_rules_tenant_user       ON aria_rules (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_aria_insights_tenant_user    ON aria_insights (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_aria_memory_tenant_user      ON aria_memory (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_mail_memory_tenant_user      ON mail_memory (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_style_examples_tenant_user   ON aria_style_examples (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_tenant_user     ON oauth_tokens (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_reply_learning_tenant_user   ON reply_learning_memory (tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_sent_mail_tenant_user        ON sent_mail_memory (tenant_id, username);

COMMIT;
