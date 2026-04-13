"""
Signature email HTML pour Raya. (EMAIL-SIGNATURE)

Utilisé par outlook_connector.py lors de l'envoi de mails.
TODO : rendre dynamique par utilisateur via la DB (champ users.signature).
"""
import os


def get_email_signature(username: str) -> str:
    """
    Retourne la signature HTML pour un utilisateur.

    Pour l'instant, signature statique de Guillaume.
    Le logo est servi depuis app/static/ via APP_BASE_URL.

    Args:
        username : identifiant de l'utilisateur (réservé pour la v2 dynamique)

    Returns:
        str : bloc HTML de signature à concaténer au corps du mail
    """
    base_url = os.getenv("APP_BASE_URL", "https://app.raya-ia.fr").rstrip("/")
    banner_url = f"{base_url}/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png"

    return f"""
<br><br>
<table cellpadding="0" cellspacing="0" style="font-family: Helvetica, Arial, sans-serif; font-size: 14px; color: #333;">
  <tr><td style="padding-bottom: 4px;">Solairement,</td></tr>
  <tr><td style="font-weight: bold; font-size: 15px; padding-bottom: 4px;">Guillaume Perrin</td></tr>
  <tr><td style="padding-bottom: 4px;">&#128222; 06 49 43 09 17</td></tr>
  <tr><td style="padding-bottom: 12px;"><a href="https://couffrant-solar.fr" style="color: #1D6FD9; text-decoration: none;">&#127758; couffrant-solar.fr</a></td></tr>
  <tr><td><img src="{banner_url}" alt="Couffrant Solar" style="width: 500px; max-width: 100%; height: auto; border: 0;"></td></tr>
</table>
"""
