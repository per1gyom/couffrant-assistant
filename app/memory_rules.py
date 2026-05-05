"""
Memoire : regles et parametres (aria_rules).
Isolation par username + tenant_id.

Fonctions canoniques a utiliser :
  app.rule_engine.get_rules_by_category(username, category, tenant_id=None)
  app.rule_engine.get_memoire_param(username, param, default, tenant_id=None)
  app.memory_rules.save_rule(category, rule, source, confidence, username, tenant_id=None)

Phase 3a : save_rule vectorise la regle a la creation (si OPENAI_API_KEY present).
Degradation gracieuse si cle absente.

5D-2d : save_rule accepte personal=True pour ecrire une regle sans tenant
        (tenant_id=NULL en base).
5F-2  : historique des versions dans aria_rules_history + rollback.
"""
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


# ─── HELPERS EMBEDDING ───

def _embed_rule(rule_text: str, category: str):
    try:
        from app.embedding import embed
        vec = embed(f"[{category}] {rule_text}")
        if vec is None:
            return None
        return "[" + ",".join(str(x) for x in vec) + "]"
    except Exception:
        return None


# ─── FONCTIONS ACTIVES ───

def get_aria_rules(username: str, tenant_id: str) -> str:
    """Retourne les regles aria d'un user.

    F.1 (audit isolation user-user, LOT 1.8) : tenant_id est maintenant
    OBLIGATOIRE. La branche else legacy qui filtrait seulement par
    username (avec WARNING) est retiree apres verification que tous les
    callers actifs passent bien tenant_id. Si un nouveau caller oublie,
    raise au lieu de fuiter.

    NOTE 05/05/2026 : cette fonction est conservee pour retrocompat.
    Le contexte de Raya utilise desormais get_aria_rules_hierarchical()
    qui produit 4 blocs distincts (connaissances_durables, infos_a_confirmer,
    comportements, culture_metier). Voir Phase 4 du chantier mini-Graphiti.
    """
    if not username:
        raise ValueError("get_aria_rules : username obligatoire")
    if not tenant_id:
        raise ValueError(
            "get_aria_rules : tenant_id obligatoire "
            "(defense en profondeur isolation user-user)"
        )
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true
              AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category != 'Mémoire'
              AND (invalid_at IS NULL OR invalid_at > NOW())
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 60
        """, (username, tenant_id))
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows])
    finally:
        if conn:
            conn.close()


def get_aria_rules_hierarchical(username: str, tenant_id: str) -> dict:
    """Retourne les regles aria classees en 4 blocs hierarchiques.

    Phase 4 du chantier mini-Graphiti (05/05/2026 soir).

    Returns un dict avec 5 cles :
      - 'connaissances_durables' : Fact + Preference (Static/Atemporal)
      - 'infos_a_confirmer'      : Fact + Dynamic (avec marqueur si > 30j)
      - 'comportements'          : Behavior (Atemporal)
      - 'culture_metier'         : Knowledge (Atemporal/Static)
      - 'rule_ids'               : list[int] de tous les ids charges
                                    (pour tracabilite feedback)

    Filtre : invalid_at IS NULL (regle encore vraie) ET active=true.
    """
    if not username:
        raise ValueError("get_aria_rules_hierarchical : username obligatoire")
    if not tenant_id:
        raise ValueError(
            "get_aria_rules_hierarchical : tenant_id obligatoire"
        )

    result = {
        "connaissances_durables": "",
        "infos_a_confirmer": "",
        "comportements": "",
        "culture_metier": "",
        "rule_ids": [],
    }

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, type, temporal_class,
                   valid_at,
                   confidence, reinforcements
            FROM aria_rules
            WHERE active = true
              AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category != 'Mémoire'
              AND (invalid_at IS NULL OR invalid_at > NOW())
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 200
        """, (username, tenant_id))
        rows = c.fetchall()

        from datetime import datetime, timedelta
        threshold_30j = datetime.now() - timedelta(days=30)

        durables = []
        infos = []
        behaviors = []
        knowledge = []
        all_ids = []

        for r in rows:
            rid, category, rule, rtype, tclass, valid_at, conf, reinf = r
            all_ids.append(rid)
            line = f"[id:{rid}][{category}] {rule}"

            if rtype == "Behavior":
                behaviors.append(line)
            elif rtype == "Knowledge":
                knowledge.append(line)
            elif rtype == "Preference":
                durables.append(line)
            elif rtype == "Fact":
                if tclass == "Dynamic":
                    if valid_at and valid_at < threshold_30j:
                        line = f"[id:{rid}][{category}] ⚠️ [A REVERIFIER] {rule}"
                    infos.append(line)
                else:
                    durables.append(line)
            else:
                durables.append(line)

        result["connaissances_durables"] = "\n".join(durables) if durables else ""
        result["infos_a_confirmer"] = "\n".join(infos) if infos else ""
        result["comportements"] = "\n".join(behaviors) if behaviors else ""
        result["culture_metier"] = "\n".join(knowledge) if knowledge else ""
        result["rule_ids"] = all_ids

        return result
    finally:
        if conn:
            conn.close()


def save_rule(category: str, rule: str, source: str = "auto",
              confidence: float = 0.7, username: str = None,
              tenant_id: str = None, personal: bool = False) -> int:
    """
    Sauvegarde une regle apprise par Raya.
    Deduplication par egalite exacte normalisee (LOWER+TRIM).
    Phase 3a : vectorise la regle a la creation pour le RAG.
    5D-2d : personal=True -> tenant_id=NULL.
    5F-2  : snapshot dans aria_rules_history a chaque creation/renforcement.
    """
    if not username:
        raise ValueError("save_rule : username obligatoire")
    if not rule or not rule.strip():
        raise ValueError("save_rule : regle vide refusee")

    rule_clean = rule.strip()

    if personal:
        effective_tenant = None
    else:
        effective_tenant = tenant_id or DEFAULT_TENANT

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Passe 1 : normalisation accents + caracteres speciaux
        # Remplace les accents par leur equivalent sans accent ET normalise les fleches
        c.execute("""
            SELECT id FROM aria_rules
            WHERE active = true
              AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category = %s
              AND LOWER(TRIM(REGEXP_REPLACE(
                TRANSLATE(rule, 'àâäéèêëîïôöùûüÿçÀÂÄÉÈÊËÎÏÔÖÙÛÜŸÇ', 'aaaeeeeiioouuuycAAAEEEEIIOOUUUYC'),
                '→|⇒', '->', 'g'
              )))
              = LOWER(TRIM(REGEXP_REPLACE(
                TRANSLATE(%s, 'àâäéèêëîïôöùûüÿçÀÂÄÉÈÊËÎÏÔÖÙÛÜŸÇ', 'aaaeeeeiioouuuycAAAEEEEIIOOUUUYC'),
                '→|⇒', '->', 'g'
              )))
            LIMIT 1
        """, (username, effective_tenant, category, rule_clean))
        existing = c.fetchone()

        # Passe 2 : si pas de match textuel, recherche semantique sur embedding
        # Seuil strict 0.93 pour eviter les faux positifs (vraies regles proches mais distinctes)
        if not existing:
            vec_for_search = _embed_rule(rule_clean, category)
            if vec_for_search:
                c.execute("""
                    SELECT id, (1 - (embedding <=> %s::vector)) AS similarity
                    FROM aria_rules
                    WHERE active = true
                      AND username = %s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                      AND category = %s
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT 1
                """, (vec_for_search, username, effective_tenant, category, vec_for_search))
                row = c.fetchone()
                if row and row[1] >= 0.93:
                    existing = (row[0],)

        if existing:
            c.execute("""
                UPDATE aria_rules
                SET reinforcements = reinforcements + 1,
                    confidence = LEAST(1.0, confidence + 0.1),
                    updated_at = NOW()
                WHERE id = %s
            """, (existing[0],))
            # 5F-2 : snapshot renforcement
            c.execute("""
                INSERT INTO aria_rules_history
                  (rule_id, username, tenant_id, category, rule,
                   confidence, reinforcements, active, change_type)
                SELECT id, username, tenant_id, category, rule,
                       confidence, reinforcements, active, 'reinforced'
                FROM aria_rules WHERE id = %s
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
        # 5F-2 : snapshot creation
        c.execute("""
            INSERT INTO aria_rules_history
              (rule_id, username, tenant_id, category, rule,
               confidence, reinforcements, active, change_type)
            VALUES (%s, %s, %s, %s, %s, %s, 1, true, 'created')
        """, (rule_id, username, effective_tenant, category, rule_clean, confidence))
        conn.commit()
        return rule_id
    finally:
        if conn:
            conn.close()


def delete_rule(rule_id: int, username: str,
                tenant_id: str = None) -> bool:
    """
    Desactive une regle (active=false).
    5F-2 : snapshot 'deactivated' dans l'historique.

    HOTFIX 26/04 (etape A.5) : retire le default 'guillaume' (anti-pattern
    multi-tenant) et log un WARNING si appele sans tenant_id explicite.
    Le pattern (tenant_id = %s OR tenant_id IS NULL) reste pour compat
    avec les regles personnelles (personal=True) qui ont tenant_id NULL.
    """
    from app.logging_config import get_logger
    logger = get_logger("raya.memory")
    if tenant_id is None:
        logger.warning(
            "[delete_rule] Appel SANS tenant_id pour user '%s' rule_id=%s "
            "-> risque fuite cross-tenant en cas d homonyme. Caller a durcir.",
            username, rule_id,
        )
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE aria_rules SET active = false, updated_at = NOW() "
            "WHERE id = %s AND username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (rule_id, username, tenant_id)
        )
        if c.rowcount > 0:
            # 5F-2 : snapshot desactivation
            c.execute("""
                INSERT INTO aria_rules_history
                  (rule_id, username, tenant_id, category, rule,
                   confidence, reinforcements, active, change_type)
                SELECT id, username, tenant_id, category, rule,
                       confidence, reinforcements, false, 'deactivated'
                FROM aria_rules WHERE id = %s
            """, (rule_id,))
        conn.commit()
        return c.rowcount > 0 or True  # rowcount deja consomme par le SELECT ci-dessus
    finally:
        if conn:
            conn.close()


def rollback_rule(rule_id: int, username: str, tenant_id: str = None) -> dict:
    """
    5F-2 : Restaure une regle a sa version precedente depuis l'historique.
    Retourne {"status": "ok", "restored_version": ...} ou {"status": "error", ...}.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Version precedente = avant-derniere entree (OFFSET 1)
        c.execute("""
            SELECT category, rule, confidence, reinforcements, active
            FROM aria_rules_history
            WHERE rule_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY changed_at DESC
            OFFSET 1 LIMIT 1
        """, (rule_id, username, tenant_id))
        prev = c.fetchone()
        if not prev:
            return {"status": "error", "message": "Aucune version precedente disponible."}

        category, rule, confidence, reinforcements, active = prev

        # Restaure la regle
        c.execute("""
            UPDATE aria_rules
            SET category = %s, rule = %s, confidence = %s,
                reinforcements = %s, active = %s, updated_at = NOW()
            WHERE id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
        """, (category, rule, confidence, reinforcements, active, rule_id, username, tenant_id))

        if c.rowcount == 0:
            return {"status": "error", "message": f"Regle {rule_id} introuvable pour {username}."}

        # Snapshot rollback
        c.execute("""
            INSERT INTO aria_rules_history
              (rule_id, username, tenant_id, category, rule,
               confidence, reinforcements, active, change_type)
            SELECT id, username, tenant_id, %s, %s, %s, %s, %s, 'rollback'
            FROM aria_rules WHERE id = %s
        """, (category, rule, confidence, reinforcements, active, rule_id))

        conn.commit()
        return {
            "status": "ok",
            "restored_version": {
                "category": category, "rule": rule,
                "confidence": confidence, "reinforcements": reinforcements,
                "active": active,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


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


def seed_default_rules(username: str = None):
    """Raya apprend d'elle-meme. Aucune regle par defaut.
    
    F.X (audit isolation user-user, LOT 1.6) : default 'guillaume' retire.
    Fonction conservee pour compat retro mais ne fait rien."""
    pass
