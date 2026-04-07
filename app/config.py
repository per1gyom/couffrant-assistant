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

# offline_access est géré automatiquement par MSAL — ne pas l'inclure
GRAPH_SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
    "Files.ReadWrite.All",
    "Contacts.Read",
    "Chat.ReadWrite",
    "TeamMember.Read.All",
]

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ASSISTANT_DB_PATH = os.getenv("ASSISTANT_DB_PATH", "assistant.db")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL_FAST = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5-20251001")
ANTHROPIC_MODEL_SMART = os.getenv("ANTHROPIC_MODEL_SMART", "claude-sonnet-4-6-20250514")

ODOO_URL = os.getenv("ODOO_URL", "").strip()
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "").strip()
ODOO_DB = os.getenv("ODOO_DB", "").strip()
ODOO_LOGIN = os.getenv("ODOO_LOGIN", "").strip()
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "").strip()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
