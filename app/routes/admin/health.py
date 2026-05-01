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
    """Force un poll immediat sur une connexion (bouton 'Tester' dans l UI).

    Pour l instant retourne juste un message : l implementation reelle
    necessite que les connecteurs exposent une fonction force_poll().
    Sera implemente Semaines 2-6 quand les connecteurs seront branches
    sur l architecture commune.
    """
    return {
        "status": "not_implemented",
        "message": (
            "Force poll pas encore disponible. "
            "Sera operationnel quand les connecteurs seront branches "
            "sur l architecture commune (Semaines 2-6 de la roadmap)."
        ),
        "connection_id": connection_id,
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
