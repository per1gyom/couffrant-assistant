"""
Endpoints /admin/health — monitoring des connexions universelles.

Phase Connexions Universelles (1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

Endpoints :
  GET  /admin/health                       JSON : etat de toutes les connexions
  GET  /admin/health/connection/{id}       JSON : detail + 50 derniers events
  POST /admin/health/connection/{id}/poll  Force un poll immediat
  POST /admin/health/test-alert            Envoie une alerte test (debug)
  GET  /admin/health/page                  HTML : UI couleur tableau
"""
import os
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.routes.deps import require_admin

router = APIRouter()


@router.get("/admin/health")
def admin_health_summary(
    request: Request,
    tenant_id: Optional[str] = None,
    _: dict = Depends(require_admin),
):
    """Resume de l etat de toutes les connexions Raya.

    Si tenant_id absent : agrégat tous tenants (vue super_admin).
    Sinon : restreint au tenant.
    """
    try:
        from app.connection_health import get_status_summary
        return {"status": "ok", **get_status_summary(tenant_id=tenant_id)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/health/connection/{connection_id}")
def admin_health_connection_detail(
    request: Request,
    connection_id: int,
    limit: int = 50,
    _: dict = Depends(require_admin),
):
    """Detail d une connexion + ses N derniers events de poll."""
    try:
        from app.connection_health import get_status_summary, get_recent_events
        from app.connection_resilience import get_circuit_state

        # On recupere le summary global et on filtre la connexion demandee
        summary = get_status_summary()
        connection = next(
            (c for c in summary.get("connections", [])
             if c["connection_id"] == connection_id),
            None,
        )
        if not connection:
            return {"status": "error",
                    "message": f"Connexion {connection_id} non trouvee"}

        events = get_recent_events(connection_id, limit=min(max(1, limit), 200))
        circuit = get_circuit_state(connection_id)

        return {
            "status": "ok",
            "connection": connection,
            "circuit": circuit,
            "recent_events": events,
            "events_count": len(events),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/health/connection/{connection_id}/poll")
def admin_health_force_poll(
    request: Request,
    connection_id: int,
    _: dict = Depends(require_admin),
):
    """Test rapide d une connexion (bouton 'Tester' dans l UI).

    Effectue UN appel API minimal au service distant (Microsoft Graph /me,
    Gmail users.getProfile, etc.) avec gestion du refresh token. Retourne
    le resultat sans declencher un poll complet.

    Implementation 06/05/2026 (apres un mois d alerte spam sur conn_14
    et impossibilite de tester l etat sans reconnecter manuellement).

    En cas de succes : enregistre via record_poll_attempt(status='ok')
    -> declenche l auto-resolution des alertes connection_silence
    deja en place dans connection_health.py.

    En cas d echec : enregistre via record_poll_attempt(status='auth_error'
    ou 'api_error') -> permet le tracking historique des pannes.

    Reponse :
      {
        "ok": True/False,
        "http_code": 200/401/...,
        "reason": "OK - connecte a contact@..." ou "Token expire...",
        "duration_ms": 234,
        "tool_type": "microsoft",
        "connection_id": 14
      }
    """
    import time, json
    from app.database import get_pg_conn
    from app.connection_health import record_poll_attempt

    started = time.time()

    # 1. Recuperer la connexion
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tool_type, credentials, connected_email "
            "FROM tenant_connections WHERE id = %s",
            (connection_id,),
        )
        row = c.fetchone()
    finally:
        if conn: conn.close()

    if not row:
        return {
            "ok": False, "http_code": 404, "duration_ms": 0,
            "reason": f"Connexion {connection_id} introuvable",
            "connection_id": connection_id,
        }

    tool_type, credentials_raw, connected_email = row[0], row[1], row[2]

    # Parse credentials (peut etre dict ou str selon postgres driver)
    if isinstance(credentials_raw, str):
        try:
            creds = json.loads(credentials_raw)
        except Exception:
            creds = {}
    elif isinstance(credentials_raw, dict):
        creds = credentials_raw
    else:
        creds = {}

    # 2. Dispatch selon tool_type
    if tool_type in ("microsoft", "outlook", "drive"):
        result = _test_microsoft_connection(connection_id, tool_type, creds, started)
    elif tool_type in ("gmail", "google"):
        result = _test_gmail_connection(connection_id, creds, started)
    elif tool_type == "odoo":
        result = {
            "ok": False, "http_code": 0,
            "reason": "Test pas encore implemente pour Odoo (a venir)",
            "duration_ms": int((time.time() - started) * 1000),
        }
    else:
        result = {
            "ok": False, "http_code": 0,
            "reason": f"Test pas encore implemente pour tool_type={tool_type}",
            "duration_ms": int((time.time() - started) * 1000),
        }

    result["tool_type"] = tool_type
    result["connection_id"] = connection_id
    result["connected_email"] = connected_email
    return result


def _test_microsoft_connection(
    connection_id: int, tool_type: str, creds: dict, started: float
) -> dict:
    """Test Microsoft Graph : refresh token + appel /me.

    Si le refresh token est expire/revoque -> retourne 401.
    Si l API plante (ex: 503 Microsoft) -> retourne le code reel.
    Sinon -> 200 OK + email du compte connecte (du retour Graph).
    """
    import time
    from app.connection_token_manager import _refresh_v2_token
    from app.connection_health import record_poll_attempt
    from app.crypto import decrypt_token

    # 1. Decrypt refresh_token (les credentials V2 sont chiffres)
    refresh_token = creds.get("refresh_token")
    if refresh_token:
        try:
            refresh_token = decrypt_token(refresh_token)
        except Exception:
            pass  # peut-etre pas chiffre (legacy)

    if not refresh_token:
        try:
            record_poll_attempt(connection_id, status="auth_error",
                                error_detail="refresh_token absent")
        except Exception:
            pass
        return {
            "ok": False, "http_code": 401,
            "reason": "Pas de refresh_token en base - reconnexion requise",
            "duration_ms": int((time.time() - started) * 1000),
        }

    # 2. Tenter le refresh (= ce que fait un poll normal)
    new_access_token = _refresh_v2_token(connection_id, "microsoft",
                                          refresh_token, creds)
    if not new_access_token:
        try:
            record_poll_attempt(connection_id, status="auth_error",
                                error_detail="refresh OAuth a echoue")
        except Exception:
            pass
        return {
            "ok": False, "http_code": 401,
            "reason": "Refresh token expire ou revoque - reconnexion OAuth requise",
            "duration_ms": int((time.time() - started) * 1000),
        }

    # 3. Mini appel /me pour valider le token frais
    from app.graph_client import graph_get
    try:
        data = graph_get(new_access_token, "/me")
        try:
            record_poll_attempt(connection_id, status="ok")
        except Exception:
            pass
        upn = data.get("userPrincipalName") or data.get("mail") or "?"
        return {
            "ok": True, "http_code": 200,
            "reason": f"OK - connecte a {upn}",
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as e:
        msg = str(e)[:200]
        try:
            record_poll_attempt(connection_id, status="api_error",
                                error_detail=msg[:500])
        except Exception:
            pass
        # Detection des erreurs courantes
        if "401" in msg or "Unauthorized" in msg or "AADSTS" in msg:
            human_msg = "Token Microsoft expire - reconnexion OAuth requise"
            http_code = 401
        elif "403" in msg or "Forbidden" in msg:
            human_msg = "Permissions Microsoft revoquees - reconnexion requise"
            http_code = 403
        elif "503" in msg or "ServiceUnavailable" in msg:
            human_msg = "Microsoft Graph indisponible (503) - reessayer plus tard"
            http_code = 503
        else:
            human_msg = f"Erreur API Microsoft Graph : {msg[:120]}"
            http_code = 0
        return {
            "ok": False, "http_code": http_code,
            "reason": human_msg,
            "duration_ms": int((time.time() - started) * 1000),
        }


def _test_gmail_connection(
    connection_id: int, creds: dict, started: float
) -> dict:
    """Test Gmail : refresh token + appel users.getProfile."""
    import time, requests
    from app.connection_token_manager import _refresh_v2_token
    from app.connection_health import record_poll_attempt
    from app.crypto import decrypt_token

    refresh_token = creds.get("refresh_token")
    if refresh_token:
        try:
            refresh_token = decrypt_token(refresh_token)
        except Exception:
            pass

    if not refresh_token:
        try:
            record_poll_attempt(connection_id, status="auth_error",
                                error_detail="refresh_token absent")
        except Exception:
            pass
        return {
            "ok": False, "http_code": 401,
            "reason": "Pas de refresh_token en base - reconnexion requise",
            "duration_ms": int((time.time() - started) * 1000),
        }

    new_access_token = _refresh_v2_token(connection_id, "gmail",
                                          refresh_token, creds)
    if not new_access_token:
        try:
            record_poll_attempt(connection_id, status="auth_error",
                                error_detail="refresh OAuth Gmail echoue")
        except Exception:
            pass
        return {
            "ok": False, "http_code": 401,
            "reason": "Refresh token Gmail expire/revoque - reconnexion OAuth requise",
            "duration_ms": int((time.time() - started) * 1000),
        }

    try:
        r = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {new_access_token}"},
            timeout=15,
        )
        if r.status_code == 200:
            try:
                record_poll_attempt(connection_id, status="ok")
            except Exception:
                pass
            data = r.json()
            return {
                "ok": True, "http_code": 200,
                "reason": f"OK - connecte a {data.get('emailAddress', '?')} "
                          f"({data.get('messagesTotal', 0)} mails)",
                "duration_ms": int((time.time() - started) * 1000),
            }
        else:
            try:
                record_poll_attempt(connection_id, status="api_error",
                                    error_detail=f"HTTP {r.status_code}")
            except Exception:
                pass
            return {
                "ok": False, "http_code": r.status_code,
                "reason": f"Erreur Gmail HTTP {r.status_code} - {r.text[:100]}",
                "duration_ms": int((time.time() - started) * 1000),
            }
    except Exception as e:
        return {
            "ok": False, "http_code": 0,
            "reason": f"Erreur reseau Gmail : {str(e)[:150]}",
            "duration_ms": int((time.time() - started) * 1000),
        }


@router.post("/admin/health/test-alert")
def admin_health_test_alert(
    request: Request,
    severity: str = "warning",
    _: dict = Depends(require_admin),
):
    """Envoie une alerte test pour valider le dispatcher (debug).

    Severite acceptee : info / warning / attention / critical / blocking
    """
    try:
        from app.alert_dispatcher import send, SEVERITIES
        if severity not in SEVERITIES:
            return {"status": "error",
                    "message": f"Severite invalide. Acceptees : {SEVERITIES}"}

        from app.tenant_manager import get_user_tenants
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"

        sent = send(
            severity=severity,
            title=f"Test alerte {severity}",
            message=(f"Ceci est une alerte de test envoyee par le panel admin. "
                     f"Severite = {severity}. Si tu lis ceci dans le canal attendu, "
                     f"le dispatcher fonctionne."),
            tenant_id=tenant_id,
            username=request.session.get("username"),
            actions=[
                {"label": "Voir /admin/health", "url": "/admin/health/page"},
            ],
            source_type="manual_test",
            source_id=f"test_{severity}",
            component=f"test_{severity}",
            alert_type="manual_test",
        )
        return {"status": "ok" if sent else "partial",
                "message": f"Alerte test {severity} envoyee"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/health/page", response_class=HTMLResponse)
def admin_health_page(
    request: Request,
    _: dict = Depends(require_admin),
):
    """UI HTML simple pour visualiser l etat des connexions.

    Tableau avec une ligne par connexion :
      - Pastille couleur selon status (vert/jaune/orange/rouge/gris)
      - Type, tenant, last poll, silence, failures
      - Bouton 'Detail' qui ouvre /admin/health/connection/{id}

    Style minimaliste pour rester coherent avec l esprit panel admin Raya.
    """
    try:
        from app.connection_health import get_status_summary
        summary = get_status_summary()
        connections = summary.get("connections", [])
        total = summary.get("total", 0)
        healthy = summary.get("healthy", 0)
        degraded = summary.get("degraded", 0)
        down = summary.get("down", 0)
        circuit_open = summary.get("circuit_open", 0)
        unknown = summary.get("unknown", 0)

        # Construction du tableau HTML
        rows_html = []
        for c in connections:
            status = c.get("status", "unknown")
            color_map = {
                "healthy":      "#22c55e",  # vert
                "degraded":     "#eab308",  # jaune
                "down":         "#ef4444",  # rouge
                "circuit_open": "#a855f7",  # violet
                "unknown":      "#94a3b8",  # gris
            }
            color = color_map.get(status, "#94a3b8")
            silence = c.get("silence_seconds")
            silence_str = f"{silence // 60} min" if silence else "—"
            last_ok = c.get("last_successful_poll_at") or "—"

            in_alert = c.get("in_alert", False)
            alert_marker = " 🚨" if in_alert else ""

            rows_html.append(f"""
              <tr>
                <td style="padding:8px;">
                  <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{color}; margin-right:6px;"></span>
                  {status}{alert_marker}
                </td>
                <td style="padding:8px;">{c.get('connection_type','')}</td>
                <td style="padding:8px;">{c.get('tenant_id','')}</td>
                <td style="padding:8px;">{c.get('username','')}</td>
                <td style="padding:8px;">{last_ok}</td>
                <td style="padding:8px;">{silence_str}</td>
                <td style="padding:8px;">{c.get('consecutive_failures',0)}</td>
                <td style="padding:8px;">
                  <a href="/admin/health/connection/{c.get('connection_id')}" style="color:#2563eb;">Detail</a>
                </td>
              </tr>
            """)

        rows_str = "\n".join(rows_html) if rows_html else (
            '<tr><td colspan="8" style="padding:20px; text-align:center; color:#64748b;">'
            'Aucune connexion enregistree. Les connecteurs s inscriront ici '
            'au fur et a mesure qu ils seront branches sur l architecture commune (Semaines 2-6).'
            '</td></tr>'
        )

        # Boutons de test
        test_buttons = """
          <div style="margin:16px 0; padding:12px; background:#f1f5f9; border-radius:6px;">
            <strong>Tester le dispatcher d alertes :</strong><br>
            <button onclick="testAlert('info')" style="margin:4px;">Info</button>
            <button onclick="testAlert('warning')" style="margin:4px;">Warning</button>
            <button onclick="testAlert('attention')" style="margin:4px;">Attention</button>
            <button onclick="testAlert('critical')" style="margin:4px;">Critical</button>
            <button onclick="testAlert('blocking')" style="margin:4px;">Blocking</button>
            <span id="test-result" style="margin-left:12px; color:#64748b;"></span>
          </div>
          <script>
            async function testAlert(severity) {
              const resultEl = document.getElementById('test-result');
              resultEl.textContent = 'Envoi...';
              try {
                const r = await fetch('/admin/health/test-alert?severity=' + severity, {method:'POST'});
                const data = await r.json();
                resultEl.textContent = data.status === 'ok' ? '✅ ' + data.message : '❌ ' + data.message;
                resultEl.style.color = data.status === 'ok' ? '#16a34a' : '#dc2626';
              } catch (e) {
                resultEl.textContent = '❌ Erreur : ' + e.message;
                resultEl.style.color = '#dc2626';
              }
            }
          </script>
        """

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Raya — /admin/health</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color:#0f172a; }}
    h1 {{ font-size: 24px; margin: 0 0 16px 0; }}
    .stats {{ display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap; }}
    .stat {{ padding:12px 16px; border-radius:6px; background:#f8fafc; border:1px solid #e2e8f0; min-width:80px; text-align:center; }}
    .stat .num {{ font-size:24px; font-weight:bold; }}
    .stat .lbl {{ font-size:12px; color:#64748b; text-transform:uppercase; }}
    table {{ width:100%; border-collapse: collapse; background: #fff; border:1px solid #e2e8f0; border-radius:8px; overflow:hidden; }}
    th {{ background:#f8fafc; text-align:left; padding:10px 8px; font-size:13px; color:#475569; text-transform:uppercase; border-bottom:1px solid #e2e8f0; }}
    tr:not(:last-child) td {{ border-bottom:1px solid #f1f5f9; }}
    a {{ text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .footer {{ margin-top:20px; font-size:13px; color:#64748b; }}
  </style>
</head>
<body>
  <h1>Raya — Sante des connexions</h1>
  <div class="stats">
    <div class="stat"><div class="num">{total}</div><div class="lbl">Total</div></div>
    <div class="stat"><div class="num" style="color:#22c55e">{healthy}</div><div class="lbl">Healthy</div></div>
    <div class="stat"><div class="num" style="color:#eab308">{degraded}</div><div class="lbl">Degraded</div></div>
    <div class="stat"><div class="num" style="color:#ef4444">{down}</div><div class="lbl">Down</div></div>
    <div class="stat"><div class="num" style="color:#a855f7">{circuit_open}</div><div class="lbl">Circuit Open</div></div>
    <div class="stat"><div class="num" style="color:#94a3b8">{unknown}</div><div class="lbl">Unknown</div></div>
  </div>
  {test_buttons}
  <table>
    <thead>
      <tr>
        <th>Status</th>
        <th>Type</th>
        <th>Tenant</th>
        <th>User</th>
        <th>Dernier poll OK</th>
        <th>Silence</th>
        <th>Echecs consec.</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {rows_str}
    </tbody>
  </table>
  <div class="footer">
    Phase Connexions Universelles - Etape 1.5 - 1er mai 2026<br>
    Voir docs/vision_connexions_universelles_01mai.md
  </div>
</body>
</html>"""
        return HTMLResponse(content=html)
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Erreur</h1><pre>{str(e)[:500]}</pre>",
            status_code=500,
        )


# ─── ENDPOINT POUR DECLENCHER LA CREATION/RENOUVELLEMENT DES WEBHOOKS ───
# Ajoute le 06/05/2026 pour pouvoir creer immediatement la subscription
# Microsoft Graph apres reconnexion d une boite (sans attendre le cron 6h).
# Aussi utile pour le chantier 'extension aux 3 dossiers' a venir.

@router.post("/admin/webhooks/ensure-now")
def admin_webhooks_ensure_now(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Declenche immediatement ensure_all_subscriptions() pour Microsoft.

    Equivalent du cron _job_webhook_renewal mais a la demande. Cree les
    subscriptions manquantes et renouvelle celles qui expirent dans <24h.

    Reservé super_admin.
    """
    try:
        from app.connectors.microsoft_webhook import ensure_all_subscriptions
        from app.database import get_pg_conn
        import time

        # Snapshot AVANT pour mesurer le delta
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT connection_id FROM webhook_subscriptions")
            subs_before = set(r[0] for r in cur.fetchall() if r[0])

        started = time.time()
        ensure_all_subscriptions()
        duration_ms = int((time.time() - started) * 1000)

        # Snapshot APRES
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT ws.connection_id, ws.subscription_id, ws.expires_at, ws.resource,
                       tc.label, tc.connected_email
                FROM webhook_subscriptions ws
                LEFT JOIN tenant_connections tc ON tc.id = ws.connection_id
                ORDER BY ws.connection_id
            """)
            subs_after_raw = cur.fetchall()
            subs_after = set(r[0] for r in subs_after_raw if r[0])

        new_subs = subs_after - subs_before
        return {
            "status": "ok",
            "duration_ms": duration_ms,
            "subscriptions_total": len(subs_after_raw),
            "subscriptions_new": list(new_subs),
            "subscriptions": [
                {
                    "connection_id": r[0],
                    "subscription_id": r[1],
                    "expires_at": r[2].isoformat() if r[2] else None,
                    "resource": r[3],
                    "label": r[4],
                    "email": r[5],
                }
                for r in subs_after_raw
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Echec ensure_all_subscriptions : {str(e)[:200]}")


# ─── ENDPOINT DEBUG : tester la creation de sub pour une connexion ───
# Ajoute le 06/05/2026 pour comprendre pourquoi conn=14 (contact@) ne
# recoit pas de subscription Microsoft Graph alors que conn=6 oui.
# Retourne le code HTTP et le message d erreur Microsoft Graph en clair.

@router.post("/admin/webhooks/test-subscription/{connection_id}")
def admin_webhook_test_subscription(
    connection_id: int,
    request: Request,
    _: dict = Depends(require_admin),
):
    """Tente de creer une subscription Microsoft Graph pour une connexion
    et retourne la reponse exacte de Microsoft (code + body).

    Permet de comprendre pourquoi une creation echoue (scope manquant,
    compte sans inbox personnelle, shared mailbox, etc.).
    """
    try:
        from app.database import get_pg_conn
        from app.connection_token_manager import decrypt_token
        import requests
        import json
        import secrets
        from datetime import datetime, timezone, timedelta

        # 1. Recupere infos connexion + decrypted token
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT tc.tool_type, tc.label, tc.connected_email,
                       tc.credentials, tc.tenant_id,
                       ca.username
                FROM tenant_connections tc
                LEFT JOIN connection_assignments ca ON ca.connection_id = tc.id
                WHERE tc.id = %s
                LIMIT 1
            """, (connection_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"Connexion #{connection_id} introuvable")
            tool_type, label, connected_email, creds_raw, tenant_id, username = row

        if tool_type not in ("microsoft", "outlook"):
            raise HTTPException(
                400,
                f"Connexion #{connection_id} de type '{tool_type}' - les "
                f"webhooks Microsoft Graph ne s appliquent qu aux "
                f"types microsoft/outlook"
            )

        creds = creds_raw if isinstance(creds_raw, dict) else json.loads(creds_raw)
        token_enc = creds.get("access_token", "")
        if not token_enc:
            raise HTTPException(500, "Pas d access_token en base pour cette connexion")

        token = decrypt_token(token_enc)

        # 2. Tester /me pour voir quel compte le token represente VRAIMENT
        me_resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        me_data = {}
        if me_resp.status_code == 200:
            me_data = me_resp.json()

        # 3. Tenter la creation de subscription EN MODE TEST (clientState random)
        from app.connectors.microsoft_webhook import (
            get_notification_url, get_lifecycle_notification_url, SUBSCRIPTION_DAYS
        )

        expiry = (datetime.now(timezone.utc) + timedelta(days=SUBSCRIPTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client_state = secrets.token_hex(16)

        sub_resp = requests.post(
            "https://graph.microsoft.com/v1.0/subscriptions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "changeType": "created",
                "notificationUrl": get_notification_url(),
                "lifecycleNotificationUrl": get_lifecycle_notification_url(),
                "resource": "me/mailFolders/inbox/messages",
                "expirationDateTime": expiry,
                "clientState": client_state,
            },
            timeout=15,
        )

        sub_body = {}
        try:
            sub_body = sub_resp.json()
        except Exception:
            sub_body = {"raw_text": sub_resp.text[:500]}

        # Si creation reussie, on l'enregistre + on cleanup la sub de test
        # NON : si succes, on la GARDE car on en a besoin
        if sub_resp.status_code in (200, 201):
            from app.connectors.microsoft_webhook import _save_subscription
            _save_subscription(
                username or "unknown",
                sub_body["id"],
                sub_body["expirationDateTime"],
                client_state,
                connection_id=connection_id,
            )

        return {
            "connection_id": connection_id,
            "label": label,
            "expected_email": connected_email,
            "tool_type": tool_type,
            "username_assigned": username,
            "token_real_account": {
                "userPrincipalName": me_data.get("userPrincipalName"),
                "mail": me_data.get("mail"),
                "displayName": me_data.get("displayName"),
                "id": me_data.get("id"),
            },
            "me_call_status": me_resp.status_code,
            "me_call_error": me_resp.text[:300] if me_resp.status_code != 200 else None,
            "subscription_create_status": sub_resp.status_code,
            "subscription_create_response": sub_body,
            "subscription_created": sub_resp.status_code in (200, 201),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur test : {str(e)[:200]}")
