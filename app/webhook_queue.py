"""Queue et worker des webhooks Odoo (Phase A.2 roadmap v4).

Architecture valide le 19/04/2026 (voir annexes Q1-Q6 de raya_planning_v4.md) :

- Les webhooks arrivent sur /webhooks/odoo/record-changed et sont **enqueues**
  dans la table vectorization_queue (persistee disque, pas de perte si crash).
- Un **worker** thread daemon depile au rythme confortable et re-fetche les
  records depuis Odoo (re-fetch = securite + coherence, voir Q3).
- **Dedup 5s** : si le meme record est deja en queue non traitee depuis moins
  de 5 secondes, on ignore le doublon (economise les re-embeds en cascade).
- **Rate limiter OpenAI** : max 2000 embeddings/min (marge sur 3000 autorises).

Ce module ne fait AUCUNE logique metier : il appelle le scanner generique
(processor.process_record + adapter_odoo.fetch_record_with_transversals).
"""

import os
import time
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("raya.webhook_queue")

# Dedup : on considere un record comme "deja en queue" si on le voit
# avec le meme (tenant, source, model, record_id) et created_at > NOW() - 5s
# ET completed_at IS NULL
DEDUP_WINDOW_SECONDS = 5

# Rate limiter : glissant sur 60 secondes, max 2000 embeddings
OPENAI_RATE_MAX_PER_MIN = 2000
_openai_calls_timestamps = deque(maxlen=OPENAI_RATE_MAX_PER_MIN + 100)
_rate_lock = threading.Lock()

# Worker : intervalle de polling de la queue (ms de sommeil entre 2 depiles
# quand la queue est vide). Trop bas = CPU. Trop haut = latence perceptible.
WORKER_IDLE_SLEEP_MS = 500

# Timeout du worker sur un record (fetch + processor). Au dela, on abandonne
# le record et on passe au suivant pour eviter qu un record casse bloque tout.
WORKER_RECORD_TIMEOUT_S = 30

# Flag global du worker. Permet un shutdown propre via stop_worker().
_worker_running = threading.Event()
_worker_thread: Optional[threading.Thread] = None


def _rate_limit_openai():
    """Bloque l appel si on a deja fait 2000 requetes OpenAI dans la derniere
    minute. Libere automatiquement quand la fenetre glissante permet un nouveau
    call. Thread-safe grace au lock."""
    with _rate_lock:
        now = time.time()
        # Purge les timestamps > 60s
        while _openai_calls_timestamps and _openai_calls_timestamps[0] < now - 60:
            _openai_calls_timestamps.popleft()
        if len(_openai_calls_timestamps) >= OPENAI_RATE_MAX_PER_MIN:
            wait = 60 - (now - _openai_calls_timestamps[0])
            logger.warning("[WebhookQueue] Rate limit OpenAI : wait %.1fs", wait)
            time.sleep(max(wait, 0.1))
        _openai_calls_timestamps.append(time.time())


def enqueue(
    tenant_id: str, source: str, model_name: str, record_id: int,
    action: str = "upsert", nonce: Optional[str] = None,
    priority: int = 5, source_info: Optional[dict] = None,
) -> str:
    """Insere un webhook dans la queue, avec dedup 5s et verification anti-rejeu.

    Retourne :
        "enqueued" : nouveau job insere
        "deduped"  : un job identique existe deja (moins de 5s, pas traite)
        "replayed" : le nonce est deja en base (rejeu detecte) -> rejete

    Le nonce est optionnel pour les appels internes (delta sync, tests).
    Pour les webhooks externes, il est obligatoire (anti-rejeu).
    """
    import json
    from app.database import get_pg_conn

    with get_pg_conn() as conn:
        cur = conn.cursor()

        # 1. Anti-rejeu : si nonce fourni, rejeter s il existe deja pour ce tenant
        if nonce:
            cur.execute(
                "SELECT 1 FROM vectorization_queue WHERE tenant_id=%s AND nonce=%s LIMIT 1",
                (tenant_id, nonce),
            )
            if cur.fetchone():
                logger.warning("[WebhookQueue] REJEU detecte tenant=%s nonce=%s",
                               tenant_id, nonce[:20])
                return "replayed"

        # 2. Dedup : meme record en queue recente pas encore traite ?
        cur.execute(
            """SELECT id FROM vectorization_queue
               WHERE tenant_id=%s AND source=%s AND model_name=%s
                 AND record_id=%s AND action=%s
                 AND completed_at IS NULL
                 AND created_at > NOW() - INTERVAL '%s seconds'
               LIMIT 1""",
            (tenant_id, source, model_name, record_id, action, DEDUP_WINDOW_SECONDS),
        )
        existing = cur.fetchone()
        if existing:
            # On met tout de meme a jour scheduled_at pour decaler le
            # traitement apres les 5s (garantit qu on lit la version finale).
            cur.execute(
                "UPDATE vectorization_queue SET scheduled_at=NOW() + INTERVAL '%s seconds' WHERE id=%s",
                (DEDUP_WINDOW_SECONDS, existing[0]),
            )
            conn.commit()
            logger.debug("[WebhookQueue] dedup: %s.%s.%s deja en queue (id=%s)",
                         source, model_name, record_id, existing[0])
            return "deduped"

        # 3. Insertion du nouveau job
        cur.execute(
            """INSERT INTO vectorization_queue
               (tenant_id, source, model_name, record_id, action, priority,
                nonce, source_info, scheduled_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                       NOW() + INTERVAL '%s seconds')""",
            (tenant_id, source, model_name, record_id, action, priority,
             nonce, json.dumps(source_info or {}), DEDUP_WINDOW_SECONDS),
        )
        conn.commit()
        return "enqueued"


def _fetch_next_job() -> Optional[dict]:
    """Recupere (et marque 'in_progress') le prochain job disponible.
    Critere : scheduled_at <= NOW(), completed_at IS NULL, tri par priority asc
    puis scheduled_at asc. Atomique via UPDATE ... RETURNING + SELECT FOR UPDATE."""
    from app.database import get_pg_conn

    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE vectorization_queue
               SET started_at = NOW(), attempts = attempts + 1
               WHERE id = (
                   SELECT id FROM vectorization_queue
                   WHERE completed_at IS NULL
                     AND (started_at IS NULL OR started_at < NOW() - INTERVAL '5 minutes')
                     AND scheduled_at <= NOW()
                   ORDER BY priority ASC, scheduled_at ASC
                   LIMIT 1
                   FOR UPDATE SKIP LOCKED
               )
               RETURNING id, tenant_id, source, model_name, record_id, action,
                         attempts, nonce""",
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            return None
        return {
            "id": row[0], "tenant_id": row[1], "source": row[2],
            "model_name": row[3], "record_id": row[4], "action": row[5],
            "attempts": row[6], "nonce": row[7],
        }


def _mark_completed(job_id: int, success: bool, error: Optional[str] = None):
    """Marque un job termine (succes ou echec apres max_attempts)."""
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE vectorization_queue SET completed_at=NOW(), last_error=%s WHERE id=%s",
            (error[:500] if error else None, job_id),
        )
        conn.commit()


def _process_job(job: dict) -> tuple[bool, Optional[str]]:
    """Traite un job : re-fetch le record depuis Odoo + process_record.

    Pour action='delete' : marque les chunks correspondants avec deleted_at
    sans re-fetcher (le record n existe plus cote Odoo).

    Retourne (success, error_message)."""
    try:
        from app.database import get_pg_conn

        tenant_id = job["tenant_id"]
        source = job["source"]
        model = job["model_name"]
        rid = job["record_id"]

        if job["action"] == "delete":
            # Soft delete : on marque les chunks + noeud + aretes
            with get_pg_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """UPDATE odoo_semantic_content SET deleted_at=NOW()
                       WHERE tenant_id=%s AND source_model=%s AND source_record_id=%s
                         AND deleted_at IS NULL""",
                    (tenant_id, model, str(rid)),
                )
                cur.execute(
                    """UPDATE semantic_graph_nodes SET deleted_at=NOW()
                       WHERE tenant_id=%s AND source=%s AND source_record_id=%s
                         AND deleted_at IS NULL""",
                    (tenant_id, source, str(rid)),
                )
                conn.commit()
            logger.info("[WebhookQueue] Soft delete %s/%s #%s OK",
                        source, model, rid)
            return (True, None)


        # Action 'upsert' (create ou write) : re-fetch + processor generique
        # On charge d abord le manifest pour savoir quels champs recuperer
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT manifest FROM connector_schemas
                   WHERE tenant_id=%s AND source=%s AND model_name=%s
                     AND enabled=TRUE""",
                (tenant_id, source, model),
            )
            row = cur.fetchone()
            if not row:
                return (False, f"manifest absent pour {source}/{model}")
            manifest = row[0]

        # Dispatch par source (pour l instant uniquement Odoo, a etendre pour
        # Drive/Outlook/Gmail dans la Phase C de la roadmap)
        if source != "odoo":
            return (False, f"source {source} pas encore supportee par le worker")

        from app.scanner.adapter_odoo import fetch_record_with_transversals
        from app.scanner.processor import process_record

        # Construit la liste des champs : metadata + vectorize + ids relations
        fields = set(["id", "display_name", "name", "write_date"])
        fields.update(manifest.get("metadata_fields") or [])
        fields.update(manifest.get("vectorize_fields") or [])
        for e in (manifest.get("graph_edges") or []):
            f = e.get("field")
            if f: fields.add(f)
        fields = sorted(fields)


        # Re-fetch : 1 record + ses transversaux
        bundle = fetch_record_with_transversals(model, rid, fields)
        record = bundle.get("record")
        if not record:
            # Record introuvable cote Odoo = probablement supprime entre temps
            # On traite comme un soft delete
            logger.info("[WebhookQueue] %s/%s #%s introuvable, soft delete",
                        source, model, rid)
            with get_pg_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """UPDATE odoo_semantic_content SET deleted_at=NOW()
                       WHERE tenant_id=%s AND source_model=%s AND source_record_id=%s
                         AND deleted_at IS NULL""",
                    (tenant_id, model, str(rid)),
                )
                cur.execute(
                    """UPDATE semantic_graph_nodes SET deleted_at=NOW()
                       WHERE tenant_id=%s AND source=%s AND source_record_id=%s
                         AND deleted_at IS NULL""",
                    (tenant_id, source, str(rid)),
                )
                conn.commit()
            return (True, None)

        # Cas 'archivage' : record existe mais active=False -> soft delete
        if record.get("active") is False:
            logger.info("[WebhookQueue] %s/%s #%s archive (active=False), soft delete",
                        source, model, rid)
            with get_pg_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """UPDATE odoo_semantic_content SET deleted_at=NOW()
                       WHERE tenant_id=%s AND source_model=%s AND source_record_id=%s
                         AND deleted_at IS NULL""",
                    (tenant_id, model, str(rid)),
                )
                conn.commit()
            return (True, None)


        # Upsert classique via le scanner generique
        # (process_record fait : texte composite + embedding + noeud + aretes
        #  + chunk, avec INSERT ON CONFLICT UPDATE partout)
        _rate_limit_openai()  # blocquant si on tape trop OpenAI
        transversals = {
            "messages": bundle.get("messages") or [],
            "trackings": bundle.get("trackings") or [],
            "attachments": bundle.get("attachments") or [],
            "followers": bundle.get("followers") or [],
        }
        result = process_record(
            tenant_id=tenant_id, source=source, model_name=model,
            record=record, manifest=manifest, transversals=transversals,
        )
        if result.get("error"):
            return (False, str(result["error"])[:300])
        logger.info("[WebhookQueue] OK %s/%s #%s (chunk=%s, edges=%s)",
                    source, model, rid,
                    result.get("chunk_id"), result.get("edges_count", 0))
        return (True, None)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()[-1500:]
        logger.error("[WebhookQueue] CRASH job id=%s : %s\n%s",
                     job.get("id"), str(e)[:200], tb)
        return (False, f"{type(e).__name__}: {str(e)[:200]}")


def _worker_loop():
    """Boucle principale du worker daemon. Depile un job a la fois, le traite,
    continue. Dort WORKER_IDLE_SLEEP_MS si la queue est vide."""
    logger.info("[WebhookQueue] Worker demarre (PID=%d)", os.getpid())
    MAX_ATTEMPTS = 3
    while _worker_running.is_set():
        try:
            job = _fetch_next_job()
            if not job:
                time.sleep(WORKER_IDLE_SLEEP_MS / 1000.0)
                continue
            success, err = _process_job(job)
            if success:
                _mark_completed(job["id"], True)
            elif job["attempts"] >= MAX_ATTEMPTS:
                # Abandon definitif apres 3 tentatives
                _mark_completed(job["id"], False, err)
                logger.warning("[WebhookQueue] Abandon job id=%s apres %d tentatives : %s",
                               job["id"], job["attempts"], err)
            else:
                # On laisse completed_at=NULL, le job sera re-tente
                # apres le reset started_at (5 min)
                logger.info("[WebhookQueue] Echec job id=%s tentative %d/%d, sera re-tente",
                            job["id"], job["attempts"], MAX_ATTEMPTS)
        except Exception as e:
            # Ne laisse JAMAIS mourir le worker. On log et on recommence.
            logger.error("[WebhookQueue] Exception dans worker loop : %s", str(e)[:300])
            time.sleep(5)
    logger.info("[WebhookQueue] Worker arrete proprement")


def start_worker():
    """Demarre le worker en thread daemon. Appelee au startup main.py.
    Idempotent : appels multiples ignores si le worker tourne deja."""
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        logger.info("[WebhookQueue] Worker deja actif, skip")
        return
    _worker_running.set()
    _worker_thread = threading.Thread(
        target=_worker_loop, name="webhook-queue-worker", daemon=True,
    )
    _worker_thread.start()


def stop_worker():
    """Arrete le worker proprement. Appele au shutdown."""
    _worker_running.clear()
    logger.info("[WebhookQueue] Stop demande au worker")


def get_stats(tenant_id: Optional[str] = None) -> dict:
    """Stats pour le dashboard de monitoring. Si tenant_id=None, aggregat global.

    Enrichi le 20/04 pour la refonte dashboards neophyte-friendly :
    - Fenetre recente configurable via env RECENT_WINDOW_MINUTES (default 15)
    - Separation erreurs reelles vs erreurs fantomes (modeles desactives)
    - Regroupement par modele pour affichage compact
    """
    import os
    from app.database import get_pg_conn
    recent_min = int(os.getenv("RECENT_WINDOW_MINUTES", "15"))
    where = "WHERE tenant_id=%s" if tenant_id else ""
    params = (tenant_id,) if tenant_id else ()
    with get_pg_conn() as conn:
        cur = conn.cursor()
        # 1. Liste des modeles officiellement desactives (source=odoo)
        cur.execute(
            "SELECT model_name, reason, category FROM deactivated_models WHERE source='odoo'"
        )
        deact = {r[0]: {"reason": r[1], "category": r[2]} for r in cur.fetchall()}
        deact_models_list = list(deact.keys())

        # 2. Compteurs 24h (existants)
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS received_24h,
                COUNT(*) FILTER (WHERE completed_at > NOW() - INTERVAL '24 hours'
                                   AND last_error IS NULL) AS processed_24h,
                COUNT(*) FILTER (WHERE completed_at > NOW() - INTERVAL '24 hours'
                                   AND last_error IS NOT NULL) AS errors_24h,
                COUNT(*) FILTER (WHERE completed_at IS NULL
                                   AND scheduled_at <= NOW()) AS pending_now,
                COUNT(*) FILTER (WHERE completed_at IS NULL
                                   AND scheduled_at > NOW()) AS delayed_dedup,
                MAX(completed_at) AS last_activity
            FROM vectorization_queue {where}
        """, params)
        row = cur.fetchone()

        # 3. Compteurs fenetre recente (configurable, defaut 15 min)
        recent_where = where + (f" AND " if where else "WHERE ") + \
            f"completed_at > NOW() - INTERVAL '{recent_min} minutes'"
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE last_error IS NULL) AS processed_recent,
                COUNT(*) FILTER (WHERE last_error IS NOT NULL) AS errors_recent
            FROM vectorization_queue {recent_where}
        """, params)
        recent = cur.fetchone()

        # 4. Separation erreurs reelles vs fantomes (sur 24h)
        if deact_models_list:
            placeholders = ",".join(["%s"] * len(deact_models_list))
            phantom_where = where + (" AND " if where else "WHERE ")
            cur.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE model_name IN ({placeholders})) AS phantom_errors,
                    COUNT(*) FILTER (WHERE model_name NOT IN ({placeholders})) AS real_errors
                FROM vectorization_queue
                {phantom_where} completed_at > NOW() - INTERVAL '24 hours'
                  AND last_error IS NOT NULL
            """, (*params, *deact_models_list, *deact_models_list))
            sep = cur.fetchone()
            phantom_24h, real_24h = sep[0] or 0, sep[1] or 0
        else:
            phantom_24h, real_24h = 0, row[2] or 0

        # 5. Regroupement par modele des erreurs 24h (top 10)
        cur.execute(f"""
            SELECT model_name, COUNT(*) AS n, MAX(last_error) AS last_err
            FROM vectorization_queue
            {where} {" AND " if where else "WHERE "}
              completed_at > NOW() - INTERVAL '24 hours'
              AND last_error IS NOT NULL
            GROUP BY model_name
            ORDER BY n DESC LIMIT 10
        """, params)
        errors_by_model = [
            {"model": r[0], "count": r[1], "sample_error": (r[2] or "")[:200],
             "is_phantom": r[0] in deact,
             "reason": deact.get(r[0], {}).get("reason"),
             "category": deact.get(r[0], {}).get("category", "unknown")}
            for r in cur.fetchall()
        ]

        return {
            "received_24h": row[0] or 0,
            "processed_24h": row[1] or 0,
            "errors_24h": row[2] or 0,
            "pending_now": row[3] or 0,
            "delayed_dedup": row[4] or 0,
            "last_activity": row[5].isoformat() if row[5] else None,
            "worker_alive": _worker_thread.is_alive() if _worker_thread else False,
            "rate_limit_calls_last_min": len(_openai_calls_timestamps),
            # Nouveaux champs
            "recent_window_minutes": recent_min,
            "processed_recent": recent[0] or 0,
            "errors_recent": recent[1] or 0,
            "phantom_errors_24h": phantom_24h,
            "real_errors_24h": real_24h,
            "errors_by_model_24h": errors_by_model,
            "deactivated_models": deact,
        }
