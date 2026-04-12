"""
Action SHARE_EVENT — publication d'un événement tenant (8-COLLAB).

Syntaxe : [ACTION:SHARE_EVENT:type|titre|corps]

Types valides :
  task_completed, document_modified, mail_important,
  meeting_scheduled, milestone_reached, alert_shared
"""
import re
from app.logging_config import get_logger

logger = get_logger("raya.actions")

_RE_SHARE_EVENT = re.compile(
    r"\[ACTION:SHARE_EVENT:([^\|\]]+)\|([^\|\]]+)\|?([^\]]*)\]"
)


def _handle_collab_actions(
    raya_response: str,
    username: str,
    tenant_id: str,
) -> list:
    """Parse et exécute les [ACTION:SHARE_EVENT:type|titre|corps]."""
    results = []
    for match in _RE_SHARE_EVENT.finditer(raya_response):
        event_type = match.group(1).strip()
        title      = match.group(2).strip()
        body       = match.group(3).strip() if match.group(3) else None
        if not title:
            continue
        try:
            from app.tenant_events import publish_event
            r = publish_event(
                tenant_id=tenant_id,
                username=username,
                event_type=event_type or "alert_shared",
                title=title,
                body=body or None,
            )
            if r.get("status") == "ok":
                results.append(f"✅ Partagé avec l'équipe : {title[:60]}")
            else:
                results.append(f"❌ SHARE_EVENT échoué : {r.get('message', '?')}")
        except Exception as e:
            logger.error(f"[SHARE_EVENT] Erreur: {e}")
            results.append(f"❌ SHARE_EVENT erreur : {str(e)[:80]}")
    return results
