"""
Dashboard service — regroupement et priorisation des mails.

Toute la logique de groupement et de priorité business est pilotée
par les règles Aria (catégorie regroupement) via rule_engine.
Aria fait évoluer ces règles via LEARN/FORGET.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from app.database import get_pg_conn
from app.rule_engine import get_rules_by_category, parse_business_priority


def normalize_text(text: str) -> str:
    if not text: return ""
    t = text.lower().strip()
    for p in ["re: ", "tr: ", "fw: ", "fwd: "]:
        changed = True
        while changed:
            changed = False
            if t.startswith(p):
                t = t[len(p):].strip()
                changed = True
    return t


def build_group_key(item: dict, regroupement_rules: list[str]) -> str:
    """
    Construit la clé de regroupement depuis les règles Aria.
    Chaque règle de regroupement peut définir un groupe spécifique.
    """
    title = normalize_text(item.get("display_title", ""))
    category = item.get("category", "autre")
    sender = (item.get("from_email") or "").lower()
    combined = f"{title} {sender} {category}"

    # Cherche une règle de regroupement spécifique
    for rule in regroupement_rules:
        rule_l = rule.lower()
        if "regrouper" not in rule_l:
            continue
        # Extrait les termes clés de la règle
        import re
        kw_part = re.sub(r"regrouper (les mails |les |)d[e']?", "", rule_l)
        kw_part = kw_part.split("=>")[0].split("→")[0].strip()
        keywords = [k.strip().strip("',") for k in kw_part.split(",")]
        if any(kw and len(kw) > 2 and kw in combined for kw in keywords):
            # Utilise la règle comme clé de groupe
            return f"rule|{kw_part[:40].strip()}"

    # Regroupement générique
    if category == "notification":
        return f"notification|{sender}"
    return f"{category}|{normalize_text(item.get('display_title', ''))}"


def choose_group_title(items: list[dict], regroupement_rules: list[str]) -> str:
    """Titre du groupe, enrichi par les règles si disponible."""
    first = items[0]
    title = normalize_text(first.get("display_title", ""))
    sender = (first.get("from_email") or "").lower()
    combined = f"{title} {sender}"

    for rule in regroupement_rules:
        rule_l = rule.lower()
        if "regrouper" not in rule_l:
            continue
        import re
        kw_part = re.sub(r"regrouper (les mails |les |)d[e']?", "", rule_l)
        kw_part = kw_part.split("=>")[0].split("→")[0].strip()
        keywords = [k.strip().strip("',") for k in kw_part.split(",")]
        if any(kw and len(kw) > 2 and kw in combined for kw in keywords):
            # Titre propre : capitalize chaque mot significatif
            return " ".join(w.capitalize() for w in kw_part.split() if len(w) > 2)[:50]

    if first.get("category") == "notification":
        return "Notifications"
    return first.get("display_title", "Sujet")


def choose_group_priority(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    if "haute" in priorities: return "haute"
    if "moyenne" in priorities: return "moyenne"
    return "basse"


def choose_group_reason(items: list[dict]) -> str:
    if len(items) == 1: return items[0].get("reason", "")
    cats = {item.get("category") for item in items}
    if "raccordement" in cats:
        return f"{len(items)} mails liés à un même sujet de raccordement."
    if cats == {"notification"}:
        return f"{len(items)} notifications regroupées."
    return f"{len(items)} mails liés au même sujet."


def choose_group_action(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    categories = [item.get("category") for item in items]
    if "haute" in priorities: return "Traiter rapidement"
    if "raccordement" in categories: return "Analyser et suivre"
    if "reunion" in categories: return "Vérifier et planifier"
    if all(cat == "notification" for cat in categories): return "Classer ou ignorer"
    return "Lire et qualifier"


def build_summary(items: list[dict]) -> str:
    texts = []
    for item in items[:2]:
        s = (item.get("short_summary") or "").strip()
        if s and s not in texts: texts.append(s)
    return " | ".join(texts)


def get_dashboard(days: int = 2, username: str = 'guillaume') -> dict:
    """
    Tableau de bord — piloté par les règles de regroupement d'Aria.
    Chaque utilisateur voit uniquement ses propres mails.
    """
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

    # Règles de regroupement d'Aria
    regroupement_rules = get_rules_by_category(username, "regroupement")

    groups = defaultdict(list)
    for row in rows:
        key = build_group_key(row, regroupement_rules)
        groups[key].append(row)

    grouped_items = []
    for _, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x["received_at"] or "", reverse=True)
        missing_fields = items_sorted[0].get("missing_fields")
        if not missing_fields:
            missing_fields = []
        elif isinstance(missing_fields, str):
            try: missing_fields = json.loads(missing_fields)
            except Exception: missing_fields = []

        grouped_items.append({
            "id": items_sorted[0].get("id"),
            "topic": choose_group_title(items_sorted, regroupement_rules),
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
    grouped_items.sort(key=lambda x: (
        priority_order.get(x["priority"], 99), x.get("latest_date") or ""
    ))

    urgent, normal, low = [], [], []
    for item in grouped_items:
        bp = parse_business_priority(item.get("category", ""), item.get("topic", ""), username)
        if bp == "urgent": urgent.append(item)
        elif bp == "faible": low.append(item)
        else: normal.append(item)

    return {
        "days": days,
        "username": username,
        "count": len(grouped_items),
        "urgent": urgent,
        "normal": normal,
        "low": low,
        "all": grouped_items,
    }
