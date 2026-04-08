import os
import threading
import requests as http_requests
from fastapi import APIRouter, Request, Body
from fastapi.responses import RedirectResponse, HTMLResponse
from app.database import get_pg_conn, init_postgres
from app.app_security import (
    create_user, delete_user, list_users, init_default_user,
    get_user_tools, set_user_tool, remove_user_tool, SCOPE_CS,
)
from app.token_manager import get_valid_microsoft_token
from app.routes.deps import require_admin

router = APIRouter(tags=["admin"])


# ─── Panel & users ───

@router.get("/admin/panel", response_class=HTMLResponse)
def admin_panel(request: Request):
    if not require_admin(request): return RedirectResponse("/login-app")
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/admin/users")
def admin_list_users(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    return list_users()


@router.post("/admin/create-user")
def admin_create_user(request: Request, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    return create_user(
        payload.get("username", "").strip(), payload.get("password", ""),
        payload.get("scope", SCOPE_CS), payload.get("tools"),
    )


@router.delete("/admin/delete-user/{target_username}")
def admin_delete_user(request: Request, target_username: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    return delete_user(target_username, request.session.get("user", ""))


# ─── Rules & insights ───

@router.get("/admin/rules")
def admin_rules(request: Request, user: str = ""):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user:
            c.execute("SELECT id,username,category,rule,confidence,reinforcements,active,created_at FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC", (user,))
        else:
            c.execute("SELECT id,username,category,rule,confidence,reinforcements,active,created_at FROM aria_rules ORDER BY username,active DESC,confidence DESC")
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/admin/insights")
def admin_insights(request: Request, user: str = ""):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user:
            c.execute("SELECT id,username,topic,insight,reinforcements,created_at FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC", (user,))
        else:
            c.execute("SELECT id,username,topic,insight,reinforcements,created_at FROM aria_insights ORDER BY username,reinforcements DESC")
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/admin/memory-status")
def admin_memory_status(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, COUNT(*) FROM aria_memory GROUP BY username")
        conversations = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM aria_rules WHERE active=true GROUP BY username")
        rules = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM aria_insights GROUP BY username")
        insights = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM mail_memory GROUP BY username")
        mails = dict(c.fetchall())
        users_all = set(list(conversations) + list(rules) + list(insights) + list(mails))
        return [{"username": u, "conversations": conversations.get(u, 0), "rules": rules.get(u, 0),
                 "insights": insights.get(u, 0), "mails": mails.get(u, 0)} for u in sorted(users_all)]
    finally:
        if conn: conn.close()


# ─── Outils ───

@router.get("/admin/user-tools/{target_username}")
def admin_get_user_tools(request: Request, target_username: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    return get_user_tools(target_username, raw=True)


@router.post("/admin/user-tools/{target_username}/{tool}")
def admin_set_user_tool(request: Request, target_username: str, tool: str, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    return set_user_tool(target_username, tool,
        payload.get("access_level", "read_only"), payload.get("enabled", True), payload.get("config", {}))


@router.delete("/admin/user-tools/{target_username}/{tool}")
def admin_remove_user_tool(request: Request, target_username: str, tool: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.app_security import remove_user_tool as _remove
    return _remove(target_username, tool)


# ─── Misc admin (non-préfixés mais réservés admin) ───

@router.get("/init-db")
def init_db_now(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    init_postgres()
    try: init_default_user()
    except Exception: pass
    return {"status": "tables créées"}


@router.get("/test-elevenlabs")
def test_elevenlabs(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    resp = http_requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": "Bonjour.", "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        timeout=30
    )
    return {"status_code": resp.status_code, "api_key_length": len(api_key), "voice_id": voice_id}


@router.get("/test-odoo")
def test_odoo(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.connectors.odoo_connector import perform_odoo_action
    return perform_odoo_action(action="get_partner_by_email", params={"email": "guillaume@couffrant-solar.fr"})


@router.get("/reorganize-drive")
def reorganize_drive(request: Request):
    if not require_admin(request): return {"error": "Réservé à l'admin."}
    from app.connectors.outlook_connector import (
        _find_sharepoint_site_and_drive, _find_folder_item_id, _graph_get,
        create_drive_folder, copy_drive_item
    )
    username = request.session.get("user", "guillaume")
    token = get_valid_microsoft_token(username)
    if not token: return {"error": "Token Microsoft manquant"}
    _, drive_id, _ = _find_sharepoint_site_and_drive(token)
    if not drive_id: return {"error": "Drive SharePoint 'Commun' introuvable"}
    _, source_id = _find_folder_item_id(token, drive_id)
    if not source_id: return {"error": "Dossier 1_Photovoltaïque introuvable"}

    def run_reorganize():
        import time
        try:
            data = _graph_get(token, f"/drives/{drive_id}/items/{source_id}/children",
                             params={"$top": 100, "$select": "name,id,folder,file"})
            items_by_name = {f.get("name"): f.get("id") for f in data.get("value", [])}
            source_meta = _graph_get(token, f"/drives/{drive_id}/items/{source_id}",
                                     params={"$select": "id,parentReference"})
            parent_id = source_meta.get("parentReference", {}).get("id")
            if not parent_id: return

            def mk(parent, name):
                r = create_drive_folder(token, parent, name, drive_id)
                if r.get("status") == "ok": print(f"[Reorganize] ✅ {name}"); return r.get("id")
                return None

            def cp(source_name, dest_id, new_name=None):
                item_id = items_by_name.get(source_name)
                if not item_id: return
                r = copy_drive_item(token, item_id, dest_id, new_name, drive_id)
                print(f"[Reorganize] {'✅' if r.get('status')=='ok' else '❌'} {source_name}")

            v2_id = mk(parent_id, "1_Photovoltaïque_V2")
            if not v2_id: return
            time.sleep(1)
            cat01=mk(v2_id,"01_Commercial"); cat02=mk(v2_id,"02_Chantiers")
            cat03=mk(v2_id,"03_Administratif_Reglementaire"); cat04=mk(v2_id,"04_Documentation_Technique")
            cat05=mk(v2_id,"05_Fournisseurs_Partenaires"); cat06=mk(v2_id,"06_Outils_et_Logiciels")
            cat07=mk(v2_id,"07_RH_et_Stock"); time.sleep(1)
            if cat01: cp("1_1 Chiffrage Particulier",cat01,"Chiffrage_Particuliers"); cp("1_Chiffrage Pro",cat01,"Chiffrage_Pro")
            if cat02:
                cp("Pilotage",cat02); cp("1_SUIVI CHANTIER PV modifié.xlsm",cat02)
                cp("Photo vidéo chantier en cours",cat02,"Photos_et_Videos"); cp("Photos drone",cat02,"Photos_Drone")
            if cat03:
                cp("2_CONSUEL",cat03,"CONSUEL"); cp("3_ENEDIS",cat03,"ENEDIS")
                cp("4_Demandes DP Cerfa et Raccordement",cat03,"Demandes_DP"); cp("Procédure d'aide EDF OA.docx",cat03)
            if cat04:
                cp("5_Document technique",cat04,"Docs_Techniques"); cp("Normes",cat04); cp("Import ELEC",cat04)
                cp("6_Audits et rapports",cat04,"Audits")
                for f in ["DOE_Couffrant_Solar_Complet_Modele.docx","DOE_Couffrant_Solar_Modele_Reutilisable.docx",
                           "DOE_Photovoltaique_Couffrant_Solar_Complet.docx","PV fin de chantier.docx","RAPPORT AUDIT PV.docx"]:
                    cp(f, cat04)
            if cat05:
                for f in ["Adiwatt","MADENR","Urban Solar","Powr Connect","formulaire compensation solaredge.pdf",
                           "Demande garantie Onduleur 1 – Copie.xlsx","Demande garantie Onduleur.xlsx"]: cp(f,cat05)
            if cat06:
                for f in ["Formation archelios calc","sauvegarde Archelios","Logiciels","unnamed.png"]: cp(f,cat06)
            if cat07:
                for f in ["Certificats et Formations Professionnels","8_Stock 2026.ods","Suivi panneau publicitaire.xlsx"]: cp(f,cat07)
            print("[Reorganize] Terminé.")
        except Exception as e: print(f"[Reorganize] Erreur : {e}")

    threading.Thread(target=run_reorganize, daemon=True).start()
    return {"status": "started", "message": "Réorganisation lancée. Vérifiez SharePoint dans 5-10 minutes.", "note": "Les originaux restent intacts."}
