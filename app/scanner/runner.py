"""
Runner du Scanner Universel — execute les scans en background.

Orchestre l execution d un run de vectorisation :
1. Recupere les manifests actifs pour la priorite demandee
2. Pour chaque manifest, fetch pagine les records Odoo via adapter_odoo
3. Pour chaque record, processor.process_record (noeud + aretes + chunk)
4. Checkpoint a chaque batch pour reprise apres interruption
5. Update progress en continu dans scanner_runs.progress

Cas supporte Phase 3 : scan de base, SANS transversaux (mail.message,
mail.tracking.value, ir.attachment). Ces derniers arrivent en Phase 5.

Execution en background thread pour eviter les timeouts HTTP. Polling via
/admin/scanner/run/status?run_id=xxx (memes pattern que introspection).
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("raya.scanner.runner")

# Cache en memoire des runs actifs (le run est aussi persiste en DB via
# scanner_runs, mais le thread vivant est ici)
_ACTIVE_THREADS: dict = {}
_THREADS_LOCK = threading.Lock()


def purge_tenant_data(tenant_id: str, source: str = "odoo") -> dict:
    """Supprime toutes les donnees vectorisees + graphe pour un tenant+source.
    Utilise par le rebuild 'init' (Q4=A valide par Guillaume : purge complete
    avant rebuild propre).

    Attention : operation destructrice. Les tables concernees sont :
    - odoo_semantic_content (chunks vectorises)
    - semantic_graph_nodes + semantic_graph_edges (pour la source donnee)
    - connector_schemas.last_scanned_at reset a NULL

    Retourne le nombre de lignes supprimees par table."""
    from app.database import get_pg_conn
    counts = {}
    with get_pg_conn() as conn:
        cur = conn.cursor()
        # 1. Chunks vectorises
        cur.execute(
            """DELETE FROM odoo_semantic_content
               WHERE tenant_id=%s AND source_model IS NOT NULL""",
            (tenant_id,),
        )
        counts["odoo_semantic_content"] = cur.rowcount
        # 2. Aretes du graphe (CASCADE depuis les noeuds)
        cur.execute(
            """DELETE FROM semantic_graph_edges
               WHERE tenant_id=%s""", (tenant_id,))
        counts["semantic_graph_edges"] = cur.rowcount
        # 3. Noeuds du graphe
        cur.execute(
            """DELETE FROM semantic_graph_nodes
               WHERE tenant_id=%s AND source=%s""",
            (tenant_id, source),
        )
        counts["semantic_graph_nodes"] = cur.rowcount
        # 4. Reset des compteurs sur connector_schemas
        cur.execute(
            """UPDATE connector_schemas
               SET last_scanned_at=NULL, records_count_raya=NULL,
                   integrity_pct=NULL, updated_at=NOW()
               WHERE tenant_id=%s AND source=%s""",
            (tenant_id, source),
        )
        counts["connector_schemas_reset"] = cur.rowcount
        conn.commit()
    logger.warning("[Runner] Purge tenant=%s source=%s : %s",
                   tenant_id, source, counts)
    return counts


def _fetch_active_manifests(
    tenant_id: str, source: str, priority_max: int = 1,
) -> list:
    """Recupere les manifests actifs jusqu a la priorite max incluse,
    tries par priorite croissante puis par taille decroissante (plus gros
    d abord, ca donne une barre de progression plus fluide)."""
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT model_name, priority, manifest, records_count_odoo
               FROM connector_schemas
               WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                 AND priority <= %s
               ORDER BY priority ASC, records_count_odoo DESC NULLS LAST""",
            (tenant_id, source, priority_max),
        )
        rows = cur.fetchall()
        return [{
            "model_name": r[0],
            "priority": r[1],
            "manifest": r[2],
            "records_count_odoo": r[3],
        } for r in rows]


def _get_fields_to_fetch(manifest: dict) -> list:
    """Consolide les champs a fetch depuis Odoo pour un record du modele.
    Union de vectorize_fields + many2one des graph_edges + metadata_fields
    + systematiquement id/display_name/write_date/create_uid/write_uid."""
    fields = set(["id", "display_name", "write_date",
                  "create_uid", "write_uid", "create_date"])
    fields.update(manifest.get("vectorize_fields", []))
    fields.update(manifest.get("metadata_fields", []))
    for edge in manifest.get("graph_edges", []):
        if edge.get("field"):
            fields.add(edge["field"])
    return sorted(fields)


def _run_scan_worker(
    run_id: str, tenant_id: str, source: str,
    priority_max: int, purge_first: bool, batch_size: int = 50,
    record_limits: Optional[dict] = None,
):
    """Worker background execute par un thread. Ne retourne rien, ecrit
    tout dans scanner_runs via orchestrator.update_progress.

    record_limits : {model_name: max_records} pour limiter le volume traite.
    0 = skip complet, None ou absent = illimite.
    """
    from app.scanner import orchestrator
    from app.scanner import adapter_odoo
    from app.scanner.processor import process_record
    from app.database import get_pg_conn

    record_limits = record_limits or {}

    try:
        # 0. Purge initiale si demande (init rebuild)
        if purge_first:
            orchestrator.update_progress(run_id,
                {"step": "purging", "current_model": None})
            counts = purge_tenant_data(tenant_id, source)
            logger.info("[Runner run=%s] Purge : %s", run_id, counts)

        # 1. Recupere les manifests a traiter
        manifests = _fetch_active_manifests(tenant_id, source, priority_max)
        if not manifests:
            orchestrator.fail_run(run_id, "Aucun manifest actif trouve")
            return

        total_models = len(manifests)
        models_progress = {}
        global_stats = {
            "models_processed": 0, "models_total": total_models,
            "records_processed": 0, "nodes_created": 0,
            "edges_created": 0, "chunks_vectorized": 0, "errors": 0,
        }

        for model_idx, mdef in enumerate(manifests):
            model_name = mdef["model_name"]
            manifest = mdef["manifest"]
            total_records = mdef["records_count_odoo"] or 0
            logger.info("[Runner run=%s] === Debut %s (%d records, %d/%d) ===",
                        run_id, model_name, total_records,
                        model_idx+1, total_models)

            fields = _get_fields_to_fetch(manifest)
            checkpoint = orchestrator.get_checkpoint(run_id, model_name) or 0

            # Applique la limite par modele si definie
            model_limit = record_limits.get(model_name)
            if model_limit == 0:
                logger.info("[Runner run=%s] SKIP %s (limite=0)",
                            run_id, model_name)
                global_stats["models_processed"] += 1
                continue
            if model_limit and model_limit < total_records:
                logger.info("[Runner run=%s] %s : limite %d/%d records",
                            run_id, model_name, model_limit, total_records)
                total_records = model_limit

            offset = 0
            records_done_this_model = 0
            records_raya = 0

            while True:
                # Stop si on a atteint la limite du modele
                if model_limit and records_done_this_model >= model_limit:
                    logger.info("[Runner run=%s] %s : limite atteinte (%d)",
                                run_id, model_name, model_limit)
                    break
                # Mise a jour progression en debut de batch
                models_progress[model_name] = {
                    "last_id": checkpoint,
                    "done": records_done_this_model,
                    "total": total_records,
                    "pct": round(100 * records_done_this_model /
                                 total_records, 1) if total_records else 0,
                }
                orchestrator.update_progress(run_id, {
                    "step": "scanning",
                    "current_model": model_name,
                    "current_model_idx": model_idx + 1,
                    "models_total": total_models,
                    "models": models_progress,
                }, stats=global_stats)


                # Fetch batch
                try:
                    batch = adapter_odoo.fetch_records_batch(
                        model_name=model_name,
                        fields=fields,
                        offset=offset,
                        limit=batch_size,
                        order="id asc",
                    )
                except Exception as e:
                    logger.exception("[Runner run=%s] fetch %s offset=%d",
                                     run_id, model_name, offset)
                    global_stats["errors"] += 1
                    # On skip ce batch, on tente le suivant
                    offset += batch_size
                    if offset > (total_records or 0) + batch_size * 2:
                        # Si on depasse largement le total attendu, on abandonne
                        break
                    continue

                if not batch:
                    # Plus rien a fetch
                    break

                # Process chaque record du batch
                for record in batch:
                    try:
                        result = process_record(
                            tenant_id=tenant_id,
                            source=source,
                            model_name=model_name,
                            record=record,
                            manifest=manifest,
                        )
                        if result.get("node_id"):
                            global_stats["nodes_created"] += 1
                            records_raya += 1
                        global_stats["edges_created"] += result.get("edges_count", 0)
                        if result.get("chunk_id"):
                            global_stats["chunks_vectorized"] += 1
                        records_done_this_model += 1
                        global_stats["records_processed"] += 1
                        checkpoint = record.get("id", checkpoint)
                    except Exception as e:
                        logger.exception("[Runner run=%s] process %s:%s",
                                         run_id, model_name, record.get("id"))
                        global_stats["errors"] += 1

                # Checkpoint en DB apres chaque batch
                orchestrator.set_checkpoint(run_id, model_name, checkpoint,
                                            records_done_this_model,
                                            total_records or 0)

                # Avance le curseur
                offset += batch_size
                # Si le batch etait plus petit que batch_size, on a fini
                if len(batch) < batch_size:
                    break

                # Rate limiting : 500ms entre batches (augmente le 18/04
                # apres incident Railway qui tuait l app pour cause de
                # healthcheck /health qui repondait trop lentement pendant
                # le scan intensif. 500ms libere assez de CPU pour /health).
                time.sleep(0.5)


            # Fin du modele : update le compteur records_raya dans connector_schemas
            global_stats["models_processed"] += 1
            try:
                with get_pg_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """UPDATE connector_schemas
                           SET records_count_raya=%s,
                               integrity_pct=CASE
                                 WHEN records_count_odoo > 0
                                 THEN ROUND(100.0 * %s / records_count_odoo, 1)
                                 ELSE NULL END,
                               last_scanned_at=NOW(),
                               updated_at=NOW()
                           WHERE tenant_id=%s AND source=%s AND model_name=%s""",
                        (records_raya, records_raya, tenant_id, source, model_name),
                    )
                    conn.commit()
            except Exception:
                logger.exception("[Runner run=%s] update connector_schemas %s",
                                 run_id, model_name)

            logger.info("[Runner run=%s] === Fin %s : %d records processed, %d edges, %d chunks ===",
                        run_id, model_name, records_done_this_model,
                        global_stats["edges_created"],
                        global_stats["chunks_vectorized"])

        # Run termine avec succes
        orchestrator.finish_run(run_id, stats=global_stats)
        logger.info("[Runner run=%s] TERMINE : %s", run_id, global_stats)

    except Exception as e:
        logger.exception("[Runner run=%s] Crash worker", run_id)
        try:
            orchestrator.fail_run(run_id, f"Worker crash: {str(e)[:500]}")
        except Exception:
            pass
    finally:
        # Nettoyage du cache threads actifs
        with _THREADS_LOCK:
            _ACTIVE_THREADS.pop(run_id, None)


# ─── API publique : lancement et controle des runs ────────────────

# Limites par modele pour eviter de saturer la DB sur les gros volumes.
# Ajoute 18/04 apres incident de saturation volume Railway (5 Go) sur
# product.template (133k records = ~800 Mo de vecteurs + index HNSW ~600 Mo).
# On garde un echantillon representatif, suffisant pour valider les cas
# Coullet/Glandier, SE100K et les kits. Les 133k articles complets arriveront
# en Phase 4+ avec volume DB augmente.
MODEL_RECORD_LIMITS = {
    "product.template": 5000,     # echantillon : top articles + kits
    "product.product": 5000,      # meme logique (pas prevu en P1 mais securite)
    "product.supplierinfo": 10000,  # relations fournisseur
    "mail.message": 10000,        # historique 10k messages recents
    "mail.tracking.value": 10000,
    "res.city": 0,                # referentiel geo = graphe only, skip
    "res.city.zip": 0,
}


def start_scan_p1(
    tenant_id: str = "couffrant",
    source: str = "odoo",
    priority_max: int = 1,
    purge_first: bool = True,
    run_type: str = "init",
    record_limits: Optional[dict] = None,
) -> str:
    """Lance un scan P1 en background thread.

    Args:
        tenant_id: identifiant du tenant
        source: 'odoo' par defaut
        priority_max: 1 pour P1 seul, 2 pour P1+P2
        purge_first: True pour rebuild complet (Q4=A, purge avant)
        run_type: 'init' (premiere fois) / 'rebuild' (re-run ulterieur)
        record_limits: override optionnel des limites par modele
            (ex: {"product.template": 1000}). Par defaut MODEL_RECORD_LIMITS.

    Retourne le run_id. Le statut est interrogeable via
    orchestrator.get_run_status(run_id).
    """
    from app.scanner import orchestrator

    effective_limits = dict(MODEL_RECORD_LIMITS)
    if record_limits:
        effective_limits.update(record_limits)

    run_id = orchestrator.create_run(
        tenant_id=tenant_id,
        source=source,
        run_type=run_type,
        params={
            "priority_max": priority_max,
            "purge_first": purge_first,
            "scope": "P1" if priority_max == 1 else f"P1-P{priority_max}",
            "record_limits": effective_limits,
        },
    )

    thread = threading.Thread(
        target=_run_scan_worker,
        args=(run_id, tenant_id, source, priority_max, purge_first, 50,
              effective_limits),
        daemon=True,
        name=f"scanner-{run_id[:8]}",
    )
    with _THREADS_LOCK:
        _ACTIVE_THREADS[run_id] = thread
    thread.start()

    logger.info("[Runner] Scan lance : run_id=%s, priority_max=%d, purge=%s, limits=%s",
                run_id, priority_max, purge_first, effective_limits)
    return run_id


def is_run_active(run_id: str) -> bool:
    """Verifie si un run a son thread worker encore vivant."""
    with _THREADS_LOCK:
        thread = _ACTIVE_THREADS.get(run_id)
    return bool(thread and thread.is_alive())
