"""
Mailbox Manager — résolution automatique des connecteurs pour un utilisateur.

get_user_mailboxes(username) retourne la liste de tous les MailboxConnector
actifs pour cet utilisateur, qu'ils soient Microsoft, Gmail, ou tout autre
provider ajouté à l'avenir.

Ordre de priorité :
  1. Connexions V2 (tenant_connections via connection_assignments) — multi-tenant
  2. Fallback legacy (oauth_tokens) — per-user

Pour ajouter un nouveau provider :
  1. Créer une classe héritant de MailboxConnector dans connectors/
  2. L'enregistrer dans PROVIDER_MAP ci-dessous
  C'est tout.
"""
from __future__ import annotations
from app.connectors.mailbox_connector import MailboxConnector
from app.logging_config import get_logger

logger = get_logger("raya.mailbox_manager")


# ─── REGISTRE DES PROVIDERS ────────────────────────────────────────
# Pour ajouter un provider : ajouter une entrée ici + créer la classe.

def _get_provider_map() -> dict:
    """Lazy import pour éviter les imports circulaires."""
    from app.connectors.microsoft_connector import MicrosoftConnector
    from app.connectors.gmail_connector2 import GmailConnector
    return {
        "microsoft": MicrosoftConnector,
        "outlook":   MicrosoftConnector,
        "gmail":     GmailConnector,
        "google":    GmailConnector,
        # "yahoo": YahooConnector,  # futur
    }


# ─── RÉSOLUTION PRINCIPALE ─────────────────────────────────────────

def get_user_mailboxes(username: str) -> list[MailboxConnector]:
    """
    Retourne tous les connecteurs actifs pour un utilisateur.
    Auto-détecte les connexions V2 + fallback legacy.
    Aucune modification de code nécessaire pour ajouter une boîte.
    """
    connectors = []
    seen_emails = set()
    provider_map = _get_provider_map()

    # 1. Connexions V2 (tenant_connections)
    try:
        from app.connection_token_manager import get_user_tool_connections
        v2 = get_user_tool_connections(username)
        for tool_type, info in v2.items():
            cls = provider_map.get(tool_type.lower())
            if not cls:
                continue
            token = info.get("token", "")
            email = info.get("email", "")
            if not token:
                continue
            if email in seen_emails:
                continue
            seen_emails.add(email)
            connectors.append(cls(username=username, email=email, token=token))
            logger.debug("[MailboxMgr] V2 connector: %s (%s)", tool_type, email)
    except Exception as e:
        logger.warning("[MailboxMgr] V2 error: %s", e)

    # 2. Fallback legacy — Microsoft (oauth_tokens provider='microsoft')
    try:
        from app.token_manager import get_valid_microsoft_token
        from app.connectors.microsoft_connector import MicrosoftConnector
        ms_token = get_valid_microsoft_token(username)
        if ms_token:
            ms_email = _get_legacy_ms_email(username)
            if ms_email not in seen_emails:
                seen_emails.add(ms_email)
                connectors.append(MicrosoftConnector(username=username, email=ms_email, token=ms_token))
                logger.debug("[MailboxMgr] Legacy MS connector: %s", ms_email)
    except Exception as e:
        logger.warning("[MailboxMgr] Legacy MS error: %s", e)

    # 3. Fallback legacy — Gmail (oauth_tokens provider='google')
    try:
        from app.token_manager import get_valid_google_token
        from app.connectors.gmail_connector2 import GmailConnector
        g_token = get_valid_google_token(username)
        if g_token:
            g_email = _get_legacy_gmail_email(username)
            if g_email not in seen_emails:
                seen_emails.add(g_email)
                connectors.append(GmailConnector(username=username, email=g_email, token=g_token))
                logger.debug("[MailboxMgr] Legacy Gmail connector: %s", g_email)
    except Exception as e:
        logger.warning("[MailboxMgr] Legacy Gmail error: %s", e)

    logger.info("[MailboxMgr] %s: %d connecteur(s) actif(s)", username, len(connectors))
    return connectors


def get_mailbox_summary(username: str) -> str:
    """
    Retourne un résumé lisible des boîtes connectées pour le prompt Raya.
    Ex: "Outlook (contact@couffrant.fr), Gmail (per1.guillaume@gmail.com)"
    """
    mailboxes = get_user_mailboxes(username)
    if not mailboxes:
        return "Aucune boîte mail connectée."
    return ", ".join(m.display_name for m in mailboxes)


# ─── RECHERCHE UNIFIÉE ─────────────────────────────────────────────

def search_contacts_all(username: str, query: str) -> list[dict]:
    """
    Recherche dans TOUS les connecteurs de l'utilisateur.
    Retourne une liste dédupliquée de contacts.
    """
    results = []
    seen_emails = set()
    for connector in get_user_mailboxes(username):
        try:
            contacts = connector.search_contacts(query)
            for c in contacts:
                key = c.email.lower() if c.email else c.name.lower()
                if key and key not in seen_emails:
                    seen_emails.add(key)
                    results.append({
                        "name": c.name, "email": c.email,
                        "phone": c.phone, "source": c.source,
                    })
        except Exception as e:
            logger.warning("[MailboxMgr] search_contacts error (%s): %s", connector.provider, e)
    return results


def create_contact_best(username: str, name: str, email: str, phone: str = "") -> dict:
    """
    Crée un contact dans le connecteur le plus adapté.
    Préfère Gmail (contacts personnels), sinon Microsoft.
    """
    mailboxes = get_user_mailboxes(username)
    # Priorité : Gmail > Microsoft
    for connector in sorted(mailboxes, key=lambda c: 0 if c.provider == "gmail" else 1):
        result = connector.create_contact(name, email, phone)
        if result.get("ok"):
            return result
    return {"ok": False, "message": "Aucun connecteur disponible pour créer le contact."}


# ─── HELPERS LEGACY ────────────────────────────────────────────────

def _get_legacy_ms_email(username: str) -> str:
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT email FROM users WHERE username=%s LIMIT 1", (username,))
        row = c.fetchone(); conn.close()
        if row and row[0] and "raya-ia.fr" not in (row[0] or ""):
            return row[0]
    except Exception:
        pass
    return ""


def _get_legacy_gmail_email(username: str) -> str:
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT email FROM gmail_tokens WHERE username=%s LIMIT 1", (username,))
        row = c.fetchone(); conn.close()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""
