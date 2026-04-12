"""
Mémoire : règles et paramètres (aria_rules).
Isolation par username + tenant_id.

Fonctions canoniques à utiliser :
  app.rule_engine.get_rules_by_category(username, category, tenant_id=None)
  app.rule_engine.get_memoire_param(username, param, default, tenant_id=None)
  app.memory_rules.save_rule(category, rule, source, confidence, username, tenant_id=None)

Phase 3a : save_rule vectorise la règle à la création (si OPENAI_API_KEY présent).
Dégradation gracieuse si clé absente — la règle est insérée sans vecteur.
"""
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


# ─── HELPERS EMBEDDING ───

def _embed_rule(rule_text: str, category: str):
    """Vectorise une règle pour la recherche RAG. Retourne la chaîne vecteur ou None."""
    try:
        from app.embedding import embed
        vec = embed(f"[{category}] {rule_text}")
        if vec is None:
            return None
        return "[" + ",".join(str(x) for x in vec) + "]"
    except Exception:
        return None


# ─── FONCTIONS ACTIVES ───

def get_aria_rules(username: str = 'guillaume', tenant_id: str = None) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute("""
                SELECT id, category, rule, confidence, reinforcements
                FROM aria_rules
                WHERE active = true
                  AND username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                  AND category != 'memoire'
                ORDER BY confidence DESC, reinforcements DESC, created_at DESC
                LIMIT 60
            """, (username, tenant_id))
        else:
            c.execute("""
                SELECT id, category, rule, confidence, reinforcements
                FROM aria_rules
                WHERE active = true AND username = %s AND category != 'memoire'
                ORDER BY confidence DESC, reinforcements DESC, created_at DESC
                LIMIT 60
            """, (username,))
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows])
    finally:
        if conn:
            conn.close()


def save_rule(category: str, rule: str, source: str = "auto",
              confidence: float = 0.7, username: str = None,
              tenant_id: str = None) -> int:
    """
    Sauvegarde une règle apprise par Raya.
    Déduplication par égalité exacte normalisée (LOWER+TRIM).
    Phase 3a : vectorise la règle à la création pour le RAG.
    """
    if not username:
        raise ValueError("save_rule : username obligatoire")
    if not rule or not rule.strip():
        raise ValueError("save_rule : règle vide refusée")

    rule_clean = rule.strip()
    effective_tenant = tenant_id or DEFAULT_TENANT

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_rules
            WHERE active = true
              AND username = %s
              AND category = %s
              AND LOWER(TRIM(rule)) = LOWER(TRIM(%s))
            LIMIT 1
        """, (username, category, rule_clean))
        existing = c.fetchone()

        if existing:
            c.execute("""
                UPDATE aria_rules
                SET reinforcements = reinforcements + 1,
                    confidence = LEAST(1.0, confidence + 0.1),
                    updated_at = NOW()
                WHERE id = %s
            """, (existing[0],))
            conn.commit()
            return existing[0]

        vec = _embed_rule(rule_clean, category)

        if vec:
            c.execute("""
                INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector) RETURNING id
            """, (username, effective_tenant, category, rule_clean, source, confidence, vec))
        else:
            c.execute("""
                INSERT INTO aria_rules (username, tenant_id, category, rule, source, confidence)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (username, effective_tenant, category, rule_clean, source, confidence))

        rule_id = c.fetchone()[0]
        conn.commit()
        return rule_id
    finally:
        if conn:
            conn.close()


def delete_rule(rule_id: int, username: str = 'guillaume') -> bool:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE aria_rules SET active = false, updated_at = NOW() WHERE id = %s AND username = %s",
            (rule_id, username)
        )
        conn.commit()
        return c.rowcount > 0
    finally:
        if conn:
            conn.close()


def extract_keywords_from_rule(rule: str) -> list:
    import re
    keywords = re.findall(r"'([^']+)'", rule.lower())
    if keywords:
        return [k.strip() for k in keywords if len(k.strip()) > 2]
    match = re.search(r"(?:contenant|de)\s+(.+?)(?:\s*=|\s*\u2192|\s*$)", rule.lower())
    if match:
        parts = [p.strip() for p in match.group(1).split(',')]
        return [p for p in parts if len(p) > 2]
    return []


def seed_default_rules(username: str = 'guillaume'):
    """Raya apprend d'elle-même. Aucune règle par défaut."""
    pass
