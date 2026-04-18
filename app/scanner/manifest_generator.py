"""
Generateur de manifests de vectorisation.

Pour chaque modele Odoo P1+P2 du plan (voir Section 3.1), genere
automatiquement un manifest JSON qui decrit :
- vectorize_fields : champs texte semantiques a embedder
- graph_edges : relations many2one a materialiser en aretes
- metadata_fields : dates/montants/etats stockes en JSONB sur le noeud
- handle_mail_thread/attachments/trackings : flags pour transversaux

Le manifest est stocke dans connector_schemas et editable via panel admin.

Principe (Q10=A validee) : generation auto sans validation prealable, mais
editable apres coup. Classification mecanique par type de champ.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("raya.scanner.manifest_generator")


# Liste des 31 modeles P1+P2 du plan (voir Section 3.1), avec leur priorite
# Chaque modele a un "role metier" qui guide certains choix d arete
MODELS_PRIORITY = {
    # P1 - Coeur metier (16 modeles)
    "res.partner": 1,
    "crm.lead": 1,
    "sale.order": 1,
    "sale.order.line": 1,
    "sale.order.template": 1,
    "sale.order.template.line": 1,
    "calendar.event": 1,
    "product.template": 1,
    "of.product.pack.lines": 1,
    "product.pack.line": 1,
    "mail.message": 1,
    "mail.tracking.value": 1,
    "of.planning.tour": 1,
    "of.planning.tour.line": 1,
    "of.survey.answers": 1,
    "of.survey.user_input.line": 1,
    # P2 - Support metier (15 modeles)
    "account.move": 2,
    "account.move.line": 2,
    "account.payment": 2,
    "of.sale.payment.schedule": 2,
    "of.account.move.payment.schedule": 2,
    "of.invoice.product.pack.lines": 2,
    "stock.picking": 2,
    "of.image": 2,
    "of.custom.document": 2,
    "of.custom.document.field": 2,
    "of.service.request": 2,
    "of.planning.intervention.template": 2,
    "of.planning.intervention.section": 2,
    "of.planning.task": 2,
    "hr.employee": 2,
    "mail.activity": 2,
}


# Noms de champs a ignorer systematiquement (bruit, techniques, transversaux deja geres)
IGNORED_FIELD_NAMES = {
    # IDs et timestamps techniques
    "id", "display_name", "__last_update", "access_token",
    # Champs gere par le systeme transversal (voir Section 3.2)
    "message_ids", "message_follower_ids", "message_partner_ids",
    "message_attachment_count", "message_has_error", "message_has_error_counter",
    "message_has_sms_error", "message_is_follower", "message_needaction",
    "message_needaction_counter", "message_main_attachment_id",
    "message_unread", "message_unread_counter", "has_message",
    # Activites (geres via mail.activity separement)
    "activity_ids", "activity_state", "activity_user_id", "activity_type_id",
    "activity_type_icon", "activity_date_deadline", "activity_summary",
    "activity_exception_decoration", "activity_exception_icon",
    "activity_calendar_event_id",
    # Champs internes Odoo (theme, website, etc.)
    "website_message_ids", "website_id", "image_1024", "image_128",
    "image_1920", "image_256", "image_512", "avatar_1024", "avatar_128",
    "avatar_1920", "avatar_256", "avatar_512",
    # Champs de sync / datastore OpenFire
    "of_datastore_is_connected", "of_datastore_res_id",
    "is_of_ds_search", "can_image_1024_be_zoomed", "can_image_variant_1024_be_zoomed",
}

# Noms de champs a VECTORISER quand ils sont de type char/text/html
# (on les cherche dans les vraies donnees, pas juste les noms de champs)
VECTORIZE_FIELD_NAMES = {
    # Texte semantique fort (a vectoriser par defaut)
    "name", "description", "description_sale", "description_purchase",
    "description_picking", "description_pickingin", "description_pickingout",
    "note", "comment", "subject", "body", "ref", "client_order_ref",
    "origin", "email_from", "partner_name", "partner_email", "contact_name",
    "street", "street2", "city", "state", "country", "zip",
    "phone", "mobile", "fax", "email", "website",
    "vat", "siret", "company_registry",
    # Produits et references techniques
    "default_code", "barcode", "norme", "brand_name", "marque",
    # Caracteristiques
    "function", "title", "job_title", "salutation",
}


# Mapping automatique many2one -> type d arete du graphe semantique
# Base sur les types d aretes validees dans app/semantic_graph.py
FIELD_TO_EDGE_TYPE = {
    # Liens vers des personnes / utilisateurs
    "partner_id": "LINKS_PARTNER",
    "commercial_partner_id": "LINKS_COMMERCIAL_PARTNER",
    "user_id": "ASSIGNED_TO",
    "invoice_user_id": "ASSIGNED_TO",
    "salesperson_id": "ASSIGNED_TO",
    "assigned_user_id": "ASSIGNED_TO",
    "create_uid": "CREATED_BY",
    "write_uid": "LAST_MODIFIED_BY",
    "author_id": "AUTHORED_BY",
    "employee_id": "PERFORMED_BY",
    "of_canvasser_id": "CANVASSED_BY",
    # Liens vers des deals / devis / factures
    "order_id": "BELONGS_TO_ORDER",
    "sale_order_id": "BELONGS_TO_ORDER",
    "move_id": "BELONGS_TO_INVOICE",
    "invoice_id": "BELONGS_TO_INVOICE",
    "payment_id": "LINKS_PAYMENT",
    "sale_order_template_id": "BASED_ON",
    # Liens vers des produits
    "product_id": "HAS_PRODUCT",
    "product_tmpl_id": "LINKS_TEMPLATE",
    "parent_product_id": "IS_COMPONENT_OF",
    "categ_id": "IN_CATEGORY",
    "brand_id": "OF_BRAND",
    # Liens vers des leads
    "lead_id": "LINKS_LEAD",
    "opportunity_id": "LINKS_OPPORTUNITY",
    # Liens vers des events / interventions
    "event_id": "LINKS_EVENT",
    "intervention_id": "LINKS_INTERVENTION",
    "calendar_event_id": "LINKS_EVENT",
    # Liens vers des tournees / planning
    "tour_id": "PART_OF_TOUR",
    "next_tour_line_id": "NEXT_STOP",
    "previous_tour_line_id": "PREVIOUS_STOP",
    # Liens geo et organisationnels
    "company_id": "IN_COMPANY",
    "country_id": "IN_COUNTRY",
    "state_id": "IN_STATE",
    "city_id": "IN_CITY",
    "zip_id": "IN_ZIP",
    "department_id": "IN_DEPARTMENT",
    "parent_id": "CHILD_OF",
    # Taxes et conditions
    "currency_id": "IN_CURRENCY",
    "payment_term_id": "HAS_PAYMENT_TERM",
    # Relations mail et documents
    "mail_message_id": "LINKS_MESSAGE",
    "attachment_id": "LINKS_DOCUMENT",
    # Questions/sondages
    "question_id": "ANSWERS_QUESTION",
    "survey_id": "IN_SURVEY",
    "user_input": "PART_OF_INPUT",
}


def _edge_type_for_field(field_name: str) -> str:
    """Deduit le type d arete a partir du nom du champ many2one.
    Fallback : 'LINKS_TO_<NomChamp>' capitalise si nom inconnu."""
    if field_name in FIELD_TO_EDGE_TYPE:
        return FIELD_TO_EDGE_TYPE[field_name]
    # Fallback : transforme 'customer_id' -> 'LINKS_CUSTOMER'
    base = field_name.replace("_id", "").replace("_ids", "").upper()
    return f"LINKS_{base}" if base else "LINKS_TO"


def generate_manifest_for_model(model_name: str, fields: list) -> dict:
    """Construit un manifest JSON pour UN modele a partir de ses champs Odoo.

    Args:
        model_name: ex 'sale.order'
        fields: liste de dicts avec name, type (ttype Odoo), relation, label,
                stored. Typiquement issu de ir.model.fields.search_read.

    Retourne le dict manifest pret a etre insere dans connector_schemas.manifest.

    Classification automatique (regle du 'dans le doute, on vectorise') :
    - char/text/html de nom semantique OU label semantique -> vectorize_fields
    - char/text/html si autre (ex. technique/ID) -> metadata_fields
    - many2one -> graph_edges avec edge_type deduit
    - one2many/many2many -> graph_edges (aretes multiples)
    - date/datetime/int/float/monetary/selection/boolean -> metadata_fields
    - binary, json, reference -> ignores par defaut (cas speciaux Phase 6/7)
    """
    vectorize, edges, metadata, ignored = [], [], [], []
    for f in fields:
        name = f.get("name", "")
        ftype = f.get("ttype") or f.get("type") or ""
        relation = f.get("relation") or None
        label = (f.get("label") or f.get("field_description") or "").lower()
        stored = f.get("stored", f.get("store", True))

        # Champ explicitement ignore ?
        if name in IGNORED_FIELD_NAMES or name.startswith("_"):
            ignored.append(name)
            continue

        # Champs textuels : vectoriser si semantique, sinon metadata
        if ftype in ("char", "text", "html"):
            is_semantic = (
                name in VECTORIZE_FIELD_NAMES
                or any(kw in name for kw in ["name", "desc", "note", "comment",
                                              "subject", "body", "ref", "norme",
                                              "caption", "message", "address"])
                or any(kw in label for kw in ["description", "note", "comment",
                                                "nom", "reference"])
            )
            if is_semantic:
                vectorize.append(name)
            else:
                metadata.append(name)
            continue

        # Many2one : arete
        if ftype == "many2one":
            edges.append({
                "field": name,
                "type": _edge_type_for_field(name),
                "target_model": relation,
            })
            continue

        # One2many ou many2many : arete multiple (attention, peut etre gros volume)
        if ftype in ("one2many", "many2many"):
            # On garde seulement si stored (sinon c est un calcul temporel)
            if stored:
                edges.append({
                    "field": name,
                    "type": _edge_type_for_field(name),
                    "target_model": relation,
                    "multiple": True,
                })
            else:
                ignored.append(name)
            continue

        # Types primitifs : metadata
        if ftype in ("integer", "float", "monetary", "boolean", "selection",
                     "date", "datetime", "json"):
            metadata.append(name)
            continue

        # Types binaires / reference : ignore par defaut
        if ftype in ("binary", "reference", "many2one_reference"):
            ignored.append(name)
            continue

        # Inconnu : on ignore avec log
        logger.warning("[ManifestGen] Type inconnu pour %s.%s: %s",
                       model_name, name, ftype)
        ignored.append(name)

    return {
        "model": model_name,
        "priority": MODELS_PRIORITY.get(model_name, 3),
        "vectorize_fields": sorted(set(vectorize)),
        "graph_edges": edges,
        "metadata_fields": sorted(set(metadata)),
        "ignored_fields": sorted(set(ignored)),
        "handle_mail_thread": True,   # Q2=A validee, tout vectorise
        "handle_attachments": True,
        "handle_trackings": True,
        "handle_followers": True,
    }


def save_manifest_to_db(
    tenant_id: str, source: str, model_name: str,
    manifest: dict, records_count_odoo: Optional[int] = None,
) -> int:
    """Upsert un manifest dans connector_schemas (INSERT ON CONFLICT).

    Si le manifest existe deja pour (tenant, source, model), il est remplace.
    Retourne l id de la ligne en DB."""
    from app.database import get_pg_conn

    priority = manifest.get("priority", 3)
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO connector_schemas
               (tenant_id, source, model_name, priority, enabled, manifest,
                records_count_odoo, last_scanned_at, updated_at)
               VALUES (%s, %s, %s, %s, TRUE, %s, %s, NULL, NOW())
               ON CONFLICT (tenant_id, source, model_name)
               DO UPDATE SET priority=EXCLUDED.priority,
                             manifest=EXCLUDED.manifest,
                             records_count_odoo=COALESCE(
                                 EXCLUDED.records_count_odoo,
                                 connector_schemas.records_count_odoo),
                             updated_at=NOW()
               RETURNING id""",
            (tenant_id, source, model_name, priority,
             json.dumps(manifest), records_count_odoo),
        )
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else None


def generate_all_manifests_from_odoo(
    tenant_id: str, source: str = "odoo",
) -> dict:
    """Fetch les champs de chaque modele P1+P2 via Odoo puis genere et sauve
    le manifest correspondant. Appele par l endpoint admin
    /admin/scanner/manifests/generate.

    Retourne un resume : {generated: N, errors: [...], models: [...]}."""
    from app.connectors.odoo_connector import odoo_call

    generated, errors = [], []
    for model_name, priority in MODELS_PRIORITY.items():
        try:
            # Fetch les champs du modele
            fields = odoo_call(
                model="ir.model.fields", method="search_read",
                kwargs={
                    "domain": [["model", "=", model_name]],
                    "fields": ["name", "field_description", "ttype",
                               "relation", "store"],
                    "limit": 500,
                },
            ) or []
            if not fields:
                errors.append(f"{model_name}: 0 champs (modele absent ?)")
                continue

            # Compte le nombre de records (pour le dashboard d integrite)
            try:
                count = odoo_call(model=model_name, method="search_count",
                                  args=[[]]) or 0
            except Exception:
                count = None

            # Normalise la cle des champs (ttype et field_description)
            normalized = [{
                "name": f.get("name"),
                "ttype": f.get("ttype"),
                "type": f.get("ttype"),
                "relation": f.get("relation"),
                "label": f.get("field_description"),
                "stored": f.get("store", True),
            } for f in fields]

            manifest = generate_manifest_for_model(model_name, normalized)
            db_id = save_manifest_to_db(
                tenant_id, source, model_name, manifest,
                records_count_odoo=count,
            )
            generated.append({
                "model": model_name,
                "priority": priority,
                "db_id": db_id,
                "records_count": count,
                "vectorize_count": len(manifest["vectorize_fields"]),
                "edges_count": len(manifest["graph_edges"]),
                "metadata_count": len(manifest["metadata_fields"]),
                "ignored_count": len(manifest["ignored_fields"]),
            })
        except Exception as e:
            logger.exception("[ManifestGen] Echec sur %s", model_name)
            errors.append(f"{model_name}: {str(e)[:200]}")

    return {
        "tenant_id": tenant_id,
        "source": source,
        "generated_count": len(generated),
        "errors_count": len(errors),
        "generated": generated,
        "errors": errors,
    }


def list_manifests(tenant_id: str, source: str = "odoo") -> list:
    """Liste les manifests existants pour un tenant+source, tries par priorite
    puis par model_name."""
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, model_name, priority, enabled, manifest,
                      records_count_odoo, records_count_raya, integrity_pct,
                      last_scanned_at, updated_at
               FROM connector_schemas
               WHERE tenant_id=%s AND source=%s
               ORDER BY priority ASC, model_name ASC""",
            (tenant_id, source),
        )
        rows = cur.fetchall()
        return [{
            "id": r[0],
            "model_name": r[1],
            "priority": r[2],
            "enabled": r[3],
            "manifest": r[4],
            "records_count_odoo": r[5],
            "records_count_raya": r[6],
            "integrity_pct": r[7],
            "last_scanned_at": r[8].isoformat() if r[8] else None,
            "updated_at": r[9].isoformat() if r[9] else None,
        } for r in rows]


def get_manifest(tenant_id: str, source: str, model_name: str) -> Optional[dict]:
    """Recupere un manifest specifique pour edition."""
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, model_name, priority, enabled, manifest,
                      records_count_odoo, records_count_raya, integrity_pct,
                      last_scanned_at, updated_at
               FROM connector_schemas
               WHERE tenant_id=%s AND source=%s AND model_name=%s""",
            (tenant_id, source, model_name),
        )
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "model_name": r[1], "priority": r[2],
            "enabled": r[3], "manifest": r[4],
            "records_count_odoo": r[5], "records_count_raya": r[6],
            "integrity_pct": r[7],
            "last_scanned_at": r[8].isoformat() if r[8] else None,
            "updated_at": r[9].isoformat() if r[9] else None,
        }


def update_manifest(
    tenant_id: str, source: str, model_name: str,
    enabled: Optional[bool] = None,
    manifest_patch: Optional[dict] = None,
) -> bool:
    """Met a jour un manifest existant. manifest_patch est fusionne avec le
    manifest existant (merge peu profond sur les champs vectorize_fields,
    graph_edges, etc.). enabled peut etre change separement."""
    existing = get_manifest(tenant_id, source, model_name)
    if not existing:
        return False

    new_manifest = existing["manifest"] or {}
    if manifest_patch:
        for key, val in manifest_patch.items():
            new_manifest[key] = val

    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        if enabled is not None:
            cur.execute(
                """UPDATE connector_schemas
                   SET manifest=%s, enabled=%s, updated_at=NOW()
                   WHERE tenant_id=%s AND source=%s AND model_name=%s""",
                (json.dumps(new_manifest), enabled, tenant_id, source, model_name),
            )
        else:
            cur.execute(
                """UPDATE connector_schemas
                   SET manifest=%s, updated_at=NOW()
                   WHERE tenant_id=%s AND source=%s AND model_name=%s""",
                (json.dumps(new_manifest), tenant_id, source, model_name),
            )
        conn.commit()
    return True
