"""
Connecteur Outlook pour Raya.
Gere : mails, calendrier, taches, contacts.

EMAIL-SIGNATURE : _build_email_html() utilise get_email_signature()
  depuis app/email_signature.py.

Le Drive SharePoint est gere dans drive_connector.py.
"""
import re
import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
ARCHIVE_FOLDER_ID = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _graph_get(token, path, params=None):
    r = requests.get(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), params=params, timeout=30)
    r.raise_for_status(); return r.json()
from app.connectors.outlook_actions import perform_outlook_action  # noqa
