from msal import ConfidentialClientApplication
from app.config import CLIENT_ID, CLIENT_SECRET, AUTHORITY

def build_msal_app():
    return ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY,
    )