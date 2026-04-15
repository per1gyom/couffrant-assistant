"""
Handler Microsoft Graph mail + filtres.
Extrait de webhook.py -- SPLIT-R3.
"""
import json,re,threading
from datetime import datetime
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.logging_config import get_logger
from app.routes.webhook_ms_handlers import process_incoming_mail,_process_mail  # noqa
logger=get_logger("raya.webhook.ms")


def _get_mail_filter_rules(username: str) -> tuple:
    try:
        from app.memory_rules import get_rules_by_category
        rules = get_rules_by_category('mail_filter', username)
        whitelist, blacklist = [], []
        for rule in rules:
            rl = rule.strip().lower()
            if rl.startswith('autoriser:'):
                whitelist.append(rl[10:].strip())
            elif rl.startswith('bloquer:'):
                blacklist.append(rl[8:].strip())
        return whitelist, blacklist
    except Exception:
        return [], []



def _matches_filter(sender: str, subject: str, patterns: list) -> bool:
    sender_l = sender.lower()
    subject_l = (subject or "").lower()
    for pattern in patterns:
        if pattern.startswith('@'):
            if sender_l.endswith(pattern):
                return True
        elif pattern.startswith('sujet:'):
            kw = pattern[6:].strip()
            if kw and kw in subject_l:
                return True
        else:
            if pattern in sender_l:
                return True
    return False



def _is_bulk_heuristic(sender: str, subject: str, preview: str) -> bool:
    sender_lower = sender.lower()
    subject_lower = (subject or "").lower()
    if any(sender_lower.startswith(p) for p in _NOREPLY_PREFIXES):
        return True
    domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
    if any(bulk in domain for bulk in _BULK_DOMAINS):
        return True
    if any(kw in subject_lower for kw in _BULK_SUBJECT_KEYWORDS):
        return True
    preview_lower = (preview or "").lower()
    if "list-unsubscribe" in preview_lower or "view in browser" in preview_lower:
        return True
    return False



def _is_spam_by_rules(sender: str, subject: str, preview: str, username: str) -> bool:
    try:
        from app.memory_rules import get_antispam_keywords
        keywords = get_antispam_keywords(username)
        text = f"{sender} {subject} {preview}".lower()
        return any(kw in text for kw in keywords if kw)
    except Exception:
        return False



