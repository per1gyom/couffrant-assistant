import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from app.database import get_pg_conn


def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    for p in ["re: ", "tr: ", "fw: ", "fwd: "]:
        while t.startswith(p):
            t = t[len(p):].strip()
    return t


def load_dashboard_rules(username: str = 'guillaume') -> dict:
    """
    Charge les règles de regroupement et d'urgence depuis aria_rules.
    Remplacement dynamique des constantes hardcodées de l'ancien dashboard_service.
    """
    try:
        from app.memory_manager import get_rules_by_category
        return {
            'urgence': get_rules_by_category('urgence', username),
            'regroupement': get_rules_by_category('regroupement', username),
            'tri_mails': get_rules_by_category('tri_mails', username),
        }
    except Exception:
        return {'urgence': [], 'regroupement': [], 'tri_mails': []}


def extract_kw(rule: str) -> list[str]:
    """Extrait les mots-clés d'une règle pour matching rapide."""
    try:
        from app.memory_manager import extract_keywords_from_rule
        return extract_keywords_from_rule(rule)
    except Exception:
        return []


def build_group_key(item: dict, rules: dict) -> str:
    """
    Construit la clé de regroupement.
    Piloté par les règles 'regroupement' d'Aria — plus de logique hardcodée.
    """
    title = normalize_text(item.get("display_title", ""))
    category = item.get("category", "autre")
    sender = (item.get("from_email") or "").lower()
    full_text = f"{title} {sender} {category}"

    # Appliquer les règles de regroupement Aria
    for rule in rules.get('regroupement', []):
        keywords = extract_kw(rule)
        for kw in keywords:
            if kw in full_text:
                return f"groupe|{kw}"

    # Regroupement par catégorie + extrémité du titre
    if category == "notification":
        return f"notification|{sender}"

    return f"{category}|{title[:50]}"


def compute_business_priority(item: dict, rules: dict) -> str:
    """
    Détermine la priorité métier.
    Piloté par les règles 'urgence' d'Aria — plus de logique hardcodée.
    """
    title = (item.get("topic") or "").lower()
    category = item.get("category") or ""
    priority = item.get("priority") or "moyenne"
    full_text = f"{title} {category}"

    # Priorité directe haute
    if priority == "haute":
        return "urgent"

    # Vérification via règles d'urgence Aria
    for rule in rules.get('urgence', []):
        keywords = extract_kw(rule)
        if any(kw in full_text for kw in keywords):
            return "urgent"

    # Priorité basse / notifications
    if category == "notification" or priority == "basse":
        return "faible"

    return "a_traiter"


def choose_group_title(items: list[dict]) -> str:
    return items[0].get("display_title", "Sujet")


def choose_group_action(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    categories = [item.get("category") for item in items]
    if "haute" in priorities:
        return "Traiter rapidement"
    if "raccordement" in categories:
        return "Analyser et suivre"
    if "reunion" in categories:
        return "Vérifier et planifier"
    if all(cat == "notification" for cat in categories):
        return "Classer ou ignorer"
    return "Lire et qualifier"


def choose_group_priority(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    if "haute" in priorities: return "haute"
    if "moyenne" in priorities: return "moyenne"
    return "basse"


def choose_group_reason(items: list[dict]) -> str:
    if len(items) == 1:
        return items[0].get("reason", "")
    cats = {item.get("category") for item in items}
    if "raccordement" in cats:
        return f"{len(items)} mails liés à un même sujet de raccordement."
    if cats == {"notification"}:
        return f"{len(items)} notifications similaires regroupées."
    return f"{len(items)} mails liés au même sujet."


def build_summary(items: list[dict]) -> str:
    texts = []
    for item in items[:2]:
        s = (item.get("short_summary") or "").strip()
        if s and s not in texts:
            texts.append(s)
    return " | ".join(texts)


def get_dashboard(days: int = 2, username: str = 'guillaume') -> dict:
    conn = get_pg_conn()
    c = conn.cursor()
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    c.execute("""
        SELECT id, message_id, received_at, from_email, display_title,
               category, priority, reason, suggested_action, short_summary,
               suggested_reply, response_type, missing_fields, confidence_level,
               raw_body_preview
        FROM mail_memory
        WHERE username = %s AND received_at >= %s
        ORDER BY received_at DESC
    """, (username, start_date))
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    # Charger les règles Aria une seule fois pour tout le dashboard
    rules = load_dashboard_rules(username)

    groups = defaultdict(list)
    for row in rows:
        groups[build_group_key(row, rules)].append(row)

    grouped_items = []
    for _, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x["received_at"] or "", reverse=True)
        missing_fields = items_sorted[0].get("missing_fields")
        if not missing_fields:
            missing_fields = []
        elif isinstance(missing_fields, str):
            try:
                missing_fields = json.loads(missing_fields)
            except Exception:
                missing_fields = []

        grouped_items.append({
            "id": items_sorted[0].get("id"),
            "topic": choose_group_title(items_sorted),
            "priority": choose_group_priority(items_sorted),
            "reason": choose_group_reason(items_sorted),
            "action": choose_group_action(items_sorted),
            "summary": build_summary(items_sorted),
            "mail_count": len(items_sorted),
            "latest_date": items_sorted[0].get("received_at"),
            "category": items_sorted[0].get("category"),
            "senders": list(dict.fromkeys([i.get("from_email") for i in items_sorted if i.get("from_email")])),
            "suggested_reply": items_sorted[0].get("suggested_reply"),
            "response_type": items_sorted[0].get("response_type"),
            "missing_fields": missing_fields,
            "confidence_level": items_sorted[0].get("confidence_level"),
            "raw_body_preview": items_sorted[0].get("raw_body_preview"),
        })

    priority_order = {"haute": 0, "moyenne": 1, "basse": 2}
    grouped_items.sort(key=lambda x: (priority_order.get(x["priority"], 99), x.get("latest_date") or ""))

    urgent, normal, low = [], [], []
    for item in grouped_items:
        bp = compute_business_priority(item, rules)
        if bp == "urgent": urgent.append(item)
        elif bp == "a_traiter": normal.append(item)
        else: low.append(item)

    return {"days": days, "count": len(grouped_items),
            "urgent": urgent, "normal": normal, "low": low, "all": grouped_items}
