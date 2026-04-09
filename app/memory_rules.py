"""
mémoire : règles et paramètres (aria_rules).
Isolation par username.
"""
from app.database import get_pg_conn


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
              confidence: float = 0.7, username: str = 'guillaume') -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_rules
            WHERE active = true AND username = %s AND category = %s AND rule ILIKE %s
            LIMIT 1
        """, (username, category, f"%{rule[:40]}%"))
        existing = c.fetchone()
        if existing:
            c.execute("""
                UPDATE aria_rules
                SET reinforcements = reinforcements + 1,
                    confidence = LEAST(1.0, confidence + 0.1), updated_at = NOW()
                WHERE id = %s
            """, (existing[0],))
            conn.commit()
            return existing[0]
        c.execute("""
            INSERT INTO aria_rules (username, category, rule, source, confidence)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (username, category, rule, source, confidence))
        rule_id = c.fetchone()[0]
        conn.commit()
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


def get_rules_by_category(category: str, username: str = 'guillaume') -> list:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rule FROM aria_rules
            WHERE active = true AND username = %s AND category = %s
            ORDER BY confidence DESC, reinforcements DESC
        """, (username, category))
        return [row[0] for row in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_rules_as_text(categories: list, username: str = 'guillaume') -> str:
    all_rules = []
    for cat in categories:
        for r in get_rules_by_category(cat, username):
            all_rules.append(f"[{cat}] {r}")
    return "\n".join(all_rules) if all_rules else ""


def get_antispam_keywords(username: str = 'guillaume') -> list:
    rules = get_rules_by_category('anti_spam', username)
    keywords = []
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    for kw in ['mailer-daemon', 'noreply@', 'no-reply@']:
        if kw not in keywords:
            keywords.append(kw)
    return list(dict.fromkeys(keywords))


def get_memoire_param(param: str, default, username: str = 'guillaume'):
    rules = get_rules_by_category('memoire', username)
    for rule in rules:
        if rule.strip().lower().startswith(f"{param.lower()}:"):
            try:
                value = rule.split(':', 1)[1].strip()
                return type(default)(value)
            except Exception:
                pass
    return default


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
