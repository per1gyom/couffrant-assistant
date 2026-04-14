"""
Dashboard service — regroupement et priorisation des mails.

Toute la logique de groupement et de priorite business est pilotee
par les regles Aria (categorie regroupement) via rule_engine.
Aria fait evoluer ces regles via LEARN/FORGET.
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
    title = normalize_text(item.get("display_title", ""))
    category = item.get("category", "autre")
    sender = (item.get("from_email") or "").lower()
    combined = f"{title} {sender} {category}"

    for rule in regroupement_rules:
        rule_l = rule.lower()
        if "regrouper" not in rule_l:
            continue
        import re
        kw_part = re.sub(r"regrouper (les mails |les |)d[e']?", "", rule_l)
        kw_part = kw_part.split("=>")[0].split("\u2192")[0].strip()
        keywords = [k.strip().strip("',") for k in kw_part.split(",")]
        if any(kw and len(kw) > 2 and kw in combined for kw in keywords):
            return f"rule|{kw_part[:40].strip()}"

    if category == "notification":
        return f"notification|{sender}"
    return f"{category}|{normalize_text(item.get('display_title', ''))}"


def choose_group_title(items: list[dict], regroupement_rules: list[str]) -> str:
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
        kw_part = kw_part.split("=>")[0].split("\u2192")[0].strip()
        keywords = [k.strip().strip("',") for k in kw_part.split(",")]
        if any(kw and len(kw) > 2 and kw in combined for kw in keywords):
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
        return f"{len(items)} mails lies a un meme sujet de raccordement."
    if cats == {"notification"}:
        return f"{len(items)} notifications regroupees."
    return f"{len(items)} mails lies au meme sujet."


def choose_group_action(items: list[dict]) -> str:
    priorities = [item.get("priority") for item in items]
    categories = [item.get("category") for item in items]
    if "haute" in priorities: return "Traiter rapidement"
    if "raccordement" in categories: return "Analyser et suivre"
    if "reunion" in categories: return "Verifier et planifier"
    if all(cat == "notification" for cat in categories): return "Classer ou ignorer"
    return "Lire et qualifier"


def build_summary(items: list[dict]) -> str:
    texts = []
    for item in items[:2]:
        s = (item.get("short_summary") or "").strip()
        if s and s not in texts: texts.append(s)
    return " | ".join(texts)

# Retrocompatibilite
from app.dashboard_queries import get_dashboard, get_costs_dashboard  # noqa
