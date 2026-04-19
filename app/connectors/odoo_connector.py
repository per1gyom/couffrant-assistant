import requests
import json
import urllib3
from app.config import ODOO_URL, ODOO_API_KEY, ODOO_DB, ODOO_LOGIN, ODOO_PASSWORD

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def odoo_authenticate() -> str:
    response = requests.post(
        f"{ODOO_URL}/web/session/authenticate",
        headers={"Content-Type": "application/json"},
        json={
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "db": ODOO_DB,
                "login": ODOO_LOGIN,
                "password": ODOO_PASSWORD,
            },
        },
        verify=False,
        timeout=30,
    )
    result = response.json()
    if "error" in result:
        raise Exception(f"Auth Odoo failed: {result['error']}")
    session_id = response.cookies.get("session_id")
    if not session_id:
        raise Exception("Pas de session_id reçu")
    return session_id


def odoo_call(model: str, method: str, args: list = [], kwargs: dict = {}) -> any:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session_id = odoo_authenticate()

    response = requests.post(
        f"{ODOO_URL}/web/dataset/call_kw/{model}/{method}",
        headers={"Content-Type": "application/json"},
        cookies={"session_id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": {**kwargs, "context": {}},
            },
        },
        verify=False,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Odoo HTTP {response.status_code}: {response.text[:5000]}")

    result = response.json()
    if "error" in result:
        # Troncature augmentee a 5000 chars (18/04) pour avoir le nom du
        # champ Odoo coupable dans le traceback (avant c etait 500, insuffisant)
        raise Exception(f"Odoo error: {json.dumps(result['error'])[:5000]}")

    return result.get("result")


def get_partner_by_email(email: str) -> dict | None:
    results = odoo_call(
        model="res.partner",
        method="search_read",
        kwargs={
            "domain": [["email", "=", email]],
            "fields": ["id", "name", "email", "phone", "street", "city"],
            "limit": 1,
        }
    )
    return results[0] if results else None


def get_projects_by_partner(partner_id: int) -> list:
    return odoo_call(
        model="project.project",
        method="search_read",
        kwargs={
            "domain": [["partner_id", "=", partner_id]],
            "fields": ["id", "name", "date_start", "date", "stage_id", "user_id"],
        }
    )


def get_tasks_by_project(project_id: int) -> list:
    return odoo_call(
        model="project.task",
        method="search_read",
        kwargs={
            "domain": [["project_id", "=", project_id]],
            "fields": ["id", "name", "stage_id", "date_deadline", "user_ids", "description"],
        }
    )


def update_project_date(project_id: int, date_start: str, date_end: str) -> bool:
    return odoo_call(
        model="project.project",
        method="write",
        args=[[project_id], {
            "date_start": date_start,
            "date": date_end,
        }]
    )


def add_note_to_partner(partner_id: int, note: str) -> bool:
    return odoo_call(
        model="mail.message",
        method="create",
        args=[{
            "res_id": partner_id,
            "model": "res.partner",
            "body": note,
            "message_type": "comment",
        }]
    )


def perform_odoo_action(action: str, params: dict) -> dict:
    if action == "get_partner_by_email":
        result = get_partner_by_email(params["email"])
        return {"status": "ok", "action": action, "result": result}

    if action == "get_projects_by_partner":
        result = get_projects_by_partner(params["partner_id"])
        return {"status": "ok", "action": action, "result": result}

    if action == "get_tasks_by_project":
        result = get_tasks_by_project(params["project_id"])
        return {"status": "ok", "action": action, "result": result}

    if action == "update_project_date":
        result = update_project_date(
            params["project_id"],
            params["date_start"],
            params["date_end"]
        )
        return {"status": "ok", "action": action, "result": result}

    if action == "add_note_to_partner":
        result = add_note_to_partner(params["partner_id"], params["note"])
        return {"status": "ok", "action": action, "result": result}

    return {"status": "error", "action": action, "message": f"Action inconnue : {action}"}