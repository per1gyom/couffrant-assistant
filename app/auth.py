from msal import ConfidentialClientApplication
from app.config import CLIENT_ID, CLIENT_SECRET, AUTHORITY, GRAPH_SCOPES

def build_msal_app():
    return ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY,
    )

def refresh_microsoft_token(refresh_token: str) -> dict | None:
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=GRAPH_SCOPES,
    )
    if "access_token" in result:
        return result
    return None