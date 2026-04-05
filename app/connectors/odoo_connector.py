import requests
import json
import urllib3
from app.config import ODOO_URL, ODOO_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def odoo_call(model: str, method: str, args: list = [], kwargs: dict = {}) -> any:

    response = requests.post(
        f"{ODOO_URL}/web/dataset/call_kw/{model}/{method}",
        headers={
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": {
                    **kwargs,
                    "context": {},
                },
            },
        },
        auth=(ODOO_API_KEY, ""),
        timeout=30,
        verify=False,
    )

    if response.status_code != 200:
        raise Exception(f"Odoo HTTP {response.status_code}: {response.text[:500]}")

    result = response.json()

    if "error" in result:
        raise Exception(f"Odoo error: {json.dumps(result['error'])[:500]}")

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