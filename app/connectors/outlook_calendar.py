"""
Helpers Graph API et formatage email Outlook.
Extrait de outlook_actions.py -- SPLIT-F5.
"""
import requests
GRAPH_BASE_URL="https://graph.microsoft.com/v1.0"
def _headers(token): return {"Authorization":f"Bearer {token}","Content-Type":"application/json"}
def _graph_get(token,path,params=None):
    r=requests.get(f"{GRAPH_BASE_URL}{path}",headers=_headers(token),params=params,timeout=30)
    r.raise_for_status(); return r.json()


def _graph_post(token, path, json_body=None):
    r = requests.post(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body or {}, timeout=30)
    r.raise_for_status(); return r.json() if r.text.strip() else {}



def _graph_patch(token, path, json_body):
    r = requests.patch(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body, timeout=30)
    r.raise_for_status(); return r.json() if r.text.strip() else {}



def _graph_delete(token, path):
    r = requests.delete(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), timeout=30)
    return r.status_code == 204




def _build_email_html(body: str, username: str = "guillaume", from_address: str = None) -> str:
    """Corps HTML du mail avec signature.

    EMAIL-SIGNATURE : déléguée à get_email_signature(username, from_address).
    Si from_address est fourni, la logique de matching par boîte mail s'applique
    (default_for_emails > apply_to_emails > is_default global > fallback statique).
    """
    from app.email_signature import get_email_signature
    signature = get_email_signature(username, from_address=from_address)
    # Convertir les sauts de ligne en <br> — white-space:pre-line est ignore par Gmail/Outlook
    body_html = body.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>\n')
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;">{body_html}</div>{signature}'


# Re-exports Drive
from app.connectors.drive_connector import (
    _find_sharepoint_site_and_drive,
    list_drive as list_aria_drive,
    read_drive_file as read_aria_drive_file,
    search_drive as search_aria_drive,
    create_folder as create_drive_folder,
    move_item as move_drive_item,
    copy_item as copy_drive_item,
)



