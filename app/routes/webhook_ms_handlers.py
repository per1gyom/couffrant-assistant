"""
Handlers de traitement des notifications Microsoft Graph.
Extrait de webhook_microsoft.py -- SPLIT-F7.
"""
import json,re,threading
from datetime import datetime
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.logging_config import get_logger
from app.routes.webhook_microsoft import _get_mail_filter_rules,_matches_filter,_is_bulk_heuristic,_is_spam_by_rules
logger=get_logger("raya.webhook.ms")


def process_incoming_mail(
    username: str,
    sender: str,
    subject: str,
    preview: str,
    message_id: str,
    received_at: str,
    mailbox_source: str = "outlook",
    raw_body: str = None,
    mailbox_email: str = None,
    connection_id: int = None,
) -> str:
    """
    Pipeline de filtrage commun (7-1b) — source-agnostic.
    Appelé par le webhook Microsoft ET le polling Gmail.

    Retourne : "duplicate", "ignored", "stored_simple", "done_ai", "fallback", "error".

    Fix 04/05/2026 : nouveaux parametres mailbox_email et connection_id pour
    identifier de maniere certaine quelle boite a recu le mail. Permet de ne
    pas confondre les 5 boites Gmail entre elles ni les 2 boites Outlook
    entre elles. Ces valeurs sont stockees telles quelles dans mail_memory.
    """
    from datetime import datetime
    from app.mail_memory_store import mail_exists, insert_mail
    from app.ai_client import analyze_single_mail_with_ai
    from app.router import route_mail_action
    from app.feedback_store import get_global_instructions
    from app.app_security import get_tenant_id
    from app.database import get_pg_conn

    try:
        if mail_exists(message_id, username):
            return "duplicate"

        tenant_id = get_tenant_id(username)
        whitelist, blacklist = _get_mail_filter_rules(username)

        # 1a — Whitelist
        whitelisted = _matches_filter(sender, subject, whitelist)

        # 1b — Heuristique statique
        if not whitelisted and _is_bulk_heuristic(sender, subject, preview):
            print(f"[Pipeline][L1b] Ignoré : '{subject[:50]}' de {sender}")
            return "ignored"

        # 1c — Blacklist
        if _matches_filter(sender, subject, blacklist):
            print(f"[Pipeline][L1c] Bloqué : '{subject[:50]}' de {sender}")
            return "ignored"

        # 2 — Anti-spam personnalisé
        if _is_spam_by_rules(sender, subject, preview, username):
            print(f"[Pipeline][L2] Ignoré : '{subject[:50]}' de {sender}")
            return "ignored"

        # 3 — Triage Haiku
        try:
            triage = route_mail_action(sender, subject, preview)
        except Exception:
            triage = "ANALYSER"

        if triage == "IGNORER":
            return "ignored"

        # 4 — Analyse ou stockage simple
        instructions = get_global_instructions(tenant_id=tenant_id)

        if triage == "STOCKER_SIMPLE":
            item = {
                "display_title": subject or "(Sans objet)",
                "category": "autre", "priority": "basse",
                "reason": "Stockage simple (triage)",
                "suggested_action": "Consulter si besoin",
                "short_summary": (preview or "")[:200],
                "group_hints": [],
                "confidence": 0.5, "confidence_level": "moyenne",
                "needs_review": False, "needs_reply": False,
                "reply_urgency": "basse", "reply_reason": "",
                "response_type": "pas_de_reponse", "missing_fields": [],
                "suggested_reply_subject": "", "suggested_reply": "",
            }
            analysis_status = "stored_simple"
        else:
            try:
                mock_msg = {
                    "id": message_id, "subject": subject,
                    "from": {"emailAddress": {"address": sender}},
                    "receivedDateTime": received_at,
                    "bodyPreview": preview,
                    "body": {"content": raw_body or preview},
                }
                item = analyze_single_mail_with_ai(mock_msg, instructions, username)
                analysis_status = "done_ai"
            except Exception as e:
                print(f"[Pipeline] Erreur analyse: {e}")
                item = {
                    "display_title": subject or "(Sans objet)",
                    "category": "autre", "priority": "moyenne",
                    "reason": "Analyse échouée", "suggested_action": "Vérifier",
                    "short_summary": (preview or "")[:200], "group_hints": [],
                    "confidence": 0.3, "needs_review": True,
                    "needs_reply": False, "reply_urgency": "basse",
                    "reply_reason": "", "suggested_reply_subject": "",
                    "suggested_reply": "",
                }
                analysis_status = "fallback"

        insert_mail({
            "username": username,
            "message_id": message_id,
            "received_at": received_at,
            "from_email": sender,
            "subject": subject,
            "display_title": item.get("display_title"),
            "category": item.get("category"),
            "priority": item.get("priority"),
            "reason": item.get("reason"),
            "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"),
            "group_hints": item.get("group_hints", []),
            "confidence": item.get("confidence", 0.0),
            "needs_review": item.get("needs_review", False),
            "raw_body_preview": preview,
            "analysis_status": analysis_status,
            "needs_reply": item.get("needs_reply"),
            "reply_urgency": item.get("reply_urgency"),
            "reply_reason": item.get("reply_reason"),
            "suggested_reply_subject": item.get("suggested_reply_subject"),
            "suggested_reply": item.get("suggested_reply"),
            "mailbox_source": mailbox_source,
            "mailbox_email": mailbox_email,
            "connection_id": connection_id,
        })

        # Heartbeat monitoring (7-7)
        try:
            from app.database import get_pg_conn as _hb_conn
            _c2 = _hb_conn()
            _c3 = _c2.cursor()
            _c3.execute("""
                INSERT INTO system_heartbeat (component, last_seen_at, status)
                VALUES ('webhook_microsoft', NOW(), 'ok')
                ON CONFLICT (component)
                DO UPDATE SET last_seen_at = NOW(), status = 'ok'
            """)
            _c2.commit()
            _c2.close()
        except Exception:
            pass

        # 5 — Scoring d'urgence + alerte
        try:
            from app.urgency_model import score_mail_urgency
            urgency = score_mail_urgency(sender, subject, preview, username, tenant_id)
            if urgency["level"] in ("important", "critical"):
                _conn = get_pg_conn()
                _c = _conn.cursor()
                _c.execute("SELECT shadow_mode, shadow_mode_until FROM users WHERE username = %s", (username,))
                _row = _c.fetchone()
                _conn.close()
                is_shadow = (_row and _row[0] and (_row[1] is None or _row[1] > datetime.now()))

                from app.proactive_alerts import create_alert
                icon = "\U0001f534" if urgency["level"] == "critical" else "\U0001f7e0"
                prio = "critical" if urgency["level"] == "critical" else "high"
                if is_shadow:
                    create_alert(
                        username=username, tenant_id=tenant_id, alert_type="mail_urgent",
                        priority=prio,
                        title=f"[SHADOW] {icon} WhatsApp : {subject[:60]}",
                        body=f"De : {sender}\nScore : {urgency['score']}/100\nRaisons : {', '.join(urgency['reasons'][:3])}",
                        source_type="mail_shadow", source_id=str(message_id[:50]),
                    )
                else:
                    create_alert(
                        username=username, tenant_id=tenant_id, alert_type="mail_urgent",
                        priority=prio,
                        title=f"Mail {urgency['level']} : {subject[:60]}",
                        body=f"De : {sender}\nScore : {urgency['score']}/100\n{item.get('short_summary', preview[:200])}",
                        source_type="mail", source_id=str(message_id[:50]),
                    )
        except Exception as e:
            print(f"[Pipeline] Erreur urgence: {e}")

        return analysis_status

    except Exception as e:
        print(f"[Pipeline] Erreur {username}/{message_id}: {e}")
        return "error"


# ─── WEBHOOK ENDPOINTS ───




def _process_mail(username: str, message_id: str):
    """
    Pipeline Microsoft — récupère le mail via Graph puis appelle process_incoming_mail.
    """
    try:
        from app.token_manager import get_valid_microsoft_token
        from app.graph_client import graph_get
        from app.mail_memory_store import mail_exists

        token = get_valid_microsoft_token(username)
        if not token:
            return
        if mail_exists(message_id, username):
            return

        try:
            msg = graph_get(token, f"/me/messages/{message_id}", params={
                "$select": "id,subject,from,receivedDateTime,bodyPreview,body,isRead"
            })
        except Exception as e:
            print(f"[Webhook] Erreur récupération mail {username}: {e}")
            return

        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
        subject = msg.get("subject", "") or ""
        preview = msg.get("bodyPreview", "") or ""
        received_at = msg.get("receivedDateTime", "")
        raw_body = msg.get("body", {}).get("content", "")

        process_incoming_mail(
            username=username, sender=sender, subject=subject,
            preview=preview, message_id=message_id,
            received_at=received_at, mailbox_source="outlook",
            raw_body=raw_body,
        )
    except Exception as e:
        print(f"[Webhook] Erreur {username}/{message_id}: {e}")


