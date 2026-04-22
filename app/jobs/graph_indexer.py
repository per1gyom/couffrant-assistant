"""
Indexation des conversations dans le graphe semantique (v2).

Role : inserer les conversations Raya (table aria_memory) dans le graphe
semantique comme noeuds de type Conversation, et creer les edges vers
les entites citees dans ces conversations.

Ainsi, quand Raya fait search_graph("Legroux"), elle remonte :
  - Les partners, devis, factures, events Odoo (deja la)
  - Les mails et fichiers Drive (deja la)
  - ET les conversations passees ou Legroux a ete discute (NOUVEAU)

Principe de batching :
  - Toutes les 8 conversations non indexees (colonne indexed_in_graph=false)
    OU
  - Apres 30 minutes d inactivite sur des conversations non indexees

Cela evite la latence synchrone a chaque message et garantit que le
graphe reste a jour raisonnablement.

Non declenche depuis la boucle agent. Tourne en job autonome
(scheduler cron ou thread en fond).
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("raya.graph_indexer")


# ==========================================================================
# SEUILS DE DECLENCHEMENT
# ==========================================================================
# Ajustement v2.1 (22/04) : batch de 1 (quasi-synchrone) au lieu de 8.
# Raison : avec l historique in-prompt reduit a 3 echanges, les echanges
# plus anciens doivent etre dans le graphe sans delai. Sinon, trou de
# memoire entre l echange n4 et son indexation (qui attendait n12).
# Le cout est negligeable (INSERT + regex ~50-100ms, async, non bloquant).
BATCH_SIZE = 1  # Indexation quasi-immediate
INACTIVITY_MINUTES = 1  # Delai minimal pour le lot si batch=1 pas atteint


# ==========================================================================
# PRE-REQUIS DB
# ==========================================================================

def ensure_schema() -> None:
    """
    Ajoute la colonne aria_memory.indexed_in_graph si elle n existe pas.
    Idempotent. Appele au demarrage du job.
    """
    from app.database import get_pg_conn

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "ALTER TABLE aria_memory "
            "ADD COLUMN IF NOT EXISTS indexed_in_graph BOOLEAN DEFAULT false"
        )
        c.execute(
            "ALTER TABLE aria_memory "
            "ADD COLUMN IF NOT EXISTS graph_indexed_at TIMESTAMP"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_aria_memory_not_indexed "
            "ON aria_memory (indexed_in_graph, id) "
            "WHERE indexed_in_graph = false"
        )
        conn.commit()
        logger.info("[graph_indexer] Schema aria_memory verifie/ajuste")
    finally:
        conn.close()


# ==========================================================================
# DETECTION DES CONVERSATIONS A INDEXER
# ==========================================================================

def get_pending_conversations(tenant_id: str, limit: int = 100) -> list[dict]:
    """
    Retourne les conversations non encore indexees dans le graphe,
    toutes ensembles et classees par ordre chronologique.
    """
    from app.database import get_pg_conn

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        # Recupere les convs du tenant qui ont du contenu exploitable
        c.execute(
            """
            SELECT am.id, am.username, am.user_input, am.aria_response, am.created_at
            FROM aria_memory am
            LEFT JOIN users u ON u.username = am.username
            WHERE (am.indexed_in_graph = false OR am.indexed_in_graph IS NULL)
              AND am.user_input IS NOT NULL
              AND am.aria_response IS NOT NULL
              AND LENGTH(am.user_input) > 3
              AND COALESCE(u.tenant_id, 'couffrant_solar') = %s
            ORDER BY am.id ASC
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    finally:
        conn.close()


def should_run_batch(tenant_id: str) -> tuple[bool, str]:
    """
    Decide si on doit lancer un batch maintenant.

    Returns:
        (should_run: bool, reason: str)

    Regles :
      - Si >=8 conversations non indexees -> run
      - Si derniere conversation non indexee a plus de 30 min -> run
      - Sinon -> ne pas run
    """
    from app.database import get_pg_conn

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT COUNT(*), MAX(created_at)
            FROM aria_memory am
            LEFT JOIN users u ON u.username = am.username
            WHERE (am.indexed_in_graph = false OR am.indexed_in_graph IS NULL)
              AND am.user_input IS NOT NULL
              AND am.aria_response IS NOT NULL
              AND COALESCE(u.tenant_id, 'couffrant_solar') = %s
            """,
            (tenant_id,),
        )
        count, last_created = c.fetchone()
        count = count or 0

        if count >= BATCH_SIZE:
            return True, f"seuil atteint ({count} convs en attente)"

        if count > 0 and last_created:
            age = datetime.now() - last_created
            if age > timedelta(minutes=INACTIVITY_MINUTES):
                return True, f"inactivite >{INACTIVITY_MINUTES}min ({count} convs)"

        return False, f"pas encore ({count} convs, pas d inactivite)"
    finally:
        conn.close()


# ==========================================================================
# EXTRACTION D ENTITES + INDEXATION D UNE CONVERSATION
# ==========================================================================

def index_conversation(
    conv: dict,
    tenant_id: str,
) -> dict:
    """
    Indexe une conversation dans le graphe semantique :
      1. Cree un noeud Conversation (type=Conversation, key=conv_{id})
      2. Extrait les cles d entites citees dans user_input + aria_response
      3. Cree un edge mentioned_in entre chaque entite trouvee et la
         conversation.

    Returns:
        {
            "conv_id": int,
            "node_id": int,
            "entities_linked": int,
            "entity_keys": list[str],
        }
    """
    from app.semantic_graph import add_node, add_edge_by_keys
    from app.entity_graph import _extract_entity_keys

    conv_id = conv["id"]
    user_text = conv.get("user_input") or ""
    raya_text = conv.get("aria_response") or ""
    combined_text = f"{user_text}\n{raya_text}"

    # 1. Creer le noeud Conversation
    node_key = f"conv_{conv_id}"
    summary = user_text[:200] + (" ..." if len(user_text) > 200 else "")

    node_id = add_node(
        tenant_id=tenant_id,
        node_type="Conversation",
        node_key=node_key,
        node_label=summary,
        node_properties={
            "username": conv.get("username"),
            "created_at": str(conv.get("created_at")),
            "text_length": len(combined_text),
        },
        source="aria_memory",
        source_record_id=str(conv_id),
    )


    # 2. Extraire les entites citees
    # _extract_entity_keys normalise les clees (majuscules -> lowercase,
    # dedouble les espaces, retire les accents, etc.)
    entity_keys = _extract_entity_keys(combined_text)

    if not entity_keys:
        return {
            "conv_id": conv_id,
            "node_id": node_id,
            "entities_linked": 0,
            "entity_keys": [],
        }

    # 3. Creer les edges mentioned_in vers chaque entite
    # L entite doit deja exister dans le graphe (via populate_from_odoo,
    # populate_from_mail_memory, populate_from_drive, etc.). Si l entite
    # n existe pas, on passe silencieusement (pas grave).
    # add_edge_by_keys exige from_type ET to_type, mais on ne connait pas
    # le type de la cible a partir de la seule cle. On resout donc le
    # (node_id, node_type) via une requete directe puis on appelle add_edge.
    from app.semantic_graph import add_edge, find_node_id
    from app.database import get_pg_conn

    linked = 0
    linked_keys = []

    # Recuperer l id du noeud Conversation qu on vient de creer
    conv_node_id = find_node_id(tenant_id, "Conversation", node_key)
    if not conv_node_id:
        logger.warning(
            "[graph_indexer] conv %d : impossible de resoudre le noeud Conversation",
            conv_id,
        )
        return {
            "conv_id": conv_id,
            "node_id": node_id,
            "entities_linked": 0,
            "entity_keys": [],
        }

    # Pour chaque entite extraite, chercher tous les noeuds avec cette cle
    # (quel que soit le type) et creer un edge depuis la conversation.
    for ekey in entity_keys:
        try:
            conn = get_pg_conn()
            try:
                c = conn.cursor()
                c.execute(
                    "SELECT id, node_type FROM semantic_graph_nodes "
                    "WHERE tenant_id = %s AND node_key = %s",
                    (tenant_id, ekey),
                )
                target_rows = c.fetchall()
            finally:
                conn.close()

            for target_id, target_type in target_rows:
                edge_id = add_edge(
                    tenant_id=tenant_id,
                    from_id=conv_node_id,
                    to_id=target_id,
                    edge_type="mentioned_in",
                    edge_confidence=0.8,
                    edge_source="llm_inferred",
                )
                if edge_id:
                    linked += 1
                    linked_keys.append(f"{target_type}:{ekey}")
        except Exception as e:
            logger.debug(
                "[graph_indexer] conv %d: impossible de lier entite %s: %s",
                conv_id, ekey, e,
            )

    return {
        "conv_id": conv_id,
        "node_id": node_id,
        "entities_linked": linked,
        "entity_keys": linked_keys,
    }


# ==========================================================================
# EXECUTION D UN BATCH
# ==========================================================================

def run_batch(tenant_id: str) -> dict:
    """
    Execute un batch d indexation pour un tenant donne.

    Returns:
        {
            "tenant_id": str,
            "conversations_processed": int,
            "total_entities_linked": int,
            "errors": list[str],
        }
    """
    from app.database import get_pg_conn

    ensure_schema()

    pending = get_pending_conversations(tenant_id, limit=100)
    if not pending:
        return {
            "tenant_id": tenant_id,
            "conversations_processed": 0,
            "total_entities_linked": 0,
            "errors": [],
        }

    logger.info(
        "[graph_indexer] Batch %s : %d conversations a indexer",
        tenant_id, len(pending),
    )

    total_linked = 0
    errors = []
    indexed_ids = []


    for conv in pending:
        try:
            result = index_conversation(conv, tenant_id)
            total_linked += result["entities_linked"]
            indexed_ids.append(conv["id"])
            logger.info(
                "[graph_indexer] conv %d -> node %d, %d entites liees",
                conv["id"], result["node_id"], result["entities_linked"],
            )
        except Exception as e:
            err = f"conv {conv['id']}: {type(e).__name__}: {e}"
            errors.append(err)
            logger.exception("[graph_indexer] %s", err)

    # Marquer les conversations traitees comme indexees
    if indexed_ids:
        conn = get_pg_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE aria_memory "
                "SET indexed_in_graph = true, graph_indexed_at = NOW() "
                "WHERE id = ANY(%s)",
                (indexed_ids,),
            )
            conn.commit()
        finally:
            conn.close()

    logger.info(
        "[graph_indexer] Batch termine : %d convs, %d entites liees, %d erreurs",
        len(indexed_ids), total_linked, len(errors),
    )
    return {
        "tenant_id": tenant_id,
        "conversations_processed": len(indexed_ids),
        "total_entities_linked": total_linked,
        "errors": errors,
    }


# ==========================================================================
# POINT D ENTREE POUR LE SCHEDULER
# ==========================================================================

def run_if_needed(tenant_id: str = "couffrant_solar") -> dict:
    """
    Point d entree appele par le scheduler (toutes les 2-5 min).

    Ne lance un batch que si les conditions sont reunies
    (voir should_run_batch).
    """
    should_run, reason = should_run_batch(tenant_id)
    if not should_run:
        logger.debug("[graph_indexer] Skip : %s", reason)
        return {"skipped": True, "reason": reason}

    logger.info("[graph_indexer] Run : %s", reason)
    return run_batch(tenant_id)


# ==========================================================================
# CLI POUR TEST MANUEL
# ==========================================================================

if __name__ == "__main__":
    # Usage : python -m app.jobs.graph_indexer [tenant_id]
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    tenant = sys.argv[1] if len(sys.argv) > 1 else "couffrant_solar"
    print(f"Lancement batch graph_indexer pour tenant={tenant}")
    result = run_if_needed(tenant)
    print(f"Resultat : {result}")
