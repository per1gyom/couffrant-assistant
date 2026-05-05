-- Migration: Phase 1 mini-Graphiti — Apprentissage hiérarchisé
-- Date: 05/05/2026 soir
-- Branche: feat/learning-hierarchy
-- Doc: docs/projet_apprentissage_hierarchise.md

-- =====================================================================
-- PRINCIPE :
-- Ajouter sans casser. Que des ALTER TABLE ADD COLUMN avec defaults.
-- Aucun DROP, aucune modification destructive.
-- Idempotent grace a IF NOT EXISTS sur les colonnes (Postgres 9.6+).
-- =====================================================================

-- 1. ARIA_RULES : ajout des dimensions type/temporal_class + bi-temporal

ALTER TABLE aria_rules
    ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'Fact';

COMMENT ON COLUMN aria_rules.type IS
    'Type de l info : Fact (objectif), Preference (user), Behavior (Raya), Knowledge (culture metier)';

ALTER TABLE aria_rules
    ADD COLUMN IF NOT EXISTS temporal_class TEXT DEFAULT 'Atemporal';

COMMENT ON COLUMN aria_rules.temporal_class IS
    'Classe temporelle : Static (immuable), Dynamic (peut evoluer), Atemporal (sans cadre temporel)';

ALTER TABLE aria_rules
    ADD COLUMN IF NOT EXISTS valid_at TIMESTAMP DEFAULT NULL;

COMMENT ON COLUMN aria_rules.valid_at IS
    'Quand l info est devenue vraie dans le monde reel (NULL si inconnu)';

ALTER TABLE aria_rules
    ADD COLUMN IF NOT EXISTS invalid_at TIMESTAMP DEFAULT NULL;

COMMENT ON COLUMN aria_rules.invalid_at IS
    'Quand l info a cesse d etre vraie (NULL = encore vraie). Bi-temporal Graphiti.';

-- 2. SEMANTIC_GRAPH_EDGES : meme bi-temporal pour les relations

ALTER TABLE semantic_graph_edges
    ADD COLUMN IF NOT EXISTS valid_at TIMESTAMP DEFAULT NULL;

COMMENT ON COLUMN semantic_graph_edges.valid_at IS
    'Quand la relation est devenue vraie dans le monde reel (NULL si inconnu)';

ALTER TABLE semantic_graph_edges
    ADD COLUMN IF NOT EXISTS invalid_at TIMESTAMP DEFAULT NULL;

COMMENT ON COLUMN semantic_graph_edges.invalid_at IS
    'Quand la relation a cesse d etre vraie (NULL = encore vraie). Bi-temporal Graphiti.';

-- 3. INDEX pour retrieval rapide des regles actives non invalidees

CREATE INDEX IF NOT EXISTS idx_aria_rules_active_valid
    ON aria_rules (type, temporal_class)
    WHERE active = true AND invalid_at IS NULL;

COMMENT ON INDEX idx_aria_rules_active_valid IS
    'Index partiel sur regles actives non-invalidees. Accelere le loader hierarchise (Phase 4).';

-- 4. INDEX sur invalid_at pour les "time travel queries" (rares mais utiles)

CREATE INDEX IF NOT EXISTS idx_aria_rules_invalid_at
    ON aria_rules (invalid_at)
    WHERE invalid_at IS NOT NULL;

COMMENT ON INDEX idx_aria_rules_invalid_at IS
    'Pour requetes "qu est ce qu on s etait dit en avril sur X" : recupere les regles invalidees.';

-- =====================================================================
-- ROLLBACK (si jamais besoin) :
-- ALTER TABLE aria_rules DROP COLUMN IF EXISTS type;
-- ALTER TABLE aria_rules DROP COLUMN IF EXISTS temporal_class;
-- ALTER TABLE aria_rules DROP COLUMN IF EXISTS valid_at;
-- ALTER TABLE aria_rules DROP COLUMN IF EXISTS invalid_at;
-- ALTER TABLE semantic_graph_edges DROP COLUMN IF EXISTS valid_at;
-- ALTER TABLE semantic_graph_edges DROP COLUMN IF EXISTS invalid_at;
-- DROP INDEX IF EXISTS idx_aria_rules_active_valid;
-- DROP INDEX IF EXISTS idx_aria_rules_invalid_at;
-- =====================================================================
