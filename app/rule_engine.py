"""
Rule Engine d'Aria — moteur de règles évolutif.

Module autonome : n'importe que database.py.
Peut être importé par ai_client.py, assistant_analyzer.py, dashboard_service.py,
main.py sans risque d'import circulaire avec memory_manager.

Toutes les règles métier d'Aria viennent de aria_rules en base.
Seuls les garde-fous de sécurité restent dans le code.

Catégories de règles :
  tri_mails      — classification des mails entrants (catégorie, priorité)
  urgence        — critères de priorité haute
  anti_spam      — mots-clés/domaines à filtrer (1 règle = une liste CSV)
  style_reponse  — style des réponses suggérées
  regroupement   — logique de groupement du dashboard
  contacts_cles  — contacts à surveiller dans les conversations
  memoire        — paramètres numériques (format "param:valeur")
  comportement   — comportement général d'Aria
"""

import re
from app.database import get_pg_conn


# ────────────────────────────────────────
# Chargement des règles
# ────────────────────────────────────────

def get_rules_by_category(username: str, category: str) -> list[str]:
    """
    Retourne les règles actives d'un utilisateur pour une catégorie.
    Retourne une liste vide si aucune règle n'existe (les modules appelants
    appliquent alors leur logique par défaut ou les seeds).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
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


def get_rules_as_text(username: str, categories: list[str]) -> str:
    """
    Retourne les règles formatées pour injection dans un prompt Claude.
    Format : "[catégorie] règle" par ligne.
    """
    lines = []
    for cat in categories:
        rules = get_rules_by_category(username, cat)
        for rule in rules:
            lines.append(f"[{cat}] {rule}")
    return "\n".join(lines)


def get_antispam_keywords(username: str) -> list[str]:
    """
    Extrait les mots-clés/domaines anti-spam depuis les règles Aria.
    Chaque règle anti_spam est une liste CSV de mots-clés.
    Aria ajoute un domaine via [ACTION:LEARN:anti_spam|nouveau.domaine.com, autre_mot].
    """
    rules = get_rules_by_category(username, "anti_spam")
    keywords = []
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    # Garde-fous absolus : toujours filtrés quelle que soit la config
    for absolute in ['mailer-daemon', 'noreply@', 'no-reply@']:
        if absolute not in keywords:
            keywords.append(absolute)
    return list(dict.fromkeys(keywords))


def get_contacts_keywords(username: str) -> list[str]:
    """
    Retourne les noms/entités à détecter dans les conversations.
    Source 1 : aria_contacts (noms et parties locales des emails)
    Source 2 : règles contacts_cles d'Aria
    Fallback : liste statique si les tables sont vides (démarrage)
    """
    keywords = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
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

    for rule in get_rules_by_category(username, "contacts_cles"):
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])

    # Fallback si aria_contacts vide (premier démarrage)
    if not keywords:
        keywords = ["arlène", "arlene", "sabrina", "benoit", "pierre", "maxence",
                    "charlotte", "pinto", "enedis", "consuel", "adiwatt",
                    "socotec", "triangle", "eleria", "edf"]

    return list(dict.fromkeys(keywords))


def get_memoire_param(username: str, param: str, default):
    """
    Lit un paramètre numérique depuis les règles memoire.
    Format : "nom_param:valeur" ex: "synth_threshold:15"
    Aria modifie ces valeurs via [ACTION:LEARN:memoire|synth_threshold:20]
    """
    rules = get_rules_by_category(username, "memoire")
    for rule in rules:
        if rule.strip().lower().startswith(f"{param.lower()}:"):
            try:
                value = rule.split(':', 1)[1].strip()
                return type(default)(value)
            except Exception:
                pass
    return default


def extract_category_keywords(username: str, target_category: str) -> list[str]:
    """
    Extrait les mots-clés liés à une catégorie depuis les règles tri_mails.
    Cherche les termes entre guillemets simples, ou après 'contenant'.
    Utilisé par l'analyseur de fallback (sans Claude).
    """
    rules = get_rules_by_category(username, "tri_mails")
    keywords = []
    for rule in rules:
        rule_l = rule.lower()
        if target_category.lower() not in rule_l:
            continue
        # Termes entre guillemets simples
        found = re.findall(r"'([^']+)'", rule_l)
        if found:
            keywords.extend([k.strip() for k in found if len(k.strip()) > 2])
            continue
        # Fallback : après 'contenant' jusqu'à '=' ou fin
        match = re.search(r"contenant\s+(.+?)(?:\s*=|\s*$)", rule_l)
        if match:
            parts = [p.strip().strip("'\"") for p in match.group(1).split(',')]
            keywords.extend([p for p in parts if len(p) > 2])
    return list(dict.fromkeys(keywords))


def get_urgency_keywords(username: str) -> list[str]:
    """
    Extrait les mots-clés d'urgence depuis les règles urgence.
    """
    rules = get_rules_by_category(username, "urgence")
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


def get_internal_domains(username: str) -> list[str]:
    """
    Extrait les domaines internes depuis les règles tri_mails.
    """
    rules = get_rules_by_category(username, "tri_mails")
    domains = []
    for rule in rules:
        rule_l = rule.lower()
        if "interne" not in rule_l:
            continue
        # Cherche les domaines (contiennent un point)
        parts = re.findall(r"[\w.-]+\.[a-z]{2,}", rule_l)
        domains.extend([p for p in parts if '.' in p and len(p) > 4])
    return domains if domains else ["couffrant-solar.fr"]


def parse_business_priority(category: str, title: str, username: str) -> str:
    """
    Détermine la priorité business d'un groupe de mails depuis les règles.
    Retourne : 'urgent', 'a_traiter', 'faible'
    Utilisé par dashboard_service.
    """
    rules = get_rules_by_category(username, "regroupement")
    cat_l = (category or "").lower()
    title_l = (title or "").lower()
    combined = f"{cat_l} {title_l}"

    for rule in rules:
        rule_l = rule.lower()
        if "=" not in rule_l and "→" not in rule_l:
            continue
        sep = "→" if "→" in rule_l else "="
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
    if cat_l == "raccordement" or cat_l == "consuel":
        return "urgent"
    if cat_l in ("financier",):
        return "urgent" if "relance" in title_l or "retard" in title_l else "a_traiter"
    if cat_l == "notification":
        return "faible"
    return "a_traiter"
