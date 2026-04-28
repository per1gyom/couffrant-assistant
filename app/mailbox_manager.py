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

    Audit multi-boites 28/04 : utilise get_all_user_connections (LISTE)
    au lieu de get_user_tool_connections (DICT) pour ne pas ecraser
    quand l user a plusieurs connexions du meme tool_type (ex: 6 Gmail).
    """
    connectors = []
    seen_emails = set()
    provider_map = _get_provider_map()

    # Connexions V2 (tenant_connections) — source de vérité unique
    # On itere sur la LISTE complete (multi-boites) au lieu du dict
    # qui ecrasait silencieusement.
    try:
        from app.connection_token_manager import get_all_user_connections
        v2_list = get_all_user_connections(username)
        for info in v2_list:
            tool_type = info.get("tool_type", "")
            cls = provider_map.get(tool_type.lower())
            if not cls:
                continue
            token = info.get("token", "")
            email = info.get("email", "")
            if not token:
                continue
            # Dedup par email pour eviter doublons (ex: 2 connexions au meme
            # gmail recree par erreur). Si pas d'email, on dedup par
            # connection_id pour ne pas tout fusionner.
            dedup_key = email.lower() if email else f"conn_{info.get('connection_id')}"
            if dedup_key in seen_emails:
                continue
            seen_emails.add(dedup_key)
            connectors.append(cls(username=username, email=email, token=token))
            logger.debug("[MailboxMgr] connector: %s (%s)", tool_type, email)
    except Exception as e:
        logger.warning("[MailboxMgr] erreur résolution connecteurs: %s", e)

    if not connectors:
        logger.info("[MailboxMgr] %s: aucun connecteur — migration requise ou boîtes non configurées.", username)
    else:
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

def load_agenda_all(username: str, days: int = 7) -> list[dict]:
    """
    Charge les événements de TOUS les calendriers connectés.
    Retourne une liste triée par date, avec source et calendar_email.
    """
    all_events = []
    for connector in get_user_mailboxes(username):
        try:
            events = connector.get_agenda(days=days)
            for e in events:
                all_events.append({
                    "id":             e.id,
                    "title":          e.title,
                    "start":          e.start,
                    "end":            e.end,
                    "location":       e.location,
                    "description":    e.description,
                    "attendees":      e.attendees,
                    "all_day":        e.all_day,
                    "source":         e.source,
                    "calendar_email": e.calendar_email,
                })
        except Exception as ex:
            logger.warning("[MailboxMgr] get_agenda error (%s): %s", connector.provider, ex)
    # Trier par date de début
    all_events.sort(key=lambda e: e.get("start", "") or "")
    return all_events


def execute_calendar_action(
    username: str,
    action: str,
    provider_hint: str = "",
    **kwargs,
) -> dict:
    """
    Exécute une action calendrier sur le bon connecteur.
    provider_hint : 'microsoft' | 'gmail' | '' (auto = premier disponible)
    action : 'create' | 'update' | 'delete'
    """
    mailboxes = get_user_mailboxes(username)
    if not mailboxes:
        return {"ok": False, "message": "Aucun calendrier connecté."}

    # Choisir le bon connecteur
    connector = None
    if provider_hint:
        for m in mailboxes:
            if m.provider == provider_hint or m.email == provider_hint:
                connector = m
                break
    if not connector:
        connector = mailboxes[0]  # premier disponible

    if action == "create":
        return connector.create_event(
            title=kwargs.get("title", ""),
            start=kwargs.get("start", ""),
            end=kwargs.get("end", ""),
            location=kwargs.get("location", ""),
            description=kwargs.get("description", ""),
            attendees=kwargs.get("attendees", []),
        )
    elif action == "update":
        return connector.update_event(kwargs.get("event_id", ""), **kwargs)
    elif action == "delete":
        return connector.delete_event(kwargs.get("event_id", ""))
    return {"ok": False, "message": f"Action calendrier inconnue : {action}"}


def get_connector_for_mailbox(username: str, hint: str = "") -> "MailboxConnector | None":
    """
    Résout le connecteur à utiliser selon un hint (email, provider, ou vide).
    hint = email exact, 'gmail', 'microsoft', 'perso', 'pro', '' → premier disponible.
    """
    mailboxes = get_user_mailboxes(username)
    if not mailboxes:
        return None
    if not hint or hint.lower() in ("auto", ""):
        return mailboxes[0]
    h = hint.lower().strip()
    # Correspondance exacte email
    for m in mailboxes:
        if m.email.lower() == h:
            return m
    # Correspondance partielle email
    for m in mailboxes:
        if m.email and h in m.email.lower():
            return m
    # Correspondance provider / alias
    gmail_aliases = {"gmail", "google", "perso", "boite perso", "boîte perso", "personnel", "particulier"}
    ms_aliases    = {"microsoft", "outlook", "office", "office365", "365", "pro",
                     "boite pro", "boîte pro", "professionnel", "entreprise"}
    for m in mailboxes:
        if m.provider == "gmail"     and h in gmail_aliases: return m
        if m.provider == "microsoft" and h in ms_aliases:    return m
    return mailboxes[0]
