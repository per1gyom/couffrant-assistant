"""
Handler Twilio/WhatsApp.
Extrait de webhook.py -- SPLIT-R3.
"""
import json
from app.database import get_pg_conn
from app.logging_config import get_logger
logger=get_logger("raya.webhook.whatsapp")


