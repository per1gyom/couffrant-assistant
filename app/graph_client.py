import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

def graph_get(access_token: str, endpoint: str, params: dict | None = None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    response = requests.get(
        f"{GRAPH_BASE_URL}{endpoint}",
        headers=headers,
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()