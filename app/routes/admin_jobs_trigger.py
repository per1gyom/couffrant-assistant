"""
Endpoints admin pour declencher manuellement certains jobs scheduler.

Utilise lors du bootstrap initial ou pour test/debug, quand on ne veut pas
attendre la prochaine execution programmee du scheduler.

Tous les endpoints sont proteges par require_super_admin (Guillaume seul).
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from app.routes.deps import require_super_admin
from app.logging_config import get_logger

logger = get_logger("raya.admin_jobs_trigger")
router = APIRouter(tags=["admin_jobs_trigger"])


def _do_gmail_watch_setup(admin_username: str) -> dict:
    """Coeur de la logique partage par les routes GET et POST.
    Capture before/after via la DB pour donner un retour utile a l UI.
    """
    from app.database import get_pg_conn
    from app.jobs.mail_gmail_watch import run_gmail_watch_renewal

    with get_pg_conn() as conn:
        c = conn.cursor()
        c.execute(
            """SELECT connection_id,
                      metadata->>'gmail_watch_history_id' as hid,
                      metadata->>'gmail_watch_expiration' as exp
               FROM connection_health
               WHERE connection_type='mail_gmail'
               ORDER BY connection_id"""
        )
        before = [
            {"connection_id": r[0], "history_id": r[1],
             "expiration": r[2]}
            for r in c.fetchall()
        ]

    logger.info(
        "[AdminTrigger] gmail_watch_renewal declenche manuellement par %s",
        admin_username,
    )
    run_gmail_watch_renewal()

    with get_pg_conn() as conn:
        c = conn.cursor()
        c.execute(
            """SELECT cc.id as connection_id, gt.email,
                      ch.metadata->>'gmail_watch_history_id' as hid,
                      ch.metadata->>'gmail_watch_expiration' as exp
               FROM tenant_connections cc
               LEFT JOIN connection_health ch ON ch.connection_id = cc.id
               LEFT JOIN gmail_tokens gt ON gt.id = (
                   SELECT id FROM gmail_tokens
                   WHERE username = (SELECT username FROM connection_assignments
                                      WHERE connection_id = cc.id LIMIT 1)
                   LIMIT 1
               )
               WHERE cc.tool_type = 'gmail' AND cc.status = 'connected'
               ORDER BY cc.id"""
        )
        after = [
            {"connection_id": r[0], "email": r[1] or "?",
             "history_id": r[2], "expiration": r[3]}
            for r in c.fetchall()
        ]

    before_map = {b["connection_id"]: b for b in before}
    created = 0
    renewed = 0
    failed = 0
    for a in after:
        cid = a["connection_id"]
        b = before_map.get(cid, {})
        if not b.get("history_id") and a.get("history_id"):
            created += 1
        elif b.get("expiration") and a.get("expiration") and \
                b.get("expiration") != a.get("expiration"):
            renewed += 1
        elif not a.get("history_id"):
            failed += 1

    return {
        "summary": {
            "total": len(after),
            "created": created,
            "renewed": renewed,
            "failed": failed,
        },
        "details_after": after,
    }


@router.post("/admin/jobs/gmail/setup_watches")
def admin_trigger_gmail_watch_setup_post(
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """Declenche immediatement run_gmail_watch_renewal() - version JSON."""
    try:
        result = _do_gmail_watch_setup(admin.get("username", "?"))
        return JSONResponse({"status": "ok", **result})
    except Exception as e:
        logger.error(
            "[AdminTrigger] gmail_watch_renewal crash : %s", str(e)[:300])
        return JSONResponse({
            "status": "error",
            "message": f"Crash : {str(e)[:200]}",
        }, status_code=500)


@router.get("/admin/jobs/gmail/setup_watches", response_class=HTMLResponse)
def admin_trigger_gmail_watch_setup_get(
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """Version GET cliquable depuis le navigateur. Affiche une page HTML
    avec le resultat lisible (pas du JSON brut).
    """
    try:
        result = _do_gmail_watch_setup(admin.get("username", "?"))
    except Exception as e:
        logger.error(
            "[AdminTrigger] gmail_watch_renewal crash : %s", str(e)[:300])
        return HTMLResponse(
            f"""<html><body style="font-family:system-ui;padding:30px;max-width:700px">
            <h1 style="color:#c00">❌ Erreur lors du setup des watches</h1>
            <p><b>Message :</b> {str(e)[:300]}</p>
            <p>Voir les logs Railway pour le detail.</p>
            <a href="/admin/health/page">← Retour au panel admin</a>
            </body></html>""",
            status_code=500,
        )

    s = result["summary"]
    rows_html = ""
    for d in result["details_after"]:
        ok = "✅" if d.get("history_id") else "❌"
        exp = d.get("expiration") or "—"
        # Conversion expiration ms -> date lisible
        if exp != "—" and exp.isdigit():
            try:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(int(exp) / 1000, tz=timezone.utc)
                exp = dt.strftime("%d/%m/%Y %H:%M UTC")
            except Exception:
                pass
        hid = d.get("history_id") or "—"
        rows_html += (
            f"<tr><td>{ok}</td>"
            f"<td>{d.get('email', '?')}</td>"
            f"<td>{hid}</td>"
            f"<td>{exp}</td></tr>"
        )

    if s["failed"] > 0:
        verdict_color = "#e67700"
        verdict_icon = "⚠️"
        verdict_msg = (
            f"{s['created']} watches creees, mais {s['failed']} en echec. "
            "Voir le tableau ci-dessous."
        )
    elif s["created"] > 0:
        verdict_color = "#2b8a3e"
        verdict_icon = "🎉"
        verdict_msg = (
            f"Les {s['created']} watches Gmail Pub/Sub ont ete creees. "
            "Pub/Sub est maintenant actif en mode SHADOW."
        )
    elif s["renewed"] > 0:
        verdict_color = "#2b8a3e"
        verdict_icon = "♻️"
        verdict_msg = f"{s['renewed']} watches renouvelees."
    else:
        verdict_color = "#1864ab"
        verdict_icon = "✅"
        verdict_msg = (
            "Toutes les watches existantes sont deja valides, "
            "rien a faire."
        )

    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8">
    <title>Setup Watches Gmail Pub/Sub</title>
    <style>
      body {{ font-family: system-ui, -apple-system, sans-serif;
              padding: 30px; max-width: 800px; margin: 0 auto;
              color: #333; }}
      h1 {{ color: #1864ab; }}
      .verdict {{ background: {verdict_color}11; border-left: 4px solid {verdict_color};
                 padding: 16px 20px; margin: 20px 0; border-radius: 4px;
                 font-size: 16px; }}
      .verdict-icon {{ font-size: 28px; margin-right: 12px; }}
      table {{ border-collapse: collapse; width: 100%;
              margin-top: 20px; font-size: 14px; }}
      th, td {{ text-align: left; padding: 10px 14px;
              border-bottom: 1px solid #ddd; }}
      th {{ background: #f1f3f5; font-weight: 600; }}
      .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
      .stat {{ background: #f8f9fa; padding: 14px 20px;
             border-radius: 6px; flex: 1; text-align: center; }}
      .stat-num {{ font-size: 28px; font-weight: 700; color: #1864ab; }}
      .stat-label {{ font-size: 12px; color: #666;
                    text-transform: uppercase; letter-spacing: 0.5px; }}
      a {{ color: #1864ab; }}
      .next {{ background: #fff9db; border-left: 4px solid #f59f00;
              padding: 16px 20px; margin-top: 30px; border-radius: 4px; }}
    </style></head>
    <body>
    <h1>📧 Setup des Watches Gmail Pub/Sub</h1>

    <div class="verdict">
      <span class="verdict-icon">{verdict_icon}</span>
      <b>{verdict_msg}</b>
    </div>

    <div class="summary">
      <div class="stat">
        <div class="stat-num">{s['total']}</div>
        <div class="stat-label">Boites Gmail</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#2b8a3e">{s['created']}</div>
        <div class="stat-label">Creees</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#1864ab">{s['renewed']}</div>
        <div class="stat-label">Renouvelees</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:{'#c92a2a' if s['failed'] else '#aaa'}">{s['failed']}</div>
        <div class="stat-label">Echec</div>
      </div>
    </div>

    <h3>Detail par boite Gmail</h3>
    <table>
      <thead><tr><th>Etat</th><th>Email</th><th>History ID</th><th>Expire le</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>

    <div class="next">
      <b>📌 Prochaine etape :</b><br>
      Si tu vois ✅ sur les 5 lignes, envoie-toi un mail test sur n importe
      laquelle des 5 boites Gmail. Dans 30 secondes a 1 minute, tu peux 
      verifier dans les logs Railway que la mention <b>[GmailPubSub][SHADOW]</b> 
      apparait : ca confirme que Pub/Sub a bien recu et achemine la 
      notification.
    </div>

    <p style="margin-top:30px"><a href="/admin/health/page">← Retour au panel admin</a></p>
    </body></html>
    """
    return HTMLResponse(html)


@router.get("/admin/jobs/scheduler_status")
def admin_scheduler_status(
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """Liste les jobs enregistres dans le scheduler avec leur prochaine
    execution. Utile pour verifier qu une variable Railway (SCHEDULER_*)
    a bien ete prise en compte au redeploiement.
    """
    try:
        from app.scheduler import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            return JSONResponse({
                "status": "error",
                "message": "Scheduler non initialise",
            }, status_code=500)
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": (job.next_run_time.isoformat()
                                   if job.next_run_time else None),
                "trigger": str(job.trigger),
            })
        return JSONResponse({
            "status": "ok",
            "total": len(jobs),
            "jobs": sorted(jobs, key=lambda j: j["id"]),
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Crash : {str(e)[:200]}",
        }, status_code=500)
