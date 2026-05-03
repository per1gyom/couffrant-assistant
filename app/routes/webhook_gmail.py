"""
Handler Twilio/WhatsApp.
Extrait de webhook.py -- SPLIT-R3.
"""
import json
from app.database import get_pg_conn
from app.logging_config import get_logger
logger=get_logger("raya.webhook.whatsapp")


def _resolve_user_by_phone(phone: str) -> str | None:
    """
    Retrouve le username à partir du numéro de téléphone. (7-8 + USER-PHONE)
    Cherche d'abord dans la colonne phone de la table users (DB),
    puis tombe sur les variables d'environnement pour la compatibilité.
    """
    import os
    from app.database import get_pg_conn

    phone_clean = phone.replace("+", "").replace(" ", "")

    # 1. Chercher en base (colonne users.phone — USER-PHONE)
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT username FROM users
            WHERE REPLACE(REPLACE(COALESCE(phone, ''), '+', ''), ' ', '') = %s
            LIMIT 1
        """, (phone_clean,))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"[Twilio] Erreur lookup phone DB: {e}")

    # 2. Fallback variables d'environnement (compatibilité ascendante)
    for key, value in os.environ.items():
        if key.startswith("NOTIFICATION_PHONE_"):
            val_clean = value.strip().replace("+", "").replace(" ", "")
            if val_clean == phone_clean:
                username = key.replace("NOTIFICATION_PHONE_", "").lower()
                if username not in ("default", "admin"):
                    return username
    return None



def _whatsapp_raya_response(username: str, message: str, tenant_id: str) -> str:
    """
    WHATSAPP-RAYA : appel LLM léger pour répondre au texte libre WhatsApp.

    Contexte minimal : hot_summary + règles comportement/style.
    Modèle : smart (Sonnet). Max 512 tokens → réponse courte, sans markdown.
    Sauvegarde l'échange dans aria_memory (partagé avec le chat).
    Log les coûts via log_llm_usage.

    Lève une exception si le LLM échoue — l'appelant applique un fallback.
    """
    from app.llm_client import llm_complete, log_llm_usage
    from app.database import get_pg_conn
    from app.rule_engine import get_rules_as_text
    from app.memory_synthesis import get_hot_summary

    # 1. Contexte léger : hot_summary (mémoire opérationnelle)
    hot_summary = ""
    try:
        hot_summary = (get_hot_summary(username) or "")[:800]
    except Exception:
        pass

    # 2. Règles de comportement et style
    rules_text = ""
    try:
        rules_text = get_rules_as_text(username, ["Comportement", "Style", "Mémoire"])
    except Exception:
        pass

    # 3. Prompt système minimal adapté WhatsApp
    context_block = f"\n\nMémoire active (résumé) :\n{hot_summary}" if hot_summary else ""
    rules_block = f"\n\nRègles de comportement :\n{rules_text[:600]}" if rules_text else ""

    system_prompt = (
        f"Tu es Raya, l'assistante IA personnelle de {username.capitalize()}. "
        f"Tu réponds via WhatsApp — sois concise, directe et vraiment utile. "
        f"Maximum 3-4 phrases. Pas de markdown, pas d'astérisques, pas de titres. "
        f"Réponds en français."
        f"{context_block}{rules_block}"
    )

    # 4. Appel LLM (Sonnet, 512 tokens max)
    result = llm_complete(
        messages=[{"role": "user", "content": message}],
        model_tier="smart",
        max_tokens=512,
        system=system_prompt,
    )
    response_text = (result.get("text") or "").strip()

    # 5. Tronquer à 1500 chars (limite WhatsApp pratique)
    if len(response_text) > 1500:
        response_text = response_text[:1497] + "…"

    # 6. Sauvegarder dans aria_memory (historique partagé chat + WhatsApp)
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_memory (username, tenant_id, user_input, aria_response)
            VALUES (%s, %s, %s, %s)
        """, (username, tenant_id, message, response_text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WhatsApp] Erreur sauvegarde aria_memory: {e}")

    # 7. Log des coûts LLM
    try:
        log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="whatsapp_raya")
    except Exception:
        pass

    return response_text



def _handle_whatsapp_command(username: str, message: str, phone: str):
    """
    Traite une commande WhatsApp entrante. (7-8)
    Commandes reconnues :
      "1" / "oui" / "gère" → exécuter la dernière action proposée
      "2" / "ok" / "m'en occupe" → marquer dernière alerte comme vue
      "3" / "rappel" / "1h" → créer un rappel dans 1h
      "4" / "ignorer" → dismiss l'alerte
      "rapport" → livrer le rapport matinal
      Texte libre → vraie réponse Raya via LLM (WHATSAPP-RAYA)
    """
    from app.connectors.twilio_connector import send_whatsapp
    from app.app_security import get_tenant_id

    message_lower = message.lower().strip()
    tenant_id = get_tenant_id(username)

    # Commande 1 — Confirmer la dernière action pending
    if message_lower in ("1", "oui", "gère", "gere"):
        try:
            from app.pending_actions import get_pending
            pending = get_pending(username, tenant_id=tenant_id, limit=1)
            if pending:
                latest = pending[0]
                send_whatsapp(phone, f"✅ Confirme l'action #{latest['id']} dans le chat Raya pour l'exécuter.")
            else:
                send_whatsapp(phone, "Pas d'action en attente.")
        except Exception as e:
            send_whatsapp(phone, f"Erreur : {str(e)[:100]}")
        return

    # Commande 2 — Marquer dernière alerte comme vue
    if message_lower in ("2", "ok", "m'en occupe", "men occupe", "je gère", "je gere"):
        try:
            from app.proactive_alerts import get_active_alerts, mark_seen
            alerts = get_active_alerts(username)
            if alerts:
                mark_seen([alerts[0]["id"]], username)
                send_whatsapp(phone, "👍 Noté, tu gères.")
            else:
                send_whatsapp(phone, "Pas d'alerte active.")
        except Exception:
            pass
        return

    # Commande 3 — Rappel dans 1h
    if message_lower in ("3", "rappel", "1h", "rappelle", "plus tard"):
        try:
            from app.proactive_alerts import create_alert
            from datetime import datetime, timedelta
            create_alert(
                username=username, tenant_id=tenant_id,
                alert_type="reminder", priority="normal",
                title="⏰ Rappel (demandé via WhatsApp)",
                body=f"Tu as demandé un rappel à {(datetime.now() + timedelta(hours=1)).strftime('%H:%M')}.",
                source_type="whatsapp_reminder",
            )
            send_whatsapp(phone, "⏰ OK, je te rappelle dans 1h.")
        except Exception:
            pass
        return

    # Commande 4 — Dismiss dernière alerte
    if message_lower in ("4", "ignorer", "ignore", "rien"):
        try:
            from app.proactive_alerts import get_active_alerts, dismiss_alert
            alerts = get_active_alerts(username)
            if alerts:
                dismiss_alert(alerts[0]["id"])
                send_whatsapp(phone, "🔕 Alerte ignorée.")
        except Exception:
            pass
        return

    # Rapport — livrer le rapport matinal
    if "rapport" in message_lower or "résumé" in message_lower or "resume" in message_lower:
        try:
            from app.routes.actions.report_actions import get_today_report, mark_report_delivered
            report = get_today_report(username)
            if report:
                send_whatsapp(phone, report["content"][:1500])
                mark_report_delivered(report["id"], "whatsapp")
            else:
                send_whatsapp(phone, "Pas de rapport disponible aujourd'hui.")
        except Exception:
            send_whatsapp(phone, "Erreur lors de la récupération du rapport.")
        return

    # ─── TEXTE LIBRE → vraie réponse Raya (WHATSAPP-RAYA) ───
    try:
        response = _whatsapp_raya_response(username, message, tenant_id)
        send_whatsapp(phone, response)
    except Exception as e:
        print(f"[WhatsApp] Erreur LLM réponse libre: {e}")
        # Fallback sur l'accusé de réception si le LLM échoue
        send_whatsapp(phone, "📩 Message reçu. Connecte-toi au chat pour une réponse complète de Raya.")

    # Logger l'activité
    try:
        from app.activity_log import log_activity
        log_activity(username, "whatsapp_raya", message[:100], phone, tenant_id)
    except Exception:
        pass


