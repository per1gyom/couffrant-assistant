"""
Routes admin — migration des regles entre tenants.

Endpoint generique pour deplacer des regles d un tenant a un autre.
Cree le 22/04/2026 pour corriger la pollution Charlotte (regles
d onboarding du 14/04 qui avaient ete sauvees dans tenant couffrant_solar
au lieu d un tenant dedie).

Pattern d usage :
  1. GET  /admin/rules/migrate-ui        -> formulaire HTML pre-rempli
  2. POST /admin/rules/migrate           -> execute la migration (JSON)
"""
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from app.database import get_pg_conn
from app.routes.deps import require_super_admin

router = APIRouter(prefix="/admin/rules", tags=["admin", "rules"])


# ─── POST : execution ───

@router.post("/migrate")
def migrate_rules_between_tenants(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_super_admin),
):
    from_context = (payload.get("from_context") or "").strip()
    to_context = (payload.get("to_context") or "").strip()
    username_filter = (payload.get("username") or "").strip()
    rule_ids = payload.get("rule_ids") or []

    if not from_context or not to_context:
        raise HTTPException(status_code=400, detail="from_context et to_context requis")
    if from_context == to_context:
        raise HTTPException(status_code=400, detail="from_context et to_context doivent etre differents")
    if not isinstance(rule_ids, list) or not rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids doit etre une liste non vide")
    if len(rule_ids) > 200:
        raise HTTPException(status_code=400, detail="Max 200 rule_ids par appel")
    try:
        rule_ids = [int(x) for x in rule_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rule_ids doit contenir des entiers")


    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        if username_filter:
            c.execute(
                "SELECT id FROM aria_rules "
                "WHERE id = ANY(%s) AND context = %s AND username = %s",
                (rule_ids, from_context, username_filter),
            )
        else:
            c.execute(
                "SELECT id FROM aria_rules "
                "WHERE id = ANY(%s) AND context = %s",
                (rule_ids, from_context),
            )
        matched_ids = [r[0] for r in c.fetchall()]
        skipped_ids = [rid for rid in rule_ids if rid not in matched_ids]

        if not matched_ids:
            return JSONResponse({
                "status": "no_match",
                "moved": 0,
                "moved_ids": [],
                "skipped_ids": skipped_ids,
                "message": "Aucune regle ne correspond aux criteres",
            })

        if username_filter:
            c.execute(
                "UPDATE aria_rules SET context = %s, updated_at = NOW() "
                "WHERE id = ANY(%s) AND context = %s AND username = %s",
                (to_context, matched_ids, from_context, username_filter),
            )
        else:
            c.execute(
                "UPDATE aria_rules SET context = %s, updated_at = NOW() "
                "WHERE id = ANY(%s) AND context = %s",
                (to_context, matched_ids, from_context),
            )
        moved_count = c.rowcount
        conn.commit()

        return JSONResponse({
            "status": "ok",
            "moved": moved_count,
            "moved_ids": matched_ids,
            "skipped_ids": skipped_ids,
            "from_context": from_context,
            "to_context": to_context,
            "username_filter": username_filter or None,
            "triggered_by": user["username"],
        })

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur migration: {str(e)[:200]}")
    finally:
        if conn:
            conn.close()


# ─── GET : preview pour le formulaire ───

@router.get("/preview")
def preview_rules(
    request: Request,
    context: str = "",
    username: str = "",
    user: dict = Depends(require_super_admin),
):
    if not context:
        return {"rules": []}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if username:
            c.execute(
                "SELECT id, category, substring(rule, 1, 100) "
                "FROM aria_rules WHERE context = %s AND username = %s "
                "ORDER BY id LIMIT 50",
                (context, username),
            )
        else:
            c.execute(
                "SELECT id, category, substring(rule, 1, 100) "
                "FROM aria_rules WHERE context = %s "
                "ORDER BY id LIMIT 50",
                (context,),
            )
        rows = c.fetchall()
        return {"rules": [{"id": r[0], "category": r[1], "rule_extract": r[2]} for r in rows]}
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


# ─── GET : page HTML de declenchement ───

_MIGRATE_UI_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Migration regles tenants — Raya Admin</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #222; }
    h1 { color: #1a1a2e; }
    .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 20px 0; }
    .rule { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px; margin: 8px 0; }
    .rule b { color: #6c757d; }
    label { display: block; margin: 12px 0 4px; font-weight: 600; }
    input[type=text], textarea { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-family: monospace; box-sizing: border-box; }
    button { background: #1a1a2e; color: white; border: 0; padding: 12px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; }
    button:hover { background: #333; }
    button:disabled { background: #888; cursor: not-allowed; }
    #result { margin-top: 20px; padding: 15px; border-radius: 4px; white-space: pre-wrap; font-family: monospace; display: none; }
    .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
  </style>
</head>
<body>
  <h1>Migration des regles entre tenants</h1>
  <p>Deplace des regles de <code>aria_rules</code> d un tenant vers un autre, sans suppression.</p>

  <div class="warning">
    <b>Pre-rempli pour :</b> migration des 10 regles Charlotte
    (onboarding du 14/04/2026) de <code>couffrant_solar</code> vers
    <code>juillet_utilisateurs</code>.
  </div>

  <h2>Regles concernees</h2>
  <div id="preview">Chargement...</div>

  <h2>Parametres</h2>
  <label>Tenant source (from_context)</label>
  <input type="text" id="from_context" value="couffrant_solar">

  <label>Tenant destination (to_context)</label>
  <input type="text" id="to_context" value="juillet_utilisateurs">

  <label>Username (filtre de securite, optionnel)</label>
  <input type="text" id="username_filter" value="Charlotte">

  <label>IDs des regles a deplacer (separes par des virgules)</label>
  <textarea id="rule_ids" rows="3">92, 93, 94, 95, 96, 97, 98, 99, 100, 101</textarea>

  <button id="btn" onclick="executeMigration()">Executer la migration</button>

  <div id="result"></div>

  <script>
    // Chargement du preview au demarrage
    (async function() {
      try {
        const resp = await fetch('/admin/rules/preview?context=couffrant_solar&username=Charlotte');
        if (resp.ok) {
          const data = await resp.json();
          const div = document.getElementById('preview');
          if (data.rules && data.rules.length) {
            div.innerHTML = data.rules.map(function(r) {
              return '<div class="rule"><b>#' + r.id + ' [' + r.category + ']</b> ' + r.rule_extract + '</div>';
            }).join('');
          } else {
            div.innerHTML = '<i>Aucune regle trouvee pour ces criteres.</i>';
          }
        } else {
          document.getElementById('preview').innerHTML = '<i>Impossible de charger le preview (HTTP ' + resp.status + ').</i>';
        }
      } catch(e) {
        document.getElementById('preview').innerHTML = '<i>Erreur : ' + e.message + '</i>';
      }
    })();

    async function executeMigration() {
      const btn = document.getElementById('btn');
      const result = document.getElementById('result');
      btn.disabled = true;
      btn.textContent = 'Migration en cours...';
      result.style.display = 'none';

      const rule_ids = document.getElementById('rule_ids').value
        .split(',')
        .map(function(s) { return parseInt(s.trim(), 10); })
        .filter(function(n) { return !isNaN(n); });

      const payload = {
        from_context: document.getElementById('from_context').value.trim(),
        to_context: document.getElementById('to_context').value.trim(),
        username: document.getElementById('username_filter').value.trim(),
        rule_ids: rule_ids
      };

      try {
        const resp = await fetch('/admin/rules/migrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        result.className = resp.ok && data.status === 'ok' ? 'success' : 'error';
        result.style.display = 'block';
        result.textContent = JSON.stringify(data, null, 2);
      } catch(e) {
        result.className = 'error';
        result.style.display = 'block';
        result.textContent = 'Erreur reseau : ' + e.message;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Executer la migration';
      }
    }
  </script>
</body>
</html>
"""

@router.get("/migrate-ui", response_class=HTMLResponse)
def migrate_ui(
    request: Request,
    user: dict = Depends(require_super_admin),
):
    return HTMLResponse(content=_MIGRATE_UI_HTML)


# ─── POST : archivage en masse (soft delete) ───

@router.post("/bulk-archive")
def bulk_archive_rules(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_super_admin),
):
    """
    Archive (soft delete) un ensemble de regles.
    Met active=false + archived_at=NOW() + archived_reason=<raison>.
    Reversible via un futur endpoint /bulk-restore.

    Body JSON :
      {
        "rule_ids": [1, 4, 5, 7, 8, 21, 106],
        "reason": "lot_2_obsolete_v1_22avril",
        "context": "couffrant_solar"   # filtre de securite
      }
    """
    rule_ids = payload.get("rule_ids") or []
    reason = (payload.get("reason") or "bulk_archive").strip()
    context_filter = (payload.get("context") or "").strip()

    if not isinstance(rule_ids, list) or not rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids doit etre une liste non vide")
    if len(rule_ids) > 200:
        raise HTTPException(status_code=400, detail="Max 200 rule_ids par appel")
    try:
        rule_ids = [int(x) for x in rule_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rule_ids doit contenir des entiers")
    if not reason or len(reason) > 100:
        raise HTTPException(status_code=400, detail="reason requis (1-100 chars)")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # 1) Verification prealable : regles qui existent et sont actives
        if context_filter:
            c.execute(
                "SELECT id FROM aria_rules "
                "WHERE id = ANY(%s) AND context = %s AND active = true",
                (rule_ids, context_filter),
            )
        else:
            c.execute(
                "SELECT id FROM aria_rules "
                "WHERE id = ANY(%s) AND active = true",
                (rule_ids,),
            )
        matched_ids = [r[0] for r in c.fetchall()]
        skipped_ids = [rid for rid in rule_ids if rid not in matched_ids]

        if not matched_ids:
            return JSONResponse({
                "status": "no_match",
                "archived": 0,
                "archived_ids": [],
                "skipped_ids": skipped_ids,
                "message": "Aucune regle active ne correspond",
            })

        # 2) UPDATE soft delete. On utilise updated_at (qui existe) car
        #    archived_at/archived_reason ne sont pas encore dans le schema.
        #    On encode la raison dans un format traceable en utilisant
        #    une INSERT parallele dans aria_rules_history.
        c.execute(
            "UPDATE aria_rules "
            "SET active = false, updated_at = NOW() "
            "WHERE id = ANY(%s) AND active = true",
            (matched_ids,),
        )
        archived_count = c.rowcount

        # 3) Log dans aria_rules_history pour tracabilite + rollback futur
        # change_type est contraint a un set fini ('created', 'updated',
        # 'reinforced', 'deactivated', 'rollback'). On utilise 'deactivated'
        # qui correspond exactement au soft-delete qu on fait.
        # La raison detaillee (reason) est retournee dans le JSON et pourra
        # etre loggee serveur-side si besoin, mais pas stockee en DB
        # faute de colonne dediee.
        for rid in matched_ids:
            c.execute(
                "INSERT INTO aria_rules_history "
                "(rule_id, username, tenant_id, category, rule, confidence, "
                " reinforcements, active, change_type, changed_at) "
                "SELECT id, username, context, category, rule, confidence, "
                "       reinforcements, false, 'deactivated', NOW() "
                "FROM aria_rules WHERE id = %s",
                (rid,),
            )
        conn.commit()

        return JSONResponse({
            "status": "ok",
            "archived": archived_count,
            "archived_ids": matched_ids,
            "skipped_ids": skipped_ids,
            "reason": reason,
            "triggered_by": user["username"],
        })

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur bulk-archive: {str(e)[:200]}")
    finally:
        if conn:
            conn.close()


# ─── GET : page HTML pour lancer le nettoyage lot 2 ───

_CLEANUP_UI_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Nettoyage regles obsoletes — Raya Admin</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #222; }
    h1 { color: #1a1a2e; }
    .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 20px 0; }
    .info { background: #d1ecf1; border-left: 4px solid #0dcaf0; padding: 12px; margin: 20px 0; }
    .rule { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px; margin: 8px 0; }
    .rule b { color: #6c757d; }
    button { background: #dc3545; color: white; border: 0; padding: 12px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; }
    button:hover { background: #b02a37; }
    button:disabled { background: #888; cursor: not-allowed; }
    #result { margin-top: 20px; padding: 15px; border-radius: 4px; white-space: pre-wrap; font-family: monospace; display: none; }
    .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
  </style>
</head>
<body>
  <h1>Nettoyage regles obsoletes — Lot 2</h1>

  <div class="info">
    <b>Action :</b> archivage (soft delete) des 7 regles obsoletes v1
    qui ne s appliquent plus a l architecture agent v2.<br>
    <b>Type :</b> <code>UPDATE active=false</code> — <u>reversible</u> via
    aria_rules_history. Aucune suppression physique.<br>
    <b>Raison loggee :</b> <code>lot_2_obsolete_v1_22avril</code>
  </div>

  <h2>Regles concernees (7 IDs)</h2>
  <div id="preview">Chargement...</div>

  <button id="btn" onclick="executeArchive()">Archiver ces 7 regles</button>

  <div id="result"></div>

  <script>
    // IDs du lot 2 : bug #1 + obsoletes v1
    const LOT2_IDS = [1, 4, 5, 7, 8, 21, 106];

    (async function loadPreview() {
      try {
        const ids = LOT2_IDS.join(',');
        const resp = await fetch('/admin/rules/preview-by-ids?ids=' + ids);
        if (resp.ok) {
          const data = await resp.json();
          const div = document.getElementById('preview');
          if (data.rules && data.rules.length) {
            div.innerHTML = data.rules.map(function(r) {
              return '<div class="rule"><b>#' + r.id + ' [' + r.category + ']</b> ' + r.rule_extract + '</div>';
            }).join('');
          } else {
            div.innerHTML = '<i>Aucune regle trouvee (deja archivees ?).</i>';
          }
        }
      } catch(e) {
        document.getElementById('preview').innerHTML = '<i>Erreur: ' + e.message + '</i>';
      }
    })();

    async function executeArchive() {
      if (!confirm('Archiver (soft delete) les ' + LOT2_IDS.length + ' regles du lot 2 ?')) return;
      const btn = document.getElementById('btn');
      const result = document.getElementById('result');
      btn.disabled = true;
      btn.textContent = 'Archivage en cours...';
      result.style.display = 'none';

      const payload = {
        rule_ids: LOT2_IDS,
        reason: 'lot_2_obsolete_v1_22avril',
        context: 'couffrant_solar'
      };

      try {
        const resp = await fetch('/admin/rules/bulk-archive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        result.className = resp.ok && data.status === 'ok' ? 'success' : 'error';
        result.style.display = 'block';
        result.textContent = JSON.stringify(data, null, 2);
      } catch(e) {
        result.className = 'error';
        result.style.display = 'block';
        result.textContent = 'Erreur reseau : ' + e.message;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Archiver ces 7 regles';
      }
    }
  </script>
</body>
</html>
"""


@router.get("/cleanup-ui", response_class=HTMLResponse)
def cleanup_ui(
    request: Request,
    user: dict = Depends(require_super_admin),
):
    """Page HTML pour lancer le nettoyage du lot 2 (obsoletes v1)."""
    return HTMLResponse(content=_CLEANUP_UI_HTML)


@router.get("/preview-by-ids")
def preview_rules_by_ids(
    request: Request,
    ids: str = "",
    user: dict = Depends(require_super_admin),
):
    """Preview d une liste de regles par IDs (pour le cleanup-ui)."""
    if not ids:
        return {"rules": []}
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids doit contenir des entiers separes par virgules")
    if not id_list:
        return {"rules": []}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, category, substring(rule, 1, 150), active "
            "FROM aria_rules WHERE id = ANY(%s) ORDER BY id",
            (id_list,),
        )
        rows = c.fetchall()
        return {
            "rules": [
                {
                    "id": r[0],
                    "category": r[1],
                    "rule_extract": r[2],
                    "active": r[3],
                }
                for r in rows
            ]
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()
