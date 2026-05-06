"""
Alert Dispatcher — envoi universel d'alertes multi-canaux (5 niveaux).

Module commun (Phase Connexions Universelles, 1er mai 2026) hérité par tous
les connecteurs et tous les jobs systeme qui ont besoin d alerter.

Voir docs/vision_connexions_universelles_01mai.md (decision Q16 Guillaume).

PHILOSOPHIE — 5 NIVEAUX DE GRAVITE, MULTI-CANAUX, PARAMETRABLE :
─────────────────────────────────────────────────────────────────
On ne demande PAS au connecteur "comment" envoyer une alerte. Il dit "il y a
un probleme de gravite X" et le dispatcher route vers les bons canaux selon :
  1. Le niveau de gravite (info / warning / attention / critical / blocking)
  2. Les preferences user (user.settings.alert_preferences en JSONB)
  3. Les valeurs par defaut intelligentes pour les 95 pct qui ne configurent rien

NIVEAUX DE GRAVITE (decision Q16 Guillaume) :
─────────────────────────────────────────────
  info       : aucune notif active. Visible uniquement /admin/health.
               Ex : "Drive a fait 3 micro-coupures auto-recuperees"

  warning    : in-app uniquement (badge dans Raya) + email du soir groupe.
               Ex : "Polling Drive lent depuis 2h"

  attention  : push mobile + email immediat. Pas de SMS.
               Ex : "Token Microsoft expire dans 24h"

  critical   : SMS + Push + email + chat (TOUS canaux en parallele).
               Ex : "Aucune ingestion Outlook depuis 1h, vraie panne"

  blocking   : SMS repete toutes les 15 min jusqu a acquittement
               + appel telephonique automatique
               + tous les canaux du critical
               Ex : "Tous les tokens HS, intervention urgente"

CANAUX SUPPORTES :
─────────────────
  ✅ in_app           : insertion dans system_alerts (visible dans Raya)
  ✅ email            : SMTP via reply_microsoft_with_token (existant)
  ✅ sms              : Twilio send_sms (existant)
  ✅ whatsapp         : Twilio send_whatsapp (existant)
  🟡 push_mobile      : Flutter app (a connecter quand l app aura les push)
  🟡 phone_call       : Twilio Voice (a connecter quand le compte aura les
                        droits, voir docs/vision_connexions_universelles)
  🟡 teams            : Microsoft Graph (a connecter quand on aura le
                        webhook Teams sortant)

INTEGRATION AVEC system_alerts (existant depuis 18/04/2026) :
──────────────────────────────────────────────────────────────
On REUTILISE la table system_alerts pour la persistance. dispatch() fait
l UPSERT dans cette table en plus d envoyer les notifications externes.
Ainsi /admin/health peut afficher l historique complet des alertes.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.alert_dispatcher")


# ─── NIVEAUX DE GRAVITE ───

SEVERITIES = ("info", "warning", "attention", "critical", "blocking")

# Mapping severite -> canaux par defaut.
# Override possible via user.settings.alert_preferences.
DEFAULT_CHANNELS_BY_SEVERITY = {
    "info":      ["in_app"],
    "warning":   ["in_app", "email_digest"],
    "attention": ["in_app", "email", "push_mobile"],
    "critical":  ["in_app", "email", "push_mobile", "sms", "whatsapp"],
    "blocking":  ["in_app", "email", "push_mobile", "sms", "whatsapp", "phone_call"],
}


# ─── COOLDOWN ENVOI EXTERNE ───
# Pour empecher le spam SMS/WhatsApp/Email quand une alerte reste active
# longtemps (ex: connection_silence qui ne se resout pas pendant 7h).
# La persistance dans system_alerts (UPSERT) deduplique deja en base, mais
# le canal externe ne checkait rien -> Twilio etait sollicite a chaque cycle.
EXTERNAL_COOLDOWN_HOURS = 4


# ─── API PRINCIPALE ───

def send(
    severity: str,
    title: str,
    message: str,
    tenant_id: str,
    username: Optional[str] = None,
    actions: Optional[list] = None,
    source_type: str = "generic",
    source_id: Optional[str] = None,
    auto_escalate_after_minutes: Optional[int] = None,
    component: Optional[str] = None,
    alert_type: Optional[str] = None,
) -> bool:
    """Envoie une alerte selon les regles du dispatcher.

    Args:
        severity: 'info' / 'warning' / 'attention' / 'critical' / 'blocking'
        title: titre court (1 ligne)
        message: contenu (peut etre plus long)
        tenant_id: tenant concerne (pour persistance + routing)
        username: si specifique a un user (sinon = tenant_admin)
        actions: liste d actions concretes proposees a l user. Format :
                 [{"label": "Reconnecter Outlook", "url": "/login?provider=microsoft"}]
        source_type: 'connection_health' / 'webhook' / 'odoo' / etc.
        source_id: identifiant de la source (connection_id, etc.)
        auto_escalate_after_minutes: si non None, l alerte passe au niveau
                                      superieur si pas acquittee a temps
        component: pour deduplication (ex: "outlook_polling_user_guillaume")
        alert_type: pour deduplication (ex: "connection_silence")

    Returns:
        True si l alerte a ete persistee (les envois externes sont best effort).
    """
    if severity not in SEVERITIES:
        logger.warning("[Dispatch] Severite inconnue : %s", severity)
        severity = "warning"

    # 1. Persistance dans system_alerts (UPSERT pour deduplication)
    persisted = _persist_alert(
        tenant_id=tenant_id,
        alert_type=alert_type or source_type,
        severity=severity,
        component=component or (source_id or "unknown"),
        title=title,
        message=message,
        actions=actions or [],
        username=username,
        source_type=source_type,
        source_id=source_id,
        auto_escalate_after_minutes=auto_escalate_after_minutes,
    )

    # 2. Resolution des canaux a utiliser
    channels = _resolve_channels(severity, username, tenant_id)
    logger.info(
        "[Dispatch] severity=%s tenant=%s user=%s canaux=%s : %s",
        severity, tenant_id, username, channels, title,
    )

    # 3. Cooldown externe : check si on a deja envoye SMS/WhatsApp/Email
    #    pour cette meme alerte (tenant+type+component) recemment.
    component_real = component or (source_id or "unknown")
    alert_type_real = alert_type or source_type
    EXTERNAL_CHANNELS = {"sms", "whatsapp", "email"}
    skip_external = _should_skip_external_send(
        tenant_id, alert_type_real, component_real,
        cooldown_hours=EXTERNAL_COOLDOWN_HOURS,
    )

    # 4. Envoi sur chaque canal (best effort, on ne fail pas si un canal echoue)
    sent_external_at_least_once = False
    for channel in channels:
        if channel in EXTERNAL_CHANNELS and skip_external:
            logger.info(
                "[Dispatch] Cooldown %dh actif pour %s/%s, skip canal %s",
                EXTERNAL_COOLDOWN_HOURS, alert_type_real, component_real, channel,
            )
            continue
        try:
            _send_on_channel(
                channel=channel,
                severity=severity,
                title=title,
                message=message,
                actions=actions or [],
                tenant_id=tenant_id,
                username=username,
            )
            if channel in EXTERNAL_CHANNELS:
                sent_external_at_least_once = True
        except Exception as e:
            logger.error(
                "[Dispatch] Canal %s echoue : %s",
                channel, str(e)[:200],
            )

    # 5. Si au moins un envoi externe a reussi, on enregistre le timestamp
    #    pour appliquer le cooldown au prochain cycle.
    if sent_external_at_least_once:
        _record_external_sent(tenant_id, alert_type_real, component_real)

    return persisted


def _get_connection_human_identity(connection_id: Optional[int]) -> tuple:
    """Retourne (label, connected_email) d'une connexion pour affichage humain.

    Refonte 06/05/2026 : permet aux alertes d'afficher
    'contact@couffrant-solar.fr' au lieu de 'connection_14'.

    En cas d'echec DB ou connexion absente : retourne (None, None) pour
    que le caller puisse fallback sur l'ID brut sans planter.
    """
    if not connection_id:
        return (None, None)
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT label, connected_email FROM tenant_connections WHERE id = %s",
            (connection_id,),
        )
        row = c.fetchone()
        if row:
            return (row[0], row[1])
        return (None, None)
    except Exception as e:
        logger.warning(
            "[AlertDispatch] _get_connection_human_identity failed for conn=%s : %s",
            connection_id, str(e)[:200],
        )
        return (None, None)
    finally:
        if conn:
            conn.close()


def dispatch_connection_alert(conn_alert: dict) -> bool:
    """Helper specifique pour les alertes de connexion (depuis connection_health).

    Appelee par le job _job_connection_health_check quand une connexion est
    en silence anormal. Construit le message + actions et delegue a send().

    Args:
        conn_alert: dict retourne par check_all_connections() :
            {
              'connection_id', 'tenant_id', 'username', 'connection_type',
              'last_successful_poll_at', 'silence_seconds',
              'alert_threshold_seconds', 'consecutive_failures', 'status'
            }
    """
    silence_min = (conn_alert.get("silence_seconds") or 0) // 60
    threshold_min = (conn_alert.get("alert_threshold_seconds") or 0) // 60

    # Severite progressive selon la duree du silence
    severity = "warning"
    if silence_min >= threshold_min * 4:
        severity = "critical"
    elif silence_min >= threshold_min * 2:
        severity = "attention"

    connection_type = conn_alert.get("connection_type", "connexion")
    connection_id = conn_alert.get("connection_id")

    # Refonte 06/05/2026 : message en francais clair avec email/label
    # de la boite plutot que "connection_14" (jargon technique).
    boite_label, boite_email = _get_connection_human_identity(connection_id)
    boite_display = boite_email or boite_label or f"connexion #{connection_id}"

    # Format duree humaine : 125 min -> "2h05"
    if silence_min >= 60:
        h = silence_min // 60
        m = silence_min % 60
        duree_humaine = f"{h}h{m:02d}"
    else:
        duree_humaine = f"{silence_min} min"

    # Verbe selon le type de source (mail vs autre)
    if connection_type.startswith("mail_") or connection_type in ("mail_outlook", "mail_gmail"):
        title = f"Boite {boite_display} silencieuse depuis {duree_humaine}"
        message = (
            f"La boite {boite_display} ne repond plus depuis {duree_humaine}. "
            f"Le systeme retente automatiquement toutes les 5 min. "
            f"Si l'alerte persiste, verifie la connexion dans le panel Societes."
        )
    elif connection_type == "drive":
        title = f"Drive '{boite_display}' silencieux depuis {duree_humaine}"
        message = (
            f"Le drive '{boite_display}' ne repond plus depuis {duree_humaine}. "
            f"Le systeme retente automatiquement. "
            f"Si l'alerte persiste, verifie la connexion dans le panel Societes."
        )
    elif connection_type == "odoo":
        title = f"Odoo '{boite_display}' silencieux depuis {duree_humaine}"
        message = (
            f"La connexion Odoo '{boite_display}' ne repond plus depuis {duree_humaine}. "
            f"Le systeme retente automatiquement. "
            f"Si l'alerte persiste, verifie l'API key dans le panel Societes."
        )
    else:
        # Generique pour types inconnus
        title = f"Connexion '{boite_display}' silencieuse depuis {duree_humaine}"
        message = (
            f"La connexion '{boite_display}' ne repond plus depuis {duree_humaine}. "
            f"Le systeme retente automatiquement. "
            f"Si l'alerte persiste, verifie dans le panel Societes."
        )

    actions = [
        {
            "label": "Voir la connexion",
            "url": f"/admin/health/connection/{connection_id}",
        },
    ]

    # Suggestion d action selon le type de connexion
    if connection_type.startswith("mail_outlook") or connection_type == "outlook":
        actions.append({
            "label": "Reconnecter Outlook",
            "url": "/login?provider=microsoft",
        })
    elif connection_type.startswith("mail_gmail") or connection_type == "gmail":
        actions.append({
            "label": "Reconnecter Gmail",
            "url": "/login?provider=google",
        })

    return send(
        severity=severity,
        title=title,
        message=message,
        tenant_id=conn_alert.get("tenant_id", "unknown"),
        username=conn_alert.get("username"),
        actions=actions,
        source_type="connection_health",
        source_id=str(conn_alert.get("connection_id")),
        component=f"connection_{conn_alert.get('connection_id')}",
        alert_type="connection_silence",
        auto_escalate_after_minutes=30 if severity == "critical" else None,
    )


# ─── PERSISTANCE DANS system_alerts ───

def _persist_alert(
    tenant_id: str,
    alert_type: str,
    severity: str,
    component: str,
    title: str,
    message: str,
    actions: list,
    username: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    auto_escalate_after_minutes: Optional[int] = None,
) -> bool:
    """UPSERT dans system_alerts (deduplication par tenant+type+component).

    Reutilise la table existante depuis 18/04/2026. Mappe nos severities sur
    le SEVERITY check de la table : info/warning/critical seuls etaient
    autorises a l origine. On utilise :
      info / warning / attention -> 'warning'
      critical / blocking         -> 'critical'

    NOTE : si on veut a terme avoir les 5 niveaux dans system_alerts.severity,
    une migration sera necessaire. Pour l instant on garde compat existant
    et on stocke le niveau detaille dans details.severity_real.
    """
    # Mapping vers les severities supportees par system_alerts
    severity_db = severity
    if severity in ("attention",):
        severity_db = "warning"
    elif severity in ("blocking",):
        severity_db = "critical"

    details = {
        "title": title,
        "actions": actions,
        "username": username,
        "source_type": source_type,
        "source_id": source_id,
        "auto_escalate_after_minutes": auto_escalate_after_minutes,
        "severity_real": severity,  # niveau original (5 valeurs)
        "raised_at": datetime.now().isoformat(),
    }

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO system_alerts
              (tenant_id, alert_type, severity, component, message, details,
               acknowledged, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, FALSE, NOW(), NOW())
            ON CONFLICT (tenant_id, alert_type, component) DO UPDATE SET
              severity = EXCLUDED.severity,
              message = EXCLUDED.message,
              details = EXCLUDED.details,
              acknowledged = CASE
                  WHEN EXCLUDED.severity = 'critical'
                       AND system_alerts.severity = 'warning'
                  THEN FALSE
                  ELSE system_alerts.acknowledged
              END,
              updated_at = NOW()
        """, (
            tenant_id, alert_type, severity_db, component, message[:1000],
            json.dumps(details, ensure_ascii=False, default=str),
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error("[Dispatch] _persist_alert echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


# ─── RESOLUTION DES CANAUX ───

def _resolve_channels(severity: str, username: Optional[str],
                      tenant_id: str) -> list:
    """Retourne la liste des canaux a utiliser pour cette alerte.

    Logique :
      1. Defaut intelligent selon severity (DEFAULT_CHANNELS_BY_SEVERITY)
      2. Override par user.settings.alert_preferences si dispo
      3. Filtre les canaux qui ne sont pas operationnels (ex: pas de
         numero Twilio configure -> on retire sms/whatsapp/phone_call)
    """
    channels = list(DEFAULT_CHANNELS_BY_SEVERITY.get(severity, ["in_app"]))

    # Override user (lecture user.settings.alert_preferences)
    if username:
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                SELECT settings FROM users
                WHERE username = %s AND tenant_id = %s
                LIMIT 1
            """, (username, tenant_id))
            row = c.fetchone()
            conn.close()
            if row and row[0]:
                settings = row[0] if isinstance(row[0], dict) else {}
                prefs = settings.get("alert_preferences", {})
                user_channels = prefs.get(severity)
                if user_channels and isinstance(user_channels, list):
                    channels = user_channels
        except Exception as e:
            logger.debug("[Dispatch] resolve_channels override echoue : %s", str(e)[:200])

    # Filtrer les canaux non disponibles
    available = []
    for ch in channels:
        if ch == "in_app":
            available.append(ch)  # toujours dispo
        elif ch in ("sms", "whatsapp"):
            if _twilio_available():
                available.append(ch)
        elif ch == "email":
            if _smtp_available():
                available.append(ch)
        elif ch == "email_digest":
            available.append(ch)  # pas de send immediat, juste un flag
        elif ch in ("push_mobile", "phone_call", "teams"):
            # Pas encore implemente, on log mais on filtre
            logger.debug("[Dispatch] Canal %s pas encore operationnel", ch)
        else:
            logger.warning("[Dispatch] Canal inconnu : %s", ch)

    return available


def _twilio_available() -> bool:
    """Verifie si Twilio est configure (clefs presentes)."""
    try:
        from app.connectors.twilio_connector import is_available
        return is_available()
    except Exception:
        return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))


def _smtp_available() -> bool:
    """Verifie si SMTP est configure (variables d env)."""
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and os.getenv("SMTP_PASSWORD")
    )


# ─── ENVOI PAR CANAL ───

def _should_skip_external_send(
    tenant_id: str,
    alert_type: str,
    component: str,
    cooldown_hours: int = EXTERNAL_COOLDOWN_HOURS,
) -> bool:
    """Verifie si on doit skipper l envoi externe (SMS/WhatsApp/Email).

    Lit details->>'last_external_sent_at' dans system_alerts. Si l envoi
    externe est plus recent que cooldown_hours, on skippe.

    Returns True si on doit skipper (cooldown actif), False sinon.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT details->>'last_external_sent_at'
            FROM system_alerts
            WHERE tenant_id = %s
              AND alert_type = %s
              AND component = %s
        """, (tenant_id, alert_type, component))
        row = c.fetchone()
        if not row or not row[0]:
            return False  # jamais envoye -> on envoie
        last_sent = row[0]
        # Parse l ISO timestamp (peut etre avec ou sans timezone)
        try:
            last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False  # parse impossible -> on envoie par securite
        delta = datetime.now(last_dt.tzinfo) - last_dt
        return delta < timedelta(hours=cooldown_hours)
    except Exception as e:
        logger.warning("[Dispatch] _should_skip_external_send echoue : %s",
                       str(e)[:200])
        return False  # en cas d erreur -> on envoie (mieux louper le cooldown
                      # que rater une alerte critique)
    finally:
        if conn: conn.close()


def _record_external_sent(
    tenant_id: str,
    alert_type: str,
    component: str,
) -> None:
    """Enregistre dans details que l envoi externe a eu lieu maintenant.

    UPDATE atomique de system_alerts.details->>'last_external_sent_at'.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE system_alerts
            SET details = jsonb_set(
                COALESCE(details, '{}'::jsonb),
                '{last_external_sent_at}',
                to_jsonb(NOW()::text)
            )
            WHERE tenant_id = %s
              AND alert_type = %s
              AND component = %s
        """, (tenant_id, alert_type, component))
        conn.commit()
    except Exception as e:
        logger.warning("[Dispatch] _record_external_sent echoue : %s",
                       str(e)[:200])
    finally:
        if conn: conn.close()


def _send_on_channel(
    channel: str,
    severity: str,
    title: str,
    message: str,
    actions: list,
    tenant_id: str,
    username: Optional[str],
) -> None:
    """Dispatcher vers la fonction d envoi specifique au canal."""
    if channel == "in_app":
        # La persistance dans system_alerts a deja ete faite par _persist_alert.
        # Rien a faire de plus pour le canal in_app (l UI lit cette table).
        return

    if channel == "email_digest":
        # Pas d envoi immediat : un job nocturne lira system_alerts pour
        # construire le digest. Rien a faire ici.
        return

    if channel == "email":
        _send_email(severity, title, message, actions, username, tenant_id)
        return

    if channel == "sms":
        _send_sms_alert(severity, title, message, username, tenant_id)
        return

    if channel == "whatsapp":
        _send_whatsapp_alert(severity, title, message, username, tenant_id)
        return

    logger.debug("[Dispatch] Canal %s ignore (non implemente)", channel)


def _send_email(severity, title, message, actions, username, tenant_id):
    """Envoi email immediat (pour attention / critical / blocking)."""
    try:
        # Resolution adresse email destinataire
        to_email = _resolve_user_email(username, tenant_id)
        if not to_email:
            logger.warning("[Dispatch] Pas d email pour user=%s tenant=%s",
                           username, tenant_id)
            return

        # Construction du contenu
        emoji = {"critical": "🚨", "blocking": "🛑", "attention": "⚠️",
                 "warning": "🟡", "info": "🔵"}.get(severity, "")
        subject = f"{emoji} Raya — {title}"

        body_lines = [
            f"Severite : {severity.upper()}",
            "",
            message,
            "",
        ]
        if actions:
            body_lines.append("Actions suggerees :")
            for a in actions:
                body_lines.append(f"  - {a.get('label')}: {a.get('url', '')}")
            body_lines.append("")
        body_lines.append("Envoye par Raya — alert_dispatcher")

        body = "\n".join(body_lines)

        # Envoi via SMTP
        import smtplib
        from email.mime.text import MIMEText

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM", smtp_user)

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("[Dispatch] Email envoye a %s : %s", to_email, title)
    except Exception as e:
        logger.error("[Dispatch] Email echoue : %s", str(e)[:200])


def _send_sms_alert(severity, title, message, username, tenant_id):
    """Envoi SMS via Twilio."""
    try:
        from app.connectors.twilio_connector import send_sms
        phone = _resolve_user_phone(username, tenant_id)
        if not phone:
            logger.warning("[Dispatch] Pas de telephone pour user=%s", username)
            return

        emoji = {"critical": "🚨", "blocking": "🛑"}.get(severity, "⚠️")
        # SMS court : titre seul + lien vers l app
        text = f"{emoji} Raya — {title[:120]}"
        send_sms(phone, text)
        logger.info("[Dispatch] SMS envoye a %s : %s", phone, title)
    except Exception as e:
        logger.error("[Dispatch] SMS echoue : %s", str(e)[:200])


def _send_whatsapp_alert(severity, title, message, username, tenant_id):
    """Envoi WhatsApp via Twilio."""
    try:
        from app.connectors.twilio_connector import send_whatsapp
        phone = _resolve_user_phone(username, tenant_id)
        if not phone:
            return

        emoji = {"critical": "🚨", "blocking": "🛑", "attention": "⚠️"}.get(severity, "")
        full_message = f"{emoji} *Raya — {title}*\n\n{message}"
        send_whatsapp(phone, full_message[:1500])
        logger.info("[Dispatch] WhatsApp envoye a %s : %s", phone, title)
    except Exception as e:
        logger.error("[Dispatch] WhatsApp echoue : %s", str(e)[:200])


# ─── HELPERS RESOLUTION USER ───

def _resolve_user_email(username: Optional[str], tenant_id: str) -> Optional[str]:
    """Trouve l email du user pour les notifications.
    Si username None : on prend le tenant_admin du tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if username:
            c.execute(
                "SELECT email FROM users WHERE username = %s AND tenant_id = %s LIMIT 1",
                (username, tenant_id),
            )
        else:
            c.execute("""
                SELECT email FROM users
                WHERE tenant_id = %s AND scope IN ('tenant_admin', 'super_admin')
                ORDER BY scope DESC LIMIT 1
            """, (tenant_id,))
        row = c.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None
    finally:
        if conn: conn.close()


def _resolve_user_phone(username: Optional[str], tenant_id: str) -> Optional[str]:
    """Trouve le telephone du user pour SMS/WhatsApp.

    Priorite :
      1. users.phone (champ DB depuis 14/04)
      2. NOTIFICATION_PHONE_<USERNAME> env var
      3. NOTIFICATION_PHONE_DEFAULT env var
    """
    if username:
        try:
            from app.security_users import get_user_phone
            phone = get_user_phone(username)
            if phone:
                return phone
        except Exception:
            pass

    if username:
        env_phone = os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "").strip()
        if env_phone:
            return env_phone

    return os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip() or None


# ─── AUTO-ESCALATION (job a creer plus tard) ───

def check_auto_escalations() -> int:
    """A appeler regulierement (job nocturne ou toutes les 10 min) pour
    detecter les alertes critical non acquittees qui doivent etre
    re-emises au niveau superieur (blocking).

    Retourne le nb d alertes auto-escaladees.
    """
    conn = None
    escalated = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Lit toutes les alertes critical non acquittees avec un timer d escalation
        c.execute("""
            SELECT id, tenant_id, alert_type, component, message, details, created_at
            FROM system_alerts
            WHERE severity = 'critical'
              AND acknowledged = FALSE
              AND details ? 'auto_escalate_after_minutes'
              AND (details->>'auto_escalate_after_minutes')::int IS NOT NULL
        """)
        rows = c.fetchall()

        for r in rows:
            alert_id, tenant_id, alert_type, component, msg, details, created = r
            details = details or {}
            timeout_min = details.get("auto_escalate_after_minutes")
            if not timeout_min:
                continue

            elapsed_min = (datetime.now() - created).total_seconds() / 60
            if elapsed_min < timeout_min:
                continue

            # On escalate : envoi en 'blocking' + retire le timer
            details["escalated_from_critical_at"] = datetime.now().isoformat()
            details.pop("auto_escalate_after_minutes", None)
            send(
                severity="blocking",
                title=f"[ESCALADE] {details.get('title', 'Alerte critique non acquittee')}",
                message=msg,
                tenant_id=tenant_id,
                username=details.get("username"),
                actions=details.get("actions", []),
                source_type=details.get("source_type", "auto_escalation"),
                source_id=details.get("source_id"),
                component=component,
                alert_type=alert_type,
            )
            escalated += 1

        conn.commit()
        if escalated:
            logger.warning("[Dispatch] %d alerte(s) auto-escalades", escalated)
    except Exception as e:
        logger.error("[Dispatch] check_auto_escalations echoue : %s", str(e)[:200])
    finally:
        if conn: conn.close()
    return escalated
