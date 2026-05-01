"""
Handler Microsoft Graph mail + filtres (helpers de filtrage uniquement).
Extrait de webhook.py -- SPLIT-R3.

NOTE 01/05/2026 : ce module ne contient QUE des helpers de filtrage
(_get_mail_filter_rules, _matches_filter, _is_bulk_heuristic,
_is_spam_by_rules) et leurs constantes (_NOREPLY_PREFIXES,
_BULK_DOMAINS, _BULK_SUBJECT_KEYWORDS).

DEUX BUGS HISTORIQUES corriges le 01/05/2026 :

  Bug 1 — Import circulaire mortel
    L import top-level vers webhook_ms_handlers (process_incoming_mail,
    _process_mail) qui existait ici a ete supprime. Il etait vestigial
    (re-exposition de noms apres SPLIT-F7), aucun code du repo ne
    l utilisait. Mais il provoquait un import circulaire fatal :
        webhook.py lazy-import webhook_ms_handlers
          -> webhook_ms_handlers top-level import webhook_microsoft
            -> webhook_microsoft top-level import webhook_ms_handlers
              -> ImportError: cannot import name process_incoming_mail
                 from partially initialized module
    Cet import circulaire causait un 500 sur CHAQUE notification
    Microsoft Graph recue, donc ZERO mail Outlook ingere depuis
    ~17 jours.

  Bug 2 — Constantes dans le mauvais module
    _NOREPLY_PREFIXES, _BULK_DOMAINS, _BULK_SUBJECT_KEYWORDS sont
    utilisees par _is_bulk_heuristic() ci-dessous, mais etaient
    definies dans webhook.py (residu de la meme migration SPLIT-R3).
    Resultat : meme si le 500 n existait pas, l ingestion plantait
    avec NameError des qu un mail arrivait. Les constantes sont
    maintenant au bon endroit, juste avant les fonctions qui les
    utilisent.
"""
import json,re,threading
from datetime import datetime
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.logging_config import get_logger
logger=get_logger("raya.webhook.ms")


# ─── PATTERNS STATIQUES (filet de base) ───
# Deplaces depuis webhook.py le 01/05/2026 : ces constantes sont utilisees
# par _is_bulk_heuristic() ci-dessous, mais etaient definies dans webhook.py
# (residu de la migration SPLIT-R3). Les fonctions levaient donc NameError
# a chaque appel. Maintenant elles sont au bon endroit.

_NOREPLY_PREFIXES = (
    "noreply@", "no-reply@", "no_reply@", "donotreply@",
    "do-not-reply@", "mailer-daemon@", "postmaster@",
    "bounce@", "bounces@", "notifications@", "notification@",
    "newsletter@", "newsletters@", "alerts@", "alert@",
    "automated@", "auto@", "system@", "support-noreply@",
    "info@noreply.", "reply@",
)

_BULK_DOMAINS = (
    "sendgrid.net", "sendgrid.com", "mailchimp.com", "mandrillapp.com",
    "mailgun.org", "hubspot.com", "salesforce.com", "marketo.com",
    "constantcontact.com", "campaign-monitor.com", "klaviyo.com",
    "brevo.com", "sendinblue.com", "mailjet.com",
    "amazonses.com", "bounce.linkedin.com", "facebookmail.com",
    "twitter.com", "notifications.google.com",
)

_BULK_SUBJECT_KEYWORDS = (
    "unsubscribe", "se désabonner", "newsletter", "digest",
    "weekly recap", "rapport hebdomadaire", "monthly report",
    "invoice #", "facture n°", "receipt for", "reçu de",
    "your order", "votre commande", "order confirmation",
    "confirmation de commande", "tracking", "livraison",
    "automated message", "message automatique",
    "do not reply", "ne pas répondre",
    "verification code", "code de vérification",
    "one-time password", "mot de passe à usage unique",
)


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



