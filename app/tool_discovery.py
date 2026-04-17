"""
Auto-découverte des outils connectés.

Explore un outil (Odoo, Drive, Teams...), extrait sa structure,
génère des descriptions naturelles via LLM, vectorise et stocke
dans tool_schemas pour que le RAG puisse les retrouver.

Résultat : Raya a une conscience naturelle des données disponibles
sans listes hardcodées dans le prompt.
"""
import json
from datetime import datetime, timezone
from app.database import get_pg_conn
from app.embedding import embed
from app.logging_config import get_logger

logger = get_logger("raya.discovery")


# ─── MODÈLES ODOO PERTINENTS ─────────────────────────────────────
# On ne vectorise pas les 500+ modèles techniques d'Odoo,
# seulement ceux qui ont du sens business pour un dirigeant.
ODOO_RELEVANT_MODELS = [
    "res.partner", "res.company", "res.users",
    "sale.order", "sale.order.line",
    "account.move", "account.move.line", "account.payment",
    "purchase.order", "purchase.order.line",
    "project.project", "project.task",
    "crm.lead", "crm.team",
    "product.product", "product.template",
    "stock.picking", "stock.move", "stock.warehouse",
    "hr.employee", "hr.department",
    "calendar.event",
    "mail.message",
]


def discover_odoo(tenant_id: str, connection_id: int = None) -> dict:
    """
    Explore Odoo et vectorise les schémas des modèles business.
    Retourne {"discovered": N, "errors": [...]}
    """
    from app.connectors.odoo_connector import odoo_call

    discovered = 0
    errors = []

    # 1. Lister les modèles accessibles
    try:
        all_models = odoo_call(
            model="ir.model", method="search_read",
            kwargs={
                "domain": [["model", "in", ODOO_RELEVANT_MODELS]],
                "fields": ["model", "name", "info"],
                "limit": 100,
            }
        )
    except Exception as e:
        return {"discovered": 0, "errors": [f"Connexion Odoo échouée : {str(e)[:200]}"]}

    if not all_models:
        return {"discovered": 0, "errors": ["Aucun modèle Odoo accessible."]}

    # 2. Pour chaque modèle : récupérer les champs et construire la description
    for model_info in all_models:
        model_name = model_info["model"]
        display = model_info.get("name", model_name)
        try:
            fields_raw = odoo_call(
                model=model_name, method="fields_get",
                kwargs={"attributes": ["string", "type", "relation", "required", "help"]}
            )

            # Filtrer les champs techniques internes d'Odoo
            skip_prefixes = ("__", "message_", "activity_", "website_", "access_")
            skip_types = ("binary",)
            useful_fields = {}
            relationships = []

            for fname, finfo in fields_raw.items():
                if any(fname.startswith(p) for p in skip_prefixes):
                    continue
                if finfo.get("type") in skip_types:
                    continue
                useful_fields[fname] = {
                    "label": finfo.get("string", fname),
                    "type": finfo.get("type", "?"),
                    "required": finfo.get("required", False),
                }
                # Capturer les relations (many2one, one2many, many2many)
                if finfo.get("relation"):
                    relationships.append({
                        "field": fname,
                        "target": finfo["relation"],
                        "type": finfo.get("type"),
                        "label": finfo.get("string", fname),
                    })

            # Construire une description naturelle (sans LLM — déterministe et rapide)
            key_fields = [f"{v['label']} ({fname})" for fname, v in useful_fields.items()
                         if v.get("required") or fname in ("name", "email", "phone",
                         "amount_total", "state", "date", "partner_id", "user_id")][:15]
            rel_targets = list(set(r["target"] for r in relationships if r["target"] in ODOO_RELEVANT_MODELS))

            description = (
                f"{display} ({model_name}) dans Odoo. "
                f"Champs principaux : {', '.join(key_fields[:10])}. "
            )
            if rel_targets:
                description += f"Lié à : {', '.join(rel_targets[:5])}. "

            # Ajouter le contexte sémantique selon le modèle
            context_hints = {
                "res.partner": "Contacts, clients, fournisseurs. Contient coordonnées, adresse, historique commercial.",
                "sale.order": "Devis et bons de commande. Contient lignes de produits, montants, état (brouillon/confirmé/annulé).",
                "account.move": "Factures et avoirs. Contient montant, état de paiement, échéance, lignes comptables.",
                "project.project": "Projets en cours. Contient dates, responsable, client associé, tâches.",
                "project.task": "Tâches de projet. Contient étape, deadline, assignation, description.",
                "crm.lead": "Opportunités commerciales (CRM). Contient prospect, montant estimé, étape du pipeline.",
                "product.product": "Produits et services. Contient prix, catégorie, stock.",
                "purchase.order": "Commandes fournisseur. Contient lignes d'achat, montants, état.",
                "account.payment": "Paiements enregistrés. Contient montant, moyen de paiement, date.",
                "stock.picking": "Bons de livraison et réceptions. Contient articles, quantités, état.",
                "hr.employee": "Employés. Contient poste, département, coordonnées.",
                "calendar.event": "Événements de calendrier Odoo. Contient date, participants, lieu.",
            }
            if model_name in context_hints:
                description += context_hints[model_name]

            # Vectoriser et stocker
            vec = embed(description)
            _upsert_schema(
                tenant_id=tenant_id,
                connection_id=connection_id,
                tool_type="odoo",
                schema_type="model",
                entity_key=model_name,
                display_name=display,
                description=description,
                fields_json=useful_fields,
                relationships_json=relationships,
                embedding=vec,
            )
            discovered += 1
            logger.info("[Discovery] Odoo %s → %d champs, %d relations", model_name, len(useful_fields), len(relationships))

        except Exception as e:
            errors.append(f"{model_name}: {str(e)[:100]}")
            logger.warning("[Discovery] Erreur %s : %s", model_name, e)

    logger.info("[Discovery] Odoo terminé : %d modèles découverts, %d erreurs", discovered, len(errors))
    return {"discovered": discovered, "errors": errors}


def _upsert_schema(tenant_id, connection_id, tool_type, schema_type,
                   entity_key, display_name, description, fields_json,
                   relationships_json, embedding):
    """Insert ou met à jour un schéma dans tool_schemas."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = f"[{','.join(str(v) for v in embedding)}]" if embedding else None
        c.execute("""
            INSERT INTO tool_schemas
                (tenant_id, connection_id, tool_type, schema_type, entity_key,
                 display_name, description, fields_json, relationships_json, embedding, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::vector, NOW())
            ON CONFLICT (tenant_id, tool_type, entity_key) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                fields_json = EXCLUDED.fields_json,
                relationships_json = EXCLUDED.relationships_json,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
        """, (
            tenant_id, connection_id, tool_type, schema_type, entity_key,
            display_name, description,
            json.dumps(fields_json, ensure_ascii=False),
            json.dumps(relationships_json, ensure_ascii=False),
            vec_str,
        ))
        conn.commit()
    except Exception as e:
        logger.error("[Discovery] Upsert échoué %s/%s: %s", tool_type, entity_key, e)
    finally:
        if conn: conn.close()


def retrieve_tool_knowledge(query: str, tenant_id: str, limit: int = 5) -> str:
    """
    Retrouve les schémas d'outils pertinents pour la question de l'utilisateur.
    Appelé par le RAG dans build_system_prompt.
    Retourne un texte naturel décrivant les outils/données pertinents.
    """
    vec = embed(query)
    if not vec:
        return ""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = f"[{','.join(str(v) for v in vec)}]"
        c.execute("""
            SELECT tool_type, entity_key, display_name, description, fields_json
            FROM tool_schemas
            WHERE tenant_id = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (tenant_id, vec_str, limit))
        rows = c.fetchall()
        if not rows:
            return ""
        parts = []
        for tool_type, entity_key, display_name, description, fields_json in rows:
            fields = fields_json or {}
            field_names = [f"{v.get('label', k)} ({k})" for k, v in list(fields.items())[:8]]
            part = f"[{tool_type}] {description}"
            if field_names:
                part += f"\n  Champs utilisables : {', '.join(field_names)}"
            parts.append(part)
        return "\n".join(parts)
    except Exception as e:
        logger.warning("[Discovery] Retrieval échoué : %s", e)
        return ""
    finally:
        if conn: conn.close()


def get_discovery_status(tenant_id: str) -> dict:
    """Retourne l'état de l'auto-découverte pour un tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tool_type, COUNT(*), MAX(updated_at)
            FROM tool_schemas WHERE tenant_id = %s
            GROUP BY tool_type
        """, (tenant_id,))
        return {row[0]: {"count": row[1], "last_update": str(row[2])} for row in c.fetchall()}
    except Exception:
        return {}
    finally:
        if conn: conn.close()
