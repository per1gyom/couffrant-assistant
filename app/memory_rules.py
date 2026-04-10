"""
Mémoire : règles et paramètres (aria_rules).
Isolation par username.

Fonctions canoniques à utiliser :
  app.rule_engine.get_rules_by_category(username, category)
  app.rule_engine.get_memoire_param(username, param, default)
  app.memory_rules.save_rule(category, rule, source, confidence, username)  ← username OBLIGATOIRE

Les fonctions get_rules_by_category et get_memoire_param de ce module sont dépréciées.
Elles existent uniquement pour la compat ascendante et délèguent vers rule_engine.
"""
import warnings
from app.database import get_pg_conn


# ─── FONCTIONS ACTIVES ───

def get_aria_rules(username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true AND username = %s AND category != 'memoire'
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 60
        """, (username,))
        rows = c.fetchall()
        if not rows: return ""
        return "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows])
    finally:
        if conn: conn.close()


def save_rule(category: str, rule: str, source: str = "auto",
              confidence: float = 0.7, username: str = None) -> int:
    """
    Sauvegarde une règle apprise par Raya.
    Déduplication par égalité exacte normalisée (LOWER+TRIM) — plus de ILIKE %prefix%.
    username obligatoire — plus de défaut 'guillaume'.
    """
    if not username:
        raise ValueError("save_rule : username obligatoire (plus de défaut 'guillaume')")
    if not rule or not rule.strip():
        raise ValueError("save_rule : règle vide refusée")

    rule_clean = rule.strip()

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Égalité exacte normalisée — empêche la fusion de règles contradictoires
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
            print(f"[save_rule] RENFORCÉ id={existing[0]} [{category}] '{rule_clean[:50]}'")
            return existing[0]

        c.execute("""
            INSERT INTO aria_rules (username, category, rule, source, confidence)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (username, category, rule_clean, source, confidence))
        rule_id = c.fetchone()[0]
        conn.commit()
        print(f"[save_rule] CRÉÉ id={rule_id} [{category}] '{rule_clean[:50]}'")
        return rule_id
    finally:
        if conn: conn.close()


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


def seed_default_rules(username: str = 'guillaume'):
    """Raya apprend d'elle-même. Aucune règle par défaut."""
    pass


# ─── WRAPPERS DÉPRÉCIÉS (compat ascendante) ───
# Étapez 2 — B4 : les fonctions canoniques vivent dans app.rule_engine.
# Ces wrappers détectent l'ordre des arguments et délèguent proprement.

_KNOWN_CATEGORIES = {
    'tri_mails', 'urgence', 'anti_spam', 'style_reponse', 'regroupement',
    'contacts_cles', 'categories_mail', 'memoire', 'mail_filter',
    'comportement', 'drive_pv', 'affichage', 'teams_ingestion',
}


def get_rules_by_category(username_or_category=None, category_or_username='guillaume') -> list:
    """
    DÉPRÉCIÉ — Utiliser app.rule_engine.get_rules_by_category(username, category).
    Détecte l'ordre des arguments et délègue à la fonction canonique.
    """
    warnings.warn(
        "app.memory_rules.get_rules_by_category est déprécié. "
        "Utiliser app.rule_engine.get_rules_by_category(username, category).",
        DeprecationWarning,
        stacklevel=2,
    )
    if username_or_category in _KNOWN_CATEGORIES:
        # Ancien ordre détecté : (category, username)
        category = username_or_category
        username = category_or_username
    else:
        # Nouvel ordre : (username, category)
        username = username_or_category
        category = category_or_username
    from app.rule_engine import get_rules_by_category as canonical
    return canonical(username, category)


def get_memoire_param(username_or_param=None, param_or_default=None, default_or_username=None):
    """
    DÉPRÉCIÉ — Utiliser app.rule_engine.get_memoire_param(username, param, default).
    Lève TypeError si l'ancien ordre (param, default, username) est détecté.
    """
    warnings.warn(
        "app.memory_rules.get_memoire_param est déprécié. "
        "Utiliser app.rule_engine.get_memoire_param(username, param, default).",
        DeprecationWarning,
        stacklevel=2,
    )
    # Détection de l'ancien ordre : si le premier arg a _ et est court, c'est un nom de param
    if isinstance(username_or_param, str) and "_" in username_or_param and len(username_or_param) < 30:
        raise TypeError(
            f"Appel ambigu à get_memoire_param : '{username_or_param}' ressemble à un nom de paramètre, "
            f"pas à un username. Utiliser l'ordre canonique : (username, param, default)."
        )
    from app.rule_engine import get_memoire_param as canonical
    return canonical(username_or_param, param_or_default, default_or_username)


def get_rules_as_text(categories: list, username: str = 'guillaume') -> str:
    """Wrapper pour compat — délègue à rule_engine."""
    from app.rule_engine import get_rules_by_category as canonical
    all_rules = []
    for cat in categories:
        for r in canonical(username, cat):
            all_rules.append(f"[{cat}] {r}")
    return "\n".join(all_rules) if all_rules else ""


def get_antispam_keywords(username: str = 'guillaume') -> list:
    from app.rule_engine import get_rules_by_category as canonical
    rules = canonical(username, 'anti_spam')
    keywords = []
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    for kw in ['mailer-daemon', 'noreply@', 'no-reply@']:
        if kw not in keywords:
            keywords.append(kw)
    return list(dict.fromkeys(keywords))
