import time
import requests

BASE_URL = "http://127.0.0.1:8000"

while True:
    try:
        r = requests.get(f"{BASE_URL}/ingest-mails-fast", timeout=30)
        print("Ingestion:", r.text)
    except Exception as e:
        print("Erreur:", e)

    time.sleep(300)