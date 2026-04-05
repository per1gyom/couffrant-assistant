import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from app.config import ASSISTANT_DB_PATH

DB_PATH = ASSISTANT_DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    prefixes = ["re: ", "tr: ", "fw: ", "fwd: "]
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if t.startswith(p):
                t = t[len(p):].strip()
                changed = True
    return t


def build_group_key(item: dict) -> str:
    title = normalize_text(item.get("display_title", ""))
    category = item.get("category", "autre")
    sender = (item.get("from_email") or "").lower()

    if category == "raccordement":
        if "enedis" in title or "engie" in title:
            return "raccordement|enedis-engie"
        return f"raccordement|{title}"

    if (
        "rt connecting" in title
        or "rt-connecting" in title
        or "rt-connecting" in sender
        or "rt-connecting.fr" in sender
    ):
        return "business|rt-connecting"

    if "adiwatt" in title or "webinair" in title or "webinaire" in title:
        return "interne|adiwatt"

    if category == "notification":
        return f"notification|{sender}"

    return f"{category}|{title}"


def choose_group_title(items: list[dict]) -> str:
    first = items[0]
    key_text = " ".join(
        [
            normalize_text(first.get("display_title", "")),
            (first.get("from_email") or "").lower(),
            first.get("category", ""),
        ]
    )

    if "rt connecting" in key_text or "rt-connecting" in key_text:
        return "RT Connecting"
    if "enedis" in key_text or "engie" in key_text:
        return "Raccordement ENEDIS / ENGIE"
    if "adiwatt" in key_text or "webinair" in key_text or "webinaire" in key_text:
        return "Webinaire AdiWatt"
    if first.get("category") == "notification":
        return "Notifications"

    return first.get("display_title", "Sujet")


def choose_group_action(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    categories = [item.get("category") for item in items]

    if "haute" in priorities:
        return "Traiter rapidement"
    if "raccordement" in categories:
        return "Analyser et suivre"
    if "reunion" in categories:
        return "Vérifier et planifier"
    if "interne" in categories:
        return "Relire si suivi nécessaire"
    if all(cat == "notification" for cat in categories):
        return "Classer ou ignorer"

    return "Lire et qualifier"


def choose_group_priority(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    if "haute" in priorities:
        return "haute"
    if "moyenne" in priorities:
        return "moyenne"
    return "basse"


def choose_group_reason(items: list[dict]) -> str:
    if len(items) == 1:
        return items[0].get("reason", "")

    cats = {item.get("category") for item in items}
    if "raccordement" in cats:
        return f"{len(items)} mails liés à un même sujet de raccordement."
    if "reunion" in cats:
        return f"{len(items)} mails liés à un même échange de réunion."
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


def get_dashboard(days: int = 2) -> dict:
    conn = get_conn()
    c = conn.cursor()

    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

    c.execute("""
        SELECT
            id,
            message_id,
            received_at,
            from_email,
            display_title,
            category,
            priority,
            reason,
            suggested_action,
            short_summary,
            suggested_reply,
            response_type,
            missing_fields,
            confidence_level,
            raw_body_preview
        FROM mail_memory
        WHERE received_at >= ?
        ORDER BY received_at DESC
    """, (start_date,))

    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    groups = defaultdict(list)
    for row in rows:
        groups[build_group_key(row)].append(row)

    grouped_items = []
    for _, items in groups.items():
        items_sorted = sorted(
            items,
            key=lambda x: x["received_at"] or "",
            reverse=True,
        )

        missing_fields = items_sorted[0].get("missing_fields")
        if not missing_fields:
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
    grouped_items.sort(
        key=lambda x: (priority_order.get(x["priority"], 99), x.get("latest_date") or ""),
        reverse=False,
    )

    def compute_business_priority(item: dict) -> str:
        title = (item.get("topic") or "").lower()
        category = item.get("category") or ""

        if category == "raccordement":
            return "urgent"

        if "commande" in title or "retard" in title or "annulation" in title:
            return "urgent"

        if category in ["reunion", "interne", "commercial"]:
            return "a_traiter"

        if category == "notification":
            return "faible"

        return "a_traiter"

    urgent = []
    normal = []
    low = []

    for item in grouped_items:
        business_priority = compute_business_priority(item)

        if business_priority == "urgent":
            urgent.append(item)
        elif business_priority == "a_traiter":
            normal.append(item)
        else:
            low.append(item)

    return {
        "days": days,
        "count": len(grouped_items),
        "urgent": urgent,
        "normal": normal,
        "low": low,
        "all": grouped_items,
    }