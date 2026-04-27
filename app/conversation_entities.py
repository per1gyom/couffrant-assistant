"""
Collecteur d entites pour les conversations chat (etape 1 fix - 27/04/2026).

PROBLEMATIQUE
=============
Quand Raya repond a un user, elle utilise des outils (search_graph,
get_client_360, search_drive, etc.) qui retournent des entites du graphe
semantique (Person, Company, Deal, etc.). Ces entites sont LES vraies
entites pertinentes pour cet echange : ce sont celles que Raya a regardees
pour formuler sa reponse.

Avant : on essayait de DEVINER ces entites apres-coup en parsant le texte
de la conversation avec des regex. Imprecis (faux positifs type
"Bonne soiree" -> "BONNET POLAIRE"), couteux, fragile.

Apres : on CAPTURE les entites au moment ou Raya les consulte. Pattern
identique a Odoo et Drive (lien explicite a la source). Confidence 1.0.

UTILISATION (3 etapes)
======================
1. Au debut d un echange agent : start_collecting() (un seul echange a la fois)
2. Pendant l execution d un outil : add_entity(node_id, ...) pour chaque
   entite consultee
3. A la sauvegarde de la conversation : flush_to_graph(conv_id) cree les
   edges mentioned_in vers toutes les entites collectees

THREAD-SAFETY
=============
Un user a UN seul echange en cours a la fois (la boucle agent est
synchrone par requete). On utilise contextvars pour isoler par requete
HTTP, donc 100% safe en multi-tenant / multi-user concurrent.
"""

import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger("raya.conv_entities")


# ContextVar : isole le collecteur par requete HTTP (asyncio safe).
# Chaque requete a son propre set d entites, pas de fuite entre users.
_current_collector: ContextVar[Optional[set]] = ContextVar(
    "_current_collector", default=None
)


def start_collecting() -> None:
    """Demarre la collecte d entites pour un nouvel echange.
    A appeler au debut de la boucle agent. Reinitialise le set."""
    _current_collector.set(set())
    logger.debug("[ConvEntities] Demarrage collecte")


def add_entity(node_id: int) -> None:
    """Ajoute un node_id a la liste des entites consultees pendant l echange.
    No-op si aucune collecte n est active (cas hors agent : webhook, cron...).

    Args:
        node_id: ID du noeud dans semantic_graph_nodes
    """
    collector = _current_collector.get()
    if collector is None:
        return  # Pas de collecte active, ignore silencieusement
    if not isinstance(node_id, int) or node_id <= 0:
        return  # Garde-fou : ID invalide, ignore
    collector.add(node_id)


def add_entities_from_search_results(results: list) -> None:
    """Helper : extrait les node_id d une liste de resultats et les ajoute
    au collecteur.

    Supporte plusieurs formats de results :
      - { "node_id": int, ... }                    (search_graph direct)
      - { "id": int, "type": ... }                 (find_nodes_by_label)
      - { "graph_node_id": int, ... }              (alternative)

    Plusieurs formats supportes pour robustesse.
    """
    collector = _current_collector.get()
    if collector is None or not results:
        return
    for r in results:
        if not isinstance(r, dict):
            continue
        # Plusieurs formats possibles selon la source
        for key in ("node_id", "id", "graph_node_id"):
            val = r.get(key)
            if isinstance(val, int) and val > 0:
                collector.add(val)
                break


# Types d entites pertinentes pour des questions humaines.
# On exclut volontairement les types techniques internes (Value, Schedule,
# Question, TourStop, Tour, DealLine, Field, Message, etc.) qui sont des
# noeuds derives d Odoo via le manifest_generator et qui partagent souvent
# le meme source_record_id que leur partner parent. Sans ce filtre, une
# conversation sur Coullet creerait 50+ edges parasites vers ces types
# techniques.
_RELEVANT_NODE_TYPES = {
    "Person", "Company", "Project", "Product",
    "Deal", "Invoice", "Payment",
    "Event", "Document", "Mail",
    "Ticket", "Task", "Lead",
    "File", "Folder",  # Drive
}


def add_entities_from_odoo_results(tenant_id: str, results: list) -> None:
    """Helper pour les resultats des outils unified_search / hybrid_search
    (search_odoo, search_drive, search_graph).

    Les resultats contiennent (source_model, source_record_id) qui
    permettent de retrouver le node_id correspondant dans
    semantic_graph_nodes via les colonnes (source, source_record_id).

    Format attendu (chaque result) :
      { "source_model": "res.partner", "source_record_id": "3795", ... }

    Filtrage : seuls les types pertinents (Person, Deal, Event, etc.) sont
    captures. Les types techniques (Value, Schedule, Field, etc.) sont
    ignores car ils generent du bruit.
    """
    collector = _current_collector.get()
    if collector is None or not results:
        return

    # Collecter les source_record_id uniques (pour minimiser les requetes)
    source_record_ids = set()
    for r in results:
        if not isinstance(r, dict):
            continue
        sri = r.get("source_record_id")
        if sri:
            source_record_ids.add(str(sri))

    if not source_record_ids:
        return

    # Une seule requete avec ANY pour tous les SRI a la fois
    # + filtre sur les types pertinents
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM semantic_graph_nodes
            WHERE tenant_id = %s
              AND source_record_id = ANY(%s)
              AND node_type = ANY(%s)
        """, (tenant_id, list(source_record_ids), list(_RELEVANT_NODE_TYPES)))
        for row in c.fetchall():
            collector.add(row[0])
    except Exception as e:
        logger.debug("[ConvEntities] resolution Odoo a echoue : %s", e)
    finally:
        if conn:
            conn.close()


def add_entity_by_source(tenant_id: str, source: str,
                         source_record_id: str) -> None:
    """Helper unitaire : resout un node_id via (source, source_record_id)
    et l ajoute au collecteur. Utile pour outils qui consultent UNE entite
    a la fois (get_client_360, read_drive_file...).

    Filtrage : limite aux types pertinents (Person, Deal, etc.), evite
    les types techniques internes (Value, Schedule, etc.).
    """
    collector = _current_collector.get()
    if collector is None or not source_record_id:
        return
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM semantic_graph_nodes
            WHERE tenant_id = %s AND source = %s
              AND source_record_id = %s
              AND node_type = ANY(%s)
            LIMIT 5
        """, (tenant_id, source, str(source_record_id),
              list(_RELEVANT_NODE_TYPES)))
        for row in c.fetchall():
            collector.add(row[0])
    except Exception as e:
        logger.debug(
            "[ConvEntities] resolution %s/%s a echoue : %s",
            source, source_record_id, e,
        )
    finally:
        if conn:
            conn.close()


def get_collected() -> list:
    """Retourne la liste des node_id collectes (sans reset)."""
    collector = _current_collector.get()
    if collector is None:
        return []
    return sorted(collector)


def flush_to_graph(conv_id: int, tenant_id: str, conv_node_id: int) -> int:
    """Cree les edges mentioned_in dans le graphe pour tous les node_id
    collectes pendant l echange.

    Args:
        conv_id: id de la conversation dans aria_memory (pour logging)
        tenant_id: tenant
        conv_node_id: id du noeud Conversation deja cree dans semantic_graph_nodes

    Returns:
        Nombre d edges crees.
    """
    from app.semantic_graph import add_edge

    collected = get_collected()
    if not collected:
        logger.debug(
            "[ConvEntities] conv %d : aucune entite collectee, skip",
            conv_id,
        )
        return 0

    edges_created = 0
    for target_id in collected:
        # Skip auto-edge si target = conversation elle-meme (defensif)
        if target_id == conv_node_id:
            continue
        try:
            edge_id = add_edge(
                tenant_id=tenant_id,
                edge_from=conv_node_id,
                edge_to=target_id,
                edge_type="mentioned_in",
                edge_confidence=1.0,            # source explicit = certitude max
                edge_source="explicit_source",  # comme Odoo et Drive
            )
            if edge_id:
                edges_created += 1
        except Exception as e:
            logger.debug(
                "[ConvEntities] conv %d : edge vers %d echoue : %s",
                conv_id, target_id, e,
            )

    logger.info(
        "[ConvEntities] conv %d : %d edges mentioned_in crees (sur %d entites collectees)",
        conv_id, edges_created, len(collected),
    )
    return edges_created


def reset() -> None:
    """Reset explicite (utile pour les tests). Le ContextVar se reset
    naturellement a la fin de chaque requete HTTP."""
    _current_collector.set(None)
