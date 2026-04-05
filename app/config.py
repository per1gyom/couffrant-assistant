import os
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID", "").strip()
CLIENT_ID = os.getenv("CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI", "").strip()

AUTHORITY = os.getenv("AUTHORITY", "").strip()
if not AUTHORITY and TENANT_ID:
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

GRAPH_SCOPES = os.getenv("GRAPH_SCOPES", "User.Read Mail.Read Calendars.Read").split()

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ASSISTANT_DB_PATH = os.getenv("ASSISTANT_DB_PATH", "assistant.db")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL_FAST = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5-20251001")
ANTHROPIC_MODEL_SMART = os.getenv("ANTHROPIC_MODEL_SMART", "claude-sonnet-4-6")
ODOO_URL = os.getenv("ODOO_URL", "").strip()
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "").strip()
ODOO_DB = os.getenv("ODOO_DB", "").strip()
ODOO_LOGIN = os.getenv("ODOO_LOGIN", "").strip()
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "").strip()