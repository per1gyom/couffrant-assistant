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
from typing import List
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from app.database import get_pg_conn
from app.routes.deps import require_super_admin

router = APIRouter(prefix="/admin/rules", tags=["admin", "rules"])


# ─── ENDPOINT POST : execution de la migration ───

@router.post("/migrate")
def migrate_rules_between_tenants(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_super_admin),
):
    """
    Deplace un ensemble de regles d un tenant (context) vers un autre.

    Body JSON attendu :
      {
        "from_context": "couffrant_solar",
        "to_context": "juillet_utilisateurs",
        "username": "Charlotte",          # optionnel : filtre supplementaire
        "rule_ids": [92, 93, 94, ...]     # liste explicite des IDs a deplacer
      }

    Retourne :
      {
        "status": "ok",
        "moved": 10,
        "moved_ids": [92, 93, ...],
        "skipped_ids": []
      }
    """
    from_context = (payload.get("from_context") or "").strip()
    to_context = (payload.get("to_context") or "").strip()
    username_filter = (payload.get("username") or "").strip()
    rule_ids = payload.get("rule_ids") or []

    # Validations basiques
    if not from_context or not to_context:
        raise HTTPException(status_code=400, detail="from_context et to_context requis")
    if from_context == to_context:
        raise HTTPException(status_code=400, detail="from_context et to_context doivent etre differents")
    if not isinstance(rule_ids, list) or not rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids doit etre une liste non vide")
    # Securite : on limite a 200 IDs max par appel
    if len(rule_ids) > 200:
        raise HTTPException(status_code=400, detail="Max 200 rule_ids par appel")
    # On verifie que tous les IDs sont des entiers
    try:
        rule_ids = [int(x) for x in rule_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rule_ids doit contenir uniquement des entiers")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # 1) Verification prealable : on recupere les regles concernees
        #    AVEC filtre strict (from_context + username si fourni)
        if username_filter:
            c.execute(
                """
                SELECT id, username, context, category, substring(rule, 1, 80)
                FROM aria_rules
                WHERE id = ANY(%s) AND context = %s AND username = %s
                """,
                (rule_ids, from_context, username_filter),
            )
        else:
            c.execute(
                """
                SELECT id, username, context, category, substring(rule, 1, 80)
                FROM aria_rules
                WHERE id = ANY(%s) AND context = %s
                """,
                (rule_ids, from_context),
            )
        rows = c.fetchall()
        matched_ids = [r[0] for r in rows]
        skipped_ids = [rid for rid in rule_ids if rid not in matched_ids]

        if not matched_ids:
            return JSONResponse(
                {
                    "status": "no_match",
                    "moved": 0,
                    "moved_ids": [],
                    "skipped_ids": skipped_ids,
                    "message": (
                        "Aucune regle ne correspond aux criteres "
                        f"(from_context={from_context}, username={username_filter or 'ANY'})"
                    ),
                },
                status_code=200,
            )

        # 2) UPDATE strict : on change context -> to_context
        #    en verifiant le from_context pour eviter de modifier par erreur
        if username_filter:
            c.execute(
                """
                UPDATE aria_rules
                SET context = %s, updated_at = NOW()
                WHERE id = ANY(%s) AND context = %s AND username = %s
                """,
                (to_context, matched_ids, from_context, username_filter),
            )
        else:
            c.execute(
                """
                UPDATE aria_rules
                SET context = %s, updated_at = NOW()
                WHERE id = ANY(%s) AND context = %s
                """,
                (to_context, matched_ids, from_context),
            )
        moved_count = c.rowcount
        conn.commit()

        return JSONResponse(
            {
                "status": "ok",
                "moved": moved_count,
                "moved_ids": matched_ids,
                "skipped_ids": skipped_ids,
                "from_context": from_context,
                "to_context": to_context,
                "username_filter": username_filter or None,
                "triggered_by": user["username"],
            }
        )

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur migration : {str(e)[:200]}")
    finally:
        if conn:
            conn.close()


# ─── ENDPOINT GET : page HTML de declenchement ───

_MIGRATE_UI_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Migration des regles entre tenants — Raya Admin</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #222; }}
    h1 {{ color: #1a1a2e; }}
    .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 20px 0; }}
    .rule {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px; margin: 8px 0; }}
    .rule b {{ color: #6c757d; }}
    label {{ display: block; margin: 12px 0 4px; font-weight: 600; }}
    input[type=text], textarea {{ width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-family: monospace; }}
    button {{ background: #1a1a2e; color: white; border: 0; padding: 12px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; }}
    button:hover {{ background: #333; }}
    button:disabled {{ background: #888; cursor: not-allowed; }}
    #result {{ margin-top: 20px; padding: 15px; border-radius: 4px; white-space: pre-wrap; font-family: monospace; display: none; }}
    .success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
    .error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
  </style>
</head>
<body>
  <h1>🔄 Migration des regles entre tenants</h1>
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
    (async () => {{
      try {{
        const resp = await fetch('/admin/rules/preview?context=couffrant_solar&username=Charlotte');
        if (resp.ok) {{
          const data = await resp.json();
          const div = document.getElementById('preview');
          if (data.rules && data.rules.length) {{
            div.innerHTML = data.rules.map(r =>
              `<div class="rule"><b>#${{r.id}} [${{r.category}}]</b> ${{r.rule_extract}}</div>`
            ).join('');
          }} else {{
            div.innerHTML = '<i>Aucune regle trouvee pour ces criteres.</i>';
          }}
        }} else {{
          document.getElementById('preview').innerHTML = '<i>Impossible de charger le preview.</i>';
        }}
      }} catch(e) {{
        document.getElementById('preview').innerHTML = '<i>Erreur : ' + e.message + '</i>';
      }}
    }})();

    async function executeMigration() {{
      const btn = document.getElementById('btn');
      const result = document.getElementById('result');
      btn.disabled = true;
      btn.textContent = 'Migration en cours...';
      result.style.display = 'none';

      const rule_ids = document.getElementById('rule_ids').value
        .split(',')
        .map(s => parseInt(s.trim(), 10))
        .filter(n => !isNaN(n));

      const payload = {{
        from_context: document.getElementById('from_context').value.trim(),
        to_context: document.getElementById('to_context').value.trim(),
        username: document.getElementById('username_filter').value.trim(),
        rule_ids: rule_ids,
      }};

      try {{
        const resp = await fetch('/admin/rules/migrate', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const data = await resp.json();
        result.className = resp.ok && data.status === 'ok' ? 'success' : 'error';
        result.style.display = 'block';
        result.textContent = JSON.stringify(data, null, 2);
      }} catch(e) {{
        result.className = 'error';
        result.style.display = 'block';
        result.textContent = 'Erreur reseau : ' + e.message;
      }} finally {{
        btn.disabled = false;
        btn.textContent = 'Executer la migration';
      }}
    }}
  </script>
</body>
</html>"""


@router.get("/migrate-ui", response_class=HTMLResponse)
def migrate_ui(
    request: Request,
    user: dict = Depends(require_super_admin),
):
    """Page HTML pre-remplie pour declencher la migration Charlotte."""
    return HTMLResponse(content=_MIGRATE_UI_HTML)


@router.get("/preview")
def preview_rules(
    request: Request,
    context: str = "",
    username: str = "",
    user: dict = Depends(require_super_admin),
):
    """Preview des regles correspondant aux criteres (pour le form UI)."""
    if not context:
        return {"rules": []}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if username:
            c.execute(
                """
                SELECT id, category, substring(rule, 1, 100)
                FROM aria_rules
                WHERE context = %s AND username = %s
                ORDER BY id
                LIMIT 50
                """,
                (context, username),
            )
        else:
            c.execute(
                """
                SELECT id, category, substring(rule, 1, 100)
                FROM aria_rules
                WHERE context = %s
                ORDER BY id
                LIMIT 50
                """,
                (context,),
            )
        rows = c.fetchall()
        return {
            "rules": [
                {"id": r[0], "category": r[1], "rule_extract": r[2]} for r in rows
            ]
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()
