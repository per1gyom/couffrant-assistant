"""
Rule Engine d'Aria — moteur de règles évolutif.

Module autonome : n'importe que database.py.
Toutes les règles métier viennent de aria_rules en base.
Seuls les garde-fous de sécurité restent dans le code.

Signatures canoniques :
  get_rules_by_category(username, category, tenant_id=None)
  get_memoire_param(username, param, default, tenant_id=None)

Le paramètre tenant_id est optionnel pour la compat ascendante.
Quand fourni, il est ajouté au filtre SQL pour l'isolation stricte.
"""

import re
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


# ─── CHARGEMENT DES RÈGLES ───

def get_rules_by_category(username: str, category: str,
                          tenant_id: str = None) -> list:
    """
    Retourne les règles actives d'un utilisateur pour une catégorie.
    Si tenant_id est fourni, filtre sur le tenant pour une isolation stricte.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute("""
                SELECT rule FROM aria_rules
                WHERE active = true
                  AND username = %s
                  AND category = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY confidence DESC, reinforcements DESC, created_at ASC
            """, (username, category, tenant_id))
        else:
            c.execute("""
                SELECT rule FROM aria_rules
                WHERE active = true AND username = %s AND category = %s
                ORDER BY confidence DESC, reinforcements DESC, created_at ASC
            """, (username, category))
        return [r[0] for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_rules_as_text(username: str, categories: list,
                      tenant_id: str = None) -> str:
    """
    Retourne les règles formatées pour injection dans un prompt.
    Format : "[catégorie] règle" par ligne.
    """
    lines = []
    for cat in categories:
        rules = get_rules_by_category(username, cat, tenant_id)
        for rule in rules:
            lines.append(f"[{cat}] {rule}")
    return "\n".join(lines)


def get_antispam_keywords(username: str, tenant_id: str = None) -> list:
    """
    Extrait les mots-clés anti-spam depuis les règles Aria.
    """
    rules = get_rules_by_category(username, "anti_spam", tenant_id)
    keywords = []
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    # Garde-fous absolus
    for absolute in ['mailer-daemon', 'noreply@', 'no-reply@']:
        if absolute not in keywords:
            keywords.append(absolute)
    return list(dict.fromkeys(keywords))


def get_contacts_keywords(username: str, tenant_id: str = None) -> list:
    """
    Retourne les noms/entités à détecter dans les conversations.
    Source 1 : aria_contacts (noms et parties locales des emails)
    Source 2 : règles contacts_cles de Raya
    """
    keywords = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute("""
                SELECT name, email FROM aria_contacts
                WHERE tenant_id = %s
                ORDER BY last_seen DESC LIMIT 50
            """, (tenant_id,))
        else:
            c.execute("SELECT name, email FROM aria_contacts ORDER BY last_seen DESC LIMIT 50")
        for name, email in c.fetchall():
            if name:
                for part in name.split():
                    part = part.strip().lower()
                    if len(part) > 2:
                        keywords.append(part)
            if email:
                local = email.split('@')[0].lower().strip()
                if len(local) > 2:
                    keywords.append(local)
    except Exception:
        pass
    finally:
        if conn: conn.close()

    for rule in get_rules_by_category(username, "contacts_cles", tenant_id):
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])

    return list(dict.fromkeys(keywords))


def get_memoire_param(username: str, param: str, default,
                      tenant_id: str = None):
    """
    Lit un paramètre numérique depuis les règles memoire.
    Format : "nom_param:valeur" ex: "synth_threshold:15"
    """
    rules = get_rules_by_category(username, "memoire", tenant_id)
    for rule in rules:
        if rule.strip().lower().startswith(f"{param.lower()}:"):
            try:
                value = rule.split(':', 1)[1].strip()
                return type(default)(value)
            except Exception:
                pass
    return default


def extract_category_keywords(username: str, target_category: str,
                               tenant_id: str = None) -> list:
    """
    Extrait les mots-clés liés à une catégorie depuis les règles tri_mails.
    """
    rules = get_rules_by_category(username, "tri_mails", tenant_id)
    keywords = []
    for rule in rules:
        rule_l = rule.lower()
        if target_category.lower() not in rule_l:
            continue
        found = re.findall(r"'([^']+)'", rule_l)
        if found:
            keywords.extend([k.strip() for k in found if len(k.strip()) > 2])
            continue
        match = re.search(r"contenant\s+(.+?)(?:\s*=|\s*$)", rule_l)
        if match:
            parts = [p.strip().strip("'\"") for p in match.group(1).split(',')]
            keywords.extend([p for p in parts if len(p) > 2])
    return list(dict.fromkeys(keywords))


def get_urgency_keywords(username: str, tenant_id: str = None) -> list:
    rules = get_rules_by_category(username, "urgence", tenant_id)
    keywords = []
    for rule in rules:
        rule_l = rule.lower()
        if "priorité haute" not in rule_l and "haute" not in rule_l:
            continue
        found = re.findall(r"'([^']+)'", rule_l)
        if found:
            keywords.extend([k.strip() for k in found if len(k.strip()) > 2])
            continue
        match = re.search(r"contenant\s+(.+?)(?:\s*=|\s*$)", rule_l)
        if match:
            parts = [p.strip() for p in match.group(1).split(',')]
            keywords.extend([p for p in parts if len(p) > 2])
    return list(dict.fromkeys(keywords))


def get_internal_domains(username: str, tenant_id: str = None) -> list:
    rules = get_rules_by_category(username, "tri_mails", tenant_id)
    domains = []
    for rule in rules:
        rule_l = rule.lower()
        if "interne" not in rule_l:
            continue
        parts = re.findall(r"[\w.-]+\.[a-z]{2,}", rule_l)
        domains.extend([p for p in parts if '.' in p and len(p) > 4])
    return domains if domains else ["couffrant-solar.fr"]


def parse_business_priority(category: str, title: str, username: str,
                             tenant_id: str = None) -> str:
    """
    Détermine la priorité business d'un groupe de mails depuis les règles.
    Retourne : 'urgent', 'a_traiter', 'faible'
    """
    rules = get_rules_by_category(username, "regroupement", tenant_id)
    cat_l = (category or "").lower()
    title_l = (title or "").lower()
    combined = f"{cat_l} {title_l}"

    for rule in rules:
        rule_l = rule.lower()
        if "=" not in rule_l and "\u2192" not in rule_l:
            continue
        sep = "\u2192" if "\u2192" in rule_l else "="
        parts = rule_l.split(sep, 1)
        if len(parts) < 2:
            continue
        condition, outcome = parts[0].strip(), parts[1].strip()

        match = False
        if "catégorie" in condition or "category" in condition:
            cat_ref = re.sub(r"cat[eé]gorie\s*", "", condition).strip().strip("'\",")
            if cat_ref and cat_ref in cat_l:
                match = True
        elif "contenant" in condition:
            kw_part = condition.split("contenant")[-1]
            kws = [k.strip().strip("'\",") for k in kw_part.split(",")]
            if any(kw and len(kw) > 2 and kw in title_l for kw in kws):
                match = True
        else:
            kws = [k.strip().strip("'\",") for k in condition.split(",")]
            if any(kw and len(kw) > 2 and kw in combined for kw in kws):
                match = True

        if match:
            if "urgent" in outcome:
                return "urgent"
            if "faible" in outcome or "basse" in outcome or "low" in outcome:
                return "faible"
            if "traiter" in outcome or "normale" in outcome or "moyen" in outcome:
                return "a_traiter"

    # Défauts si aucune règle ne s'applique
    if cat_l in ("raccordement", "consuel"):
        return "urgent"
    if cat_l == "financier":
        return "urgent" if "relance" in title_l or "retard" in title_l else "a_traiter"
    if cat_l == "notification":
        return "faible"
    return "a_traiter"
