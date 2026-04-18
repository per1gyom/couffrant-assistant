"""
Adapter Odoo — couche d abstraction au dessus de la connexion XML-RPC.

Expose des fonctions de haut niveau :
- fetch_records_batch : pagination par batches de 100 records
- fetch_mail_messages : commentaires et notifications lies a un record
- fetch_mail_trackings : historique de modifications d un record
- fetch_attachments : pieces jointes d un record (avec contenu binaire)
- fetch_record_with_transversals : tout ce qui tourne autour d un record

Isolant l adapter permet de le reutiliser pour d autres sources plus tard
(Drive, Teams) en recreant juste les memes primitives.
"""

import logging
from typing import Optional

logger = logging.getLogger("raya.scanner.adapter_odoo")


def fetch_records_batch(
    model_name: str,
    fields: list,
    offset: int = 0,
    limit: int = 100,
    domain: Optional[list] = None,
    order: str = "id asc",
) -> list:
    """Fetch un batch de records d un modele Odoo avec pagination.

    Utilise le connecteur Odoo deja en place (odoo_call) pour faire
    un search_read pagine.

    Args:
        model_name: nom du modele Odoo ('sale.order', 'res.partner'...)
        fields: liste des champs a recuperer
        offset: decalage pour pagination
        limit: taille du batch (100 par defaut)
        domain: filtre Odoo ([['state', '=', 'sale']]). Defaut: tous.
        order: tri ('id asc' par defaut pour pagination stable)
    """
    from app.connectors.odoo_connector import odoo_call
    try:
        records = odoo_call(
            model=model_name, method="search_read",
            kwargs={
                "domain": domain or [],
                "fields": fields,
                "offset": offset,
                "limit": limit,
                "order": order,
            },
        )
        return records or []
    except Exception as e:
        logger.error("[Adapter] fetch_records_batch %s offset=%d: %s",
                     model_name, offset, str(e)[:200])
        raise


def count_records(model_name: str, domain: Optional[list] = None) -> int:
    """Compte le nombre total de records d un modele (pour pagination)."""
    from app.connectors.odoo_connector import odoo_call
    try:
        return odoo_call(
            model=model_name, method="search_count",
            args=[domain or []],
        ) or 0
    except Exception as e:
        logger.error("[Adapter] count_records %s: %s",
                     model_name, str(e)[:200])
        return 0


def fetch_mail_messages(
    model_name: str,
    record_ids: list,
    include_system: bool = True,
) -> list:
    """Fetch les mail.message lies a une liste de records.

    Relation polymorphique via res_model + res_id. Permet de recuperer en
    un seul call tous les commentaires pour un batch de records.

    Args:
        model_name: modele parent (ex: 'sale.order')
        record_ids: liste d'IDs de records du modele
        include_system: inclure les notifications auto Odoo (Q2=A pour Guillaume)
    """
    if not record_ids:
        return []
    from app.connectors.odoo_connector import odoo_call
    # Q2=A : on vectorise TOUS les messages (comment + notification + email)
    # car Guillaume veut la vision Jarvis totale pour la proactivite
    domain = [
        ("model", "=", model_name),
        ("res_id", "in", list(record_ids)),
    ]
    if not include_system:
        domain.append(("message_type", "in", ["comment", "email"]))
    try:
        messages = odoo_call(
            model="mail.message", method="search_read",
            kwargs={
                "domain": domain,
                "fields": ["id", "res_id", "body", "subject", "author_id",
                           "email_from", "date", "message_type",
                           "attachment_ids", "tracking_value_ids"],
                "order": "date asc",
            },
        )
        return messages or []
    except Exception as e:
        logger.error("[Adapter] fetch_mail_messages %s: %s",
                     model_name, str(e)[:200])
        return []


def fetch_mail_trackings(message_ids: list) -> list:
    """Fetch l historique des modifications de champs pour des messages.

    Permet a Raya de dire 'ce devis est passe de draft a sale le 18/03 par
    Guillaume'.
    """
    if not message_ids:
        return []
    from app.connectors.odoo_connector import odoo_call
    try:
        trackings = odoo_call(
            model="mail.tracking.value", method="search_read",
            kwargs={
                "domain": [("mail_message_id", "in", list(message_ids))],
                "fields": ["id", "mail_message_id", "field_desc", "field_type",
                           "old_value_char", "new_value_char",
                           "old_value_datetime", "new_value_datetime",
                           "old_value_float", "new_value_float",
                           "old_value_integer", "new_value_integer"],
            },
        )
        return trackings or []
    except Exception as e:
        logger.error("[Adapter] fetch_mail_trackings: %s", str(e)[:200])
        return []


def fetch_attachments(
    model_name: str,
    record_ids: list,
    include_binary: bool = False,
) -> list:
    """Fetch les pieces jointes (ir.attachment) liees a des records.

    Args:
        include_binary: si True, recupere aussi le champ datas (base64 du
            contenu). False par defaut pour eviter de charger des MB inutiles
            dans le fetch initial. Le contenu est fetch separement par record
            au moment de l extraction (Phase 6).
    """
    if not record_ids:
        return []
    from app.connectors.odoo_connector import odoo_call
    fields = ["id", "name", "mimetype", "file_size", "res_model", "res_id",
              "type", "create_uid", "create_date"]
    if include_binary:
        fields.append("datas")
    try:
        attachments = odoo_call(
            model="ir.attachment", method="search_read",
            kwargs={
                "domain": [
                    ("res_model", "=", model_name),
                    ("res_id", "in", list(record_ids)),
                ],
                "fields": fields,
            },
        )
        return attachments or []
    except Exception as e:
        logger.error("[Adapter] fetch_attachments %s: %s",
                     model_name, str(e)[:200])
        return []


def fetch_followers(model_name: str, record_ids: list) -> list:
    """Fetch les followers (abonnes) lies a des records."""
    if not record_ids:
        return []
    from app.connectors.odoo_connector import odoo_call
    try:
        followers = odoo_call(
            model="mail.followers", method="search_read",
            kwargs={
                "domain": [
                    ("res_model", "=", model_name),
                    ("res_id", "in", list(record_ids)),
                ],
                "fields": ["id", "res_id", "partner_id"],
            },
        )
        return followers or []
    except Exception as e:
        logger.error("[Adapter] fetch_followers %s: %s",
                     model_name, str(e)[:200])
        return []


def fetch_record_with_transversals(
    model_name: str,
    record_id: int,
    fields: list,
) -> dict:
    """Recupere UN record complet + tous ses transversaux en 1 seul appel.

    Utilise notamment par les webhooks qui veulent mettre a jour UN record
    specifique sans refaire un batch complet.

    Retourne :
        {
            "record": {...},
            "messages": [...],
            "trackings": [...],
            "attachments": [...],
            "followers": [...],
        }
    """
    records = fetch_records_batch(
        model_name, fields,
        domain=[("id", "=", record_id)], limit=1,
    )
    if not records:
        return {"record": None}
    messages = fetch_mail_messages(model_name, [record_id])
    msg_ids = [m["id"] for m in messages]
    trackings = fetch_mail_trackings(msg_ids)
    attachments = fetch_attachments(model_name, [record_id])
    followers = fetch_followers(model_name, [record_id])
    return {
        "record": records[0],
        "messages": messages,
        "trackings": trackings,
        "attachments": attachments,
        "followers": followers,
    }
