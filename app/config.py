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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")