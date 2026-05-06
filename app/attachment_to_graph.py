"""
Attachment -> Semantic Graph.

Pousse les pieces jointes de attachment_index vers semantic_graph_nodes
avec leurs relations vers les autres entites du graphe (Mail, Mailbox,
Person, Company, Project, Folder).

Cree le 06/05/2026 dans le cadre du chantier B (Pieces Jointes mails).
Voir docs/bilan_session_06mai.md et docs/raya_changelog.md.

ARCHITECTURE :
─────────────────────────────────────────────────────────────────
  TABLE SOURCE : attachment_index (rempli par attachment_pipeline.py)

  TABLE CIBLE  : semantic_graph_nodes
                 - 1 node Attachment par ligne attachment_index
                 - node_key = "attachment_{id}"
                 - source = source_type ('mail_attachment', 'drive_file')
                 - source_record_id = attachment_index.id

  EDGES        : semantic_graph_edges
                 - attachment -> Mail (mentioned_in) si vient d un mail
                 - attachment -> Mailbox (delivered_to) si vient d un mail
                 - attachment -> Person (mentioned_in) si nom matche
                 - attachment -> Company (mentioned_in) si nom matche
                 - attachment -> Project (part_of_project) si ref matche
                 - attachment -> Folder (mentioned_in) si dossier matche

EXTRACTION D ENTITES (MVP 06/05) :
─────────────────────────────────────────────────────────────────
  Approche simple : matching fuzzy sur les nodes EXISTANTS du graphe.
  Pas d appel Haiku pour l instant (sera ajoute en etape 3c future
  pour aller chercher des entites qui ne sont pas encore dans le
  graphe).

  Strategie :
    1. Tokeniser le nom de fichier (separateurs _-. )
    2. Generer des bi-grammes ("devis socotec")
    3. Pour chaque token, chercher dans semantic_graph_nodes par label
       (find_nodes_by_label) sur les types Person, Company, Project, Folder
    4. Si match, creer un edge avec confidence = ratio longueur

USAGE :
─────────────────────────────────────────────────────────────────
  push_attachment_to_graph(attachment_id)  # un seul attachment

  Hook automatique : a la fin de process_attachment(), apres le
  _store_attachment reussi. Voir attachment_pipeline.py.
"""
from __future__ import annotations

import re
from typing import Optional

from app.database import get_pg_conn
from app.semantic_graph import (
    add_node, add_edge_by_keys, find_nodes_by_label,
)
from app.logging_config import get_logger

logger = get_logger("raya.attachment_to_graph")


# ─── EXTRACTION D ENTITES ───

def _extract_entities_from_attachment(
    file_name: str,
    text_content: str,
    tenant_id: str,
    text_max_chars: int = 2000,
) -> dict:
    """Extraction simple d entites par matching fuzzy sur le graphe existant.

    MVP 06/05/2026 : pas d appel Haiku, juste matching de tokens contre
    les Person/Company/Project/Folder deja presents dans le graphe.
    """
    matches = {
        "persons": [],
        "companies": [],
        "projects": [],
        "folders": [],
    }

    # 1. Tokenisation du nom de fichier
    name_clean = (file_name or "").lower()
    if "." in name_clean:
        name_clean = name_clean.rsplit(".", 1)[0]
    name_tokens = re.split(r"[_\-.\s]+", name_clean)
    name_tokens = [t for t in name_tokens if len(t) >= 3]

    # 2. Bi-grammes du nom de fichier
    bi_tokens = []
    for i in range(len(name_tokens) - 1):
        bi_tokens.append(f"{name_tokens[i]} {name_tokens[i + 1]}")

    # 3. Tokens du texte (premiers 2000 chars)
    text_snippet = (text_content or "")[:text_max_chars].lower()
    text_tokens = re.findall(r"\b[a-zA-Zéèêàâîïôöûü]{4,}\b", text_snippet)
    from collections import Counter
    text_tokens = [w for w, _ in Counter(text_tokens).most_common(30)]

    # 4. Liste finale de candidats (dedupliques + cap)
    candidates = list(set(name_tokens + bi_tokens + text_tokens))[:50]

    # 5. Matching dans le graphe pour chaque candidat
    seen_keys = set()
    type_mapping = [
        ("Person", "persons"),
        ("Company", "companies"),
        ("Project", "projects"),
        ("Folder", "folders"),
    ]

    for cand in candidates:
        if len(cand) < 3:
            continue
        for node_type, key in type_mapping:
            try:
                results = find_nodes_by_label(
                    tenant_id, cand,
                    node_type=node_type, limit=3,
                )
                for r in results:
                    if r["node_key"] in seen_keys:
                        continue
                    label_lower = (r["node_label"] or "").lower()
                    if not label_lower or cand not in label_lower:
                        continue
                    score = min(1.0, len(cand) / max(len(label_lower), 1))
                    matches[key].append({
                        "node_key": r["node_key"],
                        "node_label": r["node_label"],
                        "node_type": r["node_type"],
                        "score": score,
                        "match_term": cand,
                    })
                    seen_keys.add(r["node_key"])
            except Exception as e:
                logger.debug(
                    "[AttachToGraph] match %s/%s : %s",
                    node_type, cand[:20], str(e)[:80],
                )

    return matches


# ─── CONTEXTE MAIL PARENT ───

def _get_mail_for_attachment(attachment_id: int) -> Optional[dict]:
    """Recupere les infos du mail parent depuis la source_ref.

    source_ref pour mail_attachment = "{message_id}:{outlook_or_gmail_att_id}"
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT source_type, source_ref FROM attachment_index WHERE id = %s",
            (attachment_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        source_type, source_ref = row
        if source_type != "mail_attachment" or ":" not in (source_ref or ""):
            return None
        message_id = source_ref.rsplit(":", 1)[0]

        c.execute(
            """
            SELECT id, tenant_id, message_id, mailbox_email
            FROM mail_memory
            WHERE message_id = %s
              AND deleted_at IS NULL
            LIMIT 1
            """,
            (message_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "mail_id": row[0],
            "tenant_id": row[1],
            "message_id": row[2],
            "mailbox_email": row[3],
        }
    except Exception as e:
        logger.warning(
            "[AttachToGraph] _get_mail_for_attachment %s : %s",
            attachment_id, str(e)[:200],
        )
        return None
    finally:
        if conn:
            conn.close()


# ─── PUSH UNITAIRE ───

def push_attachment_to_graph(attachment_id: int) -> Optional[int]:
    """Pousse une PJ vers le graphe avec ses edges contextuelles.

    Idempotent : ON CONFLICT DO UPDATE sur (tenant_id, node_type, node_key).

    Cree :
      1. Le node Attachment
      2. Edge Attachment -> Mail (mentioned_in) si vient d un mail
      3. Edge Attachment -> Mailbox (delivered_to) idem
      4. Edges fuzzy Attachment -> Person/Company/Project/Folder via
         matching du nom + contenu sur le graphe existant

    Returns:
        Le node_id Attachment cree (int), ou None si echec.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, tenant_id, file_name, file_size, mime_type,
                   text_content, source_type, source_ref, connection_id,
                   summary_content, vision_processed
            FROM attachment_index
            WHERE id = %s
            """,
            (attachment_id,),
        )
        row = c.fetchone()
        if not row:
            logger.warning("[AttachToGraph] attachment %s introuvable",
                            attachment_id)
            return None
        cols = [
            "id", "tenant_id", "file_name", "file_size", "mime_type",
            "text_content", "source_type", "source_ref", "connection_id",
            "summary_content", "vision_processed",
        ]
        att = dict(zip(cols, row))
    except Exception as e:
        logger.error(
            "[AttachToGraph] lecture attachment %s : %s",
            attachment_id, str(e)[:200],
        )
        return None
    finally:
        if conn:
            conn.close()

    if not att["tenant_id"]:
        logger.debug("[AttachToGraph] attachment %s sans tenant_id, skip",
                      attachment_id)
        return None

    # ─ 1. Node Attachment ─
    label = (att["file_name"] or "(sans nom)")[:200]
    size_kb = (att["file_size"] or 0) / 1024
    node_id = add_node(
        tenant_id=att["tenant_id"],
        node_type="Attachment",
        node_key=f"attachment_{att['id']}",
        node_label=label,
        node_properties={
            "file_name": att["file_name"],
            "file_size": att["file_size"],
            "size_kb": round(size_kb, 1),
            "mime_type": att["mime_type"],
            "source_type": att["source_type"],
            "source_ref": att["source_ref"],
            "connection_id": att["connection_id"],
            "vision_processed": att["vision_processed"],
            "has_text": bool(att.get("text_content")),
            "has_summary": bool(att.get("summary_content")),
        },
        source=att["source_type"] or "attachment",
        source_record_id=str(att["id"]),
    )
    if not node_id:
        logger.warning("[AttachToGraph] add_node attachment %s echec",
                        attachment_id)
        return None

    edges_created = 0

    # ─ 2 + 3. Edges vers le mail parent et la mailbox ─
    if att["source_type"] == "mail_attachment":
        mail_info = _get_mail_for_attachment(attachment_id)
        if mail_info:
            try:
                add_edge_by_keys(
                    tenant_id=att["tenant_id"],
                    from_type="Attachment",
                    from_key=f"attachment_{att['id']}",
                    to_type="Mail",
                    to_key=f"mail_{mail_info['mail_id']}",
                    edge_type="mentioned_in",
                    edge_confidence=1.0,
                    edge_source="explicit_source",
                )
                edges_created += 1
            except Exception as e:
                logger.debug(
                    "[AttachToGraph] edge -> Mail echec : %s", str(e)[:100],
                )

            if mail_info.get("mailbox_email"):
                try:
                    add_edge_by_keys(
                        tenant_id=att["tenant_id"],
                        from_type="Attachment",
                        from_key=f"attachment_{att['id']}",
                        to_type="Mailbox",
                        to_key=f"mailbox_{mail_info['mailbox_email']}",
                        edge_type="delivered_to",
                        edge_confidence=1.0,
                        edge_source="explicit_source",
                    )
                    edges_created += 1
                except Exception as e:
                    logger.debug(
                        "[AttachToGraph] edge -> Mailbox echec : %s",
                        str(e)[:100],
                    )

    # ─ 4. Edges fuzzy vers entites existantes ─
    try:
        entities = _extract_entities_from_attachment(
            file_name=att["file_name"] or "",
            text_content=att.get("text_content") or "",
            tenant_id=att["tenant_id"],
        )

        edge_mapping = [
            ("persons", "mentioned_in", "Person"),
            ("companies", "mentioned_in", "Company"),
            ("projects", "part_of_project", "Project"),
            ("folders", "mentioned_in", "Folder"),
        ]
        for entity_type_plural, edge_type, target_node_type in edge_mapping:
            for ent in entities.get(entity_type_plural, []):
                if ent["score"] < 0.3:
                    continue
                try:
                    add_edge_by_keys(
                        tenant_id=att["tenant_id"],
                        from_type="Attachment",
                        from_key=f"attachment_{att['id']}",
                        to_type=target_node_type,
                        to_key=ent["node_key"],
                        edge_type=edge_type,
                        edge_confidence=ent["score"],
                        edge_source="llm_inferred",
                        edge_metadata={
                            "match_term": ent["match_term"],
                            "matching_method": "fuzzy_file_name_text",
                            "phase": "B_etape_3b",
                        },
                    )
                    edges_created += 1
                except Exception as e:
                    logger.debug(
                        "[AttachToGraph] edge entity echec : %s",
                        str(e)[:100],
                    )
    except Exception as e:
        logger.warning(
            "[AttachToGraph] extraction entites echec : %s", str(e)[:200],
        )

    if edges_created > 0:
        logger.info(
            "[AttachToGraph] PJ #%d (%s) -> %d edges crees",
            attachment_id, (att["file_name"] or "?")[:30], edges_created,
        )

    return node_id
