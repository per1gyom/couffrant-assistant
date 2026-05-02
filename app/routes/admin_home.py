"""
Page d'accueil hub des outils admin.

Sert de menu central pour acceder a tous les outils admin de Raya
sans avoir a connaitre les URLs par coeur.

URL : GET /admin
Permission : require_admin (super_admin OU tenant_admin)

Les outils sont regroupes par categorie : Drive, Mail, Jobs, Connexions,
Utilisateurs, Audit. Chaque carte contient les liens vers les pages
existantes et un statut "disponible" s'il est connu.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from app.routes.deps import require_admin
from app.logging_config import get_logger

logger = get_logger("raya.admin_home")
router = APIRouter(tags=["admin_home"])


_HTML_HEAD = """<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Raya - Menu</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         max-width: 1200px; margin: 24px auto; padding: 0 24px;
         color: #2c3e50; background: #f8f9fa; }
  h1 { font-size: 24px; margin-bottom: 6px; }
  .subtitle { color: #7f8c8d; font-size: 14px; margin-bottom: 28px; }
  h2 { font-size: 16px; margin-top: 32px; color: #34495e;
       text-transform: uppercase; letter-spacing: 0.5px;
       border-bottom: 2px solid #3498db; padding-bottom: 6px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 14px; margin-top: 12px; }
  .tool-card { background: white; border-radius: 8px; padding: 16px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.08);
               transition: box-shadow 0.2s, transform 0.2s; }
  .tool-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                     transform: translateY(-2px); }
  .tool-icon { font-size: 24px; margin-bottom: 8px; }
  .tool-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
  .tool-desc { font-size: 12px; color: #7f8c8d; margin-bottom: 10px;
               line-height: 1.4; }
  .tool-link { display: inline-block; padding: 5px 12px; border-radius: 4px;
               background: #3498db; color: white; text-decoration: none;
               font-size: 12px; font-weight: 500; }
  .tool-link:hover { background: #2980b9; }
  .tool-link.secondary { background: white; color: #3498db;
                         border: 1px solid #3498db; }
  .tool-link.secondary:hover { background: #3498db; color: white; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: 10px; font-weight: 500; margin-left: 6px; }
  .badge-new { background: #d4edda; color: #155724; }
  .badge-beta { background: #fef9e7; color: #7d6608; }
  .info { background: #e8f4fd; padding: 10px 14px; border-radius: 4px;
          margin-bottom: 12px; font-size: 13px; color: #0c5494; }
  .scope-info { display: inline-block; padding: 4px 12px; border-radius: 4px;
                background: #ecf0f1; font-size: 12px; color: #34495e; }
</style>
</head><body>
"""


@router.get("/admin", response_class=HTMLResponse)
def admin_home(
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Page d accueil hub des outils admin.

    Liste toutes les pages admin accessibles selon le scope du user
    connecte. Les super_admin voient tout, les tenant_admin voient
    leurs outils tenant.
    """
    username = admin.get("username", "?")
    scope = admin.get("scope", "?")
    tenant_id = admin.get("tenant_id", "?")
    is_super = (scope == "super_admin")

    body = _HTML_HEAD
    body += f"""
<h1>🛠️ Admin Raya</h1>
<div class="subtitle">
  Connecte en tant que <b>{username}</b>
  <span class="scope-info">scope: {scope}</span>
  <span class="scope-info">tenant: {tenant_id}</span>
</div>

<h2>📁 Drive (SharePoint, Google Drive, NAS)</h2>
<div class="grid">
  <div class="tool-card">
    <div class="tool-icon">⚙️</div>
    <div class="tool-title">Configuration Drive
      <span class="badge badge-new">NOUVEAU</span>
    </div>
    <div class="tool-desc">
      Gerer les racines surveillees + regles inclusion/exclusion granulaires
      par dossier. Logique "le chemin le plus long gagne".
    </div>
    <a class="tool-link" href="/admin/drive_config">Ouvrir</a>
  </div>
</div>
"""

    body += """
<h2>📧 Mail (Gmail, Outlook)</h2>
<div class="grid">
  <div class="tool-card">
    <div class="tool-icon">📡</div>
    <div class="tool-title">Etat Pub/Sub Gmail
      <span class="badge badge-new">NOUVEAU</span>
    </div>
    <div class="tool-desc">
      Monitoring temps-reel des push Pub/Sub Gmail recus
      (auto-refresh 15s). Verifie la sante du systeme.
    </div>
    <a class="tool-link" href="/admin/jobs/gmail/pubsub_status">Ouvrir</a>
  </div>
</div>
"""

    if is_super:
        body += """
<h2>⏰ Jobs scheduler</h2>
<div class="grid">
  <div class="tool-card">
    <div class="tool-icon">📋</div>
    <div class="tool-title">Statut scheduler</div>
    <div class="tool-desc">
      Liste de tous les jobs APScheduler avec leur prochaine execution.
    </div>
    <a class="tool-link" href="/admin/jobs/scheduler_status">Ouvrir</a>
  </div>
  <div class="tool-card">
    <div class="tool-icon">▶️</div>
    <div class="tool-title">Setup Watches Gmail</div>
    <div class="tool-desc">
      Declenche manuellement la creation/renouvellement des watches Gmail.
      Affiche le resultat detaille par boite.
    </div>
    <a class="tool-link" href="/admin/jobs/gmail/setup_watches">Ouvrir</a>
  </div>
</div>
"""

        body += """
<h2>🔌 Connexions externes</h2>
<div class="grid">
  <div class="tool-card">
    <div class="tool-icon">🔵</div>
    <div class="tool-title">SharePoint sites</div>
    <div class="tool-desc">
      Lister les sites SharePoint accessibles par token Microsoft du
      super-admin. Pour selectionner un nouveau site a connecter.
    </div>
    <a class="tool-link secondary"
       href="/admin/sharepoint/sites/couffrant_solar">Ouvrir (couffrant_solar)</a>
  </div>
  <div class="tool-card">
    <div class="tool-icon">🟢</div>
    <div class="tool-title">Google Drive folders</div>
    <div class="tool-desc">
      Lister les dossiers Google Drive accessibles par token Gmail du
      super-admin. Pour selectionner un dossier a connecter.
    </div>
    <a class="tool-link secondary"
       href="/admin/drive/folders/couffrant_solar">Ouvrir (couffrant_solar)</a>
  </div>
</div>
"""

    # Liens utiles toujours dispos
    body += """
<h2>📊 Audit & sante</h2>
<div class="grid">
  <div class="tool-card">
    <div class="tool-icon">❤️</div>
    <div class="tool-title">Health check</div>
    <div class="tool-desc">
      Statut general de l app (liveness probe). Doit etre 200 OK.
    </div>
    <a class="tool-link secondary" href="/health">Ouvrir</a>
  </div>
</div>

<div class="info" style="margin-top: 32px;">
  <b>💡 Astuce</b> : tu peux mettre cette page <code>/admin</code> en
  favori dans ton navigateur pour acceder rapidement a tous les outils
  admin de Raya.
</div>
</body></html>
"""
    return HTMLResponse(body)
