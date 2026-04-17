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
# Liste prioritaire (gros ROI, toujours indexés en premier).
# Elle est complétée dynamiquement par _discover_relevant_odoo_models() qui
# détecte aussi les modules métier installés (planning, mrp, hr.leave...).
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

# Préfixes de modèles Odoo toujours exclus (techniques, jamais business)
_ODOO_EXCLUDED_PREFIXES = (
    "ir.", "base.", "res.config", "res.partner.bank", "res.groups",
    "bus.", "mail.template", "mail.channel", "mail.activity.type",
    "web.", "website.", "digest.", "auth_", "l10n_", "account.tax",
    "report.", "resource.", "decimal.precision", "analytic.",
)

# Modules métier importants (ajoutés s'ils sont installés côté Odoo).
# Le critère : "présent et a au moins un enregistrement".
_ODOO_EXTRA_CANDIDATES = [
    "planning.slot", "planning.planning", "planning.role",
    "hr.leave", "hr.leave.type", "hr.attendance",
    "mrp.production", "mrp.bom",
    "maintenance.request", "maintenance.equipment",
    "fleet.vehicle",
    "helpdesk.ticket",
    "sign.request", "documents.document",
    "pos.order",
]


def _discover_relevant_odoo_models() -> list[str]:
    """
    Liste les modèles Odoo business pertinents, dynamiquement.
    Combine :
      - ODOO_RELEVANT_MODELS (priorité)
      - _ODOO_EXTRA_CANDIDATES filtrés sur présence réelle (ir.model)
    Permet de capter planning.slot et autres modules métier sans hardcode.
    """
    from app.connectors.odoo_connector import odoo_call
    models = list(ODOO_RELEVANT_MODELS)
    try:
        # Vérifier la présence des candidats supplémentaires dans ir.model
        existing = odoo_call(
            model="ir.model", method="search_read",
            kwargs={
                "domain": [["model", "in", _ODOO_EXTRA_CANDIDATES]],
                "fields": ["model"],
                "limit": len(_ODOO_EXTRA_CANDIDATES),
            }
        )
        for m in (existing or []):
            if m["model"] not in models:
                models.append(m["model"])
    except Exception as e:
        logger.warning("[Discovery] Détection modèles extras échouée : %s", e)
    return models


def discover_odoo(tenant_id: str, connection_id: int = None) -> dict:
    """
    Explore Odoo et vectorise les schémas des modèles business.
    Retourne {"discovered": N, "errors": [...]}
    """
    from app.connectors.odoo_connector import odoo_call

    discovered = 0
    errors = []

    # Liste dynamique : ODOO_RELEVANT_MODELS + modules métier installés détectés
    models_to_explore = _discover_relevant_odoo_models()

    # 1. Lister les modèles accessibles
    try:
        all_models = odoo_call(
            model="ir.model", method="search_read",
            kwargs={
                "domain": [["model", "in", models_to_explore]],
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
            rel_targets = list(set(r["target"] for r in relationships if r["target"] in models_to_explore))

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


# ─── DRIVE : DÉCOUVERTE DES DOSSIERS ET FICHIERS RÉCENTS ────────

def discover_drive(tenant_id: str, username: str, connection_id: int = None) -> dict:
    """
    Explore les drives connectés d'un user (SharePoint + Google Drive) et vectorise :
      - les dossiers de niveau 1-2 (structure de l'arborescence)
      - les 30 fichiers les plus récents (pour que Raya les retrouve par contexte)

    Retourne {"discovered": N, "folders": F, "files": X, "errors": [...]}.
    """
    from app.drive_manager import get_user_drives

    discovered = 0
    folders_count = 0
    files_count = 0
    errors = []

    drives = get_user_drives(username)
    if not drives:
        return {"discovered": 0, "folders": 0, "files": 0,
                "errors": [f"Aucun drive connecté pour {username}"]}

    for drv in drives:
        provider = drv.provider
        drive_label = drv.label
        try:
            # 1. Lister la racine → dossiers de niveau 1
            root_items = drv.list("") or []
            folders_lvl1 = [it for it in root_items if it.item_type == "folder"]

            for folder in folders_lvl1[:30]:
                description = (
                    f"Dossier '{folder.name}' dans {drive_label} ({provider}). "
                    f"Accessible via l'action SEARCHDRIVE. "
                    f"URL directe : {folder.url or 'n/a'}."
                )
                try:
                    vec = embed(description)
                    _upsert_schema(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        tool_type="drive",
                        schema_type="folder",
                        entity_key=f"{provider}:folder:{folder.id}",
                        display_name=folder.name,
                        description=description,
                        fields_json={"path": folder.path, "url": folder.url,
                                     "modified": folder.modified, "provider": provider},
                        relationships_json=[],
                        embedding=vec,
                    )
                    discovered += 1
                    folders_count += 1
                except Exception as e:
                    errors.append(f"folder {folder.name}: {str(e)[:80]}")

            # 2. Fichiers récents via search(""): utilise l'ordre modifié DESC
            recent_files = drv.search("", max_results=30) or []
            recent_files = [it for it in recent_files if it.item_type == "file"][:30]

            for f in recent_files:
                description = (
                    f"Fichier '{f.name}' dans {drive_label} ({provider}), "
                    f"modifié le {f.modified or 'n/a'}. "
                    f"Accessible via SEARCHDRIVE ou par URL directe."
                )
                try:
                    vec = embed(description)
                    _upsert_schema(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        tool_type="drive",
                        schema_type="recent_file",
                        entity_key=f"{provider}:file:{f.id}",
                        display_name=f.name,
                        description=description,
                        fields_json={"path": f.path, "url": f.url,
                                     "modified": f.modified, "size": f.size,
                                     "provider": provider},
                        relationships_json=[],
                        embedding=vec,
                    )
                    discovered += 1
                    files_count += 1
                except Exception as e:
                    errors.append(f"file {f.name}: {str(e)[:80]}")

            logger.info("[Discovery] Drive %s (%s) → %d dossiers, %d fichiers indexés",
                        drive_label, provider, folders_count, files_count)

        except Exception as e:
            errors.append(f"{provider}: {str(e)[:200]}")
            logger.warning("[Discovery] Erreur drive %s : %s", provider, e)

    logger.info("[Discovery] Drive terminé : %d éléments (%d dossiers + %d fichiers), %d erreurs",
                discovered, folders_count, files_count, len(errors))
    return {"discovered": discovered, "folders": folders_count,
            "files": files_count, "errors": errors}


# ─── CALENDRIER : DÉCOUVERTE DES ÉVÉNEMENTS ET RÉCURRENTS ───────

def discover_calendar(tenant_id: str, username: str, connection_id: int = None) -> dict:
    """
    Indexe les événements des 30 prochains jours (tous calendriers confondus : MS + Google).
    Pour chaque événement : sujet, date, participants, lieu, récurrence.
    Utile pour que Raya sache 'tu as RDV avec X lundi' sans lire l'agenda complet à chaque requête.
    """
    from app.mailbox_manager import load_agenda_all

    discovered = 0
    errors = []
    try:
        events = load_agenda_all(username, days=30) or []
    except Exception as e:
        return {"discovered": 0, "errors": [f"load_agenda_all échoué : {str(e)[:200]}"]}

    for ev in events[:80]:  # cap raisonnable
        try:
            subject = ev.get("subject") or ev.get("summary") or "(sans sujet)"
            start = ev.get("start") or ev.get("start_time") or ""
            end = ev.get("end") or ev.get("end_time") or ""
            location = ev.get("location") or ""
            attendees = ev.get("attendees") or []
            # Normaliser les participants (peut être liste d'emails ou liste de dicts)
            attendee_emails = []
            for a in attendees:
                if isinstance(a, dict):
                    email = a.get("email") or a.get("emailAddress", {}).get("address", "")
                else:
                    email = str(a)
                if email:
                    attendee_emails.append(email)

            description = (
                f"Événement '{subject}' prévu le {start}"
                + (f" à {location}" if location else "")
                + (f", avec {', '.join(attendee_emails[:5])}" if attendee_emails else "")
                + f". Source : {ev.get('source', 'calendar')}."
            )
            vec = embed(description)
            _upsert_schema(
                tenant_id=tenant_id,
                connection_id=connection_id,
                tool_type="calendar",
                schema_type="event",
                entity_key=f"event:{ev.get('id', subject)[:100]}",
                display_name=subject,
                description=description,
                fields_json={"start": start, "end": end, "location": location,
                             "attendees": attendee_emails, "source": ev.get("source", "")},
                relationships_json=[{"type": "attendee", "target": em} for em in attendee_emails],
                embedding=vec,
            )
            discovered += 1
        except Exception as e:
            errors.append(f"event: {str(e)[:80]}")

    logger.info("[Discovery] Calendar terminé : %d événements indexés, %d erreurs", discovered, len(errors))
    return {"discovered": discovered, "errors": errors}


# ─── CONTACTS : DÉCOUVERTE PAR FRÉQUENCE D'ÉCHANGE ──────────────

def discover_contacts(tenant_id: str, username: str, connection_id: int = None) -> dict:
    """
    Indexe les contacts fréquents depuis mail_memory (proxy "qui contacte qui").
    Pour chaque contact : nombre d'échanges, dernier contact, premier sujet récent.
    Permet à Raya de prioriser les contacts récurrents dans ses réponses.
    """
    discovered = 0
    errors = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email, MAX(from_name) AS name,
                   COUNT(*) AS mail_count, MAX(received_at) AS last_seen,
                   (array_agg(subject ORDER BY received_at DESC))[1] AS last_subject
            FROM mail_memory
            WHERE username = %s
              AND from_email IS NOT NULL AND from_email != ''
            GROUP BY from_email
            HAVING COUNT(*) >= 2
            ORDER BY MAX(received_at) DESC
            LIMIT 100
        """, (username,))
        rows = c.fetchall()
    except Exception as e:
        return {"discovered": 0, "errors": [f"mail_memory query échouée : {str(e)[:200]}"]}
    finally:
        if conn: conn.close()

    for from_email, name, mail_count, last_seen, last_subject in rows:
        try:
            display = name or from_email
            description = (
                f"Contact fréquent : {display} ({from_email}). "
                f"{mail_count} échanges, dernier le {last_seen}. "
                f"Dernier sujet : « {(last_subject or '')[:120]} »."
            )
            vec = embed(description)
            _upsert_schema(
                tenant_id=tenant_id,
                connection_id=connection_id,
                tool_type="contacts",
                schema_type="contact",
                entity_key=f"contact:{from_email.lower()}",
                display_name=display,
                description=description,
                fields_json={"email": from_email, "name": name,
                             "mail_count": mail_count,
                             "last_seen": str(last_seen) if last_seen else "",
                             "last_subject": last_subject or ""},
                relationships_json=[],
                embedding=vec,
            )
            discovered += 1
        except Exception as e:
            errors.append(f"contact {from_email}: {str(e)[:80]}")

    logger.info("[Discovery] Contacts terminé : %d contacts indexés, %d erreurs", discovered, len(errors))
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
