"""
Moteur d'optimisation hebdomadaire des règles — Rules V2 (25 avril 2026).

VISION UTILISATEUR (Guillaume 25/04) :
- Fusion automatique des doublons : invisible, zéro friction
- Contradictions claires : Opus tranche seul (garde la plus récente)
- Contradictions ambiguës : question en attente pour la prochaine session chat
- Oubli doux : règles non utilisées depuis 60j dégradées progressivement
- Aucun message dans le chat après optimisation (résultats dans panel admin)

Planification : chaque dimanche 03h00 (via scheduler_jobs.py).
Peut aussi être lancé manuellement avec dry_run=True pour preview.

Couches d'optimisation :
  A. FUSION AUTOMATIQUE : doublons (cosine >= 0.93 OU texte normalisé identique)
  B. CONTRADICTIONS OPUS : détection intelligente via LLM
  C. OUBLI DOUX : règles inactives depuis 60j → confidence -= 0.1
  D. JOURNAL : log complet dans rules_optimization_log
"""
import json
import time
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")

# Constantes
SIMILARITY_THRESHOLD = 0.93      # Même seuil qu'à l'ingestion
CONFIDENCE_BONUS_ON_MERGE = 0.03
OUBLI_DOUX_DAYS = 60
OUBLI_DOUX_DEGRADATION = 0.1
OUBLI_DOUX_MIN_CONFIDENCE = 0.10
OPUS_MAX_RULES = 80              # Limite tokens pour Opus


# ===== COUCHE A : FUSION AUTOMATIQUE DES DOUBLONS =========================

def _find_merge_candidates(username: str, tenant_id: str, threshold: float) -> list:
    """
    Trouve les paires de règles similaires (cosine >= threshold) pour un user+tenant.

    Filtre :
      - Les deux règles actives
      - Même username + tenant_id (isolation stricte)
      - Catégories compatibles (identiques OU l'une est 'auto')
      - Les deux ont un embedding

    Retourne liste de tuples :
      (id1, id2, cat1, cat2, rule1, rule2, conf1, conf2,
       reinf1, reinf2, src1, src2, similarity)
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT
              r1.id, r2.id,
              r1.category, r2.category,
              r1.rule, r2.rule,
              r1.confidence, r2.confidence,
              r1.reinforcements, r2.reinforcements,
              r1.source, r2.source,
              (1 - (r1.embedding <=> r2.embedding)) AS similarity
            FROM aria_rules r1
            JOIN aria_rules r2 ON r1.id < r2.id
              AND r1.username = r2.username
              AND r1.tenant_id = r2.tenant_id
            WHERE r1.username = %s
              AND r1.tenant_id = %s
              AND r1.active = true AND r2.active = true
              AND r1.embedding IS NOT NULL AND r2.embedding IS NOT NULL
              AND r1.level != 'immuable' AND r2.level != 'immuable'
              AND (1 - (r1.embedding <=> r2.embedding)) >= %s
              AND (r1.category = r2.category
                   OR r1.category = 'auto' OR r2.category = 'auto')
            ORDER BY similarity DESC
        """, (username, tenant_id, threshold))
        return c.fetchall()
    finally:
        if conn: conn.close()


def _pick_winner(pair: tuple) -> tuple:
    """
    Choisit le winner d'une paire selon priorité :
      1. Confidence la plus élevée
      2. Reinforcements les plus élevés
      3. Règle la plus longue (plus détaillée)
      4. ID le plus petit (arbitrage stable)

    Retourne (winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, category).
    Pour la catégorie : spécifique > 'auto'.
    """
    (id1, id2, cat1, cat2, rule1, rule2,
     conf1, conf2, reinf1, reinf2, _src1, _src2, _sim) = pair

    if conf1 != conf2:
        winner_is_1 = conf1 > conf2
    elif reinf1 != reinf2:
        winner_is_1 = reinf1 > reinf2
    elif len(rule1 or "") != len(rule2 or ""):
        winner_is_1 = len(rule1 or "") > len(rule2 or "")
    else:
        winner_is_1 = id1 < id2

    if winner_is_1:
        winner_id, loser_id = id1, id2
        w_conf, l_conf = conf1, conf2
        w_reinf, l_reinf = reinf1, reinf2
    else:
        winner_id, loser_id = id2, id1
        w_conf, l_conf = conf2, conf1
        w_reinf, l_reinf = reinf2, reinf1

    if cat1 == 'auto' and cat2 != 'auto':
        category = cat2
    elif cat2 == 'auto' and cat1 != 'auto':
        category = cat1
    else:
        category = cat1

    return winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, category


def _apply_merge(winner_id: int, loser_id: int, w_conf: float, l_conf: float,
                 w_reinf: int, l_reinf: int, category: str, dry_run: bool) -> bool:
    """
    Effectue la fusion :
    - Snapshot des 2 règles dans aria_rules_history
    - Winner : confidence += bonus, reinforcements += loser's
    - Loser : active=false, source='merged_into_<winner_id>'
    Retourne True si fusion effective.
    """
    if dry_run:
        return True
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Snapshot avant
        c.execute("""
            INSERT INTO aria_rules_history
              (rule_id, username, tenant_id, category, rule,
               confidence, reinforcements, active, change_type)
            SELECT id, username, tenant_id, category, rule,
                   confidence, reinforcements, active, 'merged_optimizer'
            FROM aria_rules WHERE id IN (%s, %s)
        """, (winner_id, loser_id))
        # UPDATE winner : bonus + héritage du compteur loser
        new_conf = min(1.0, max(w_conf, l_conf) + CONFIDENCE_BONUS_ON_MERGE)
        c.execute("""
            UPDATE aria_rules
            SET confidence = %s,
                reinforcements = reinforcements + %s,
                category = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (new_conf, l_reinf, category, winner_id))
        # UPDATE loser : désactivation + traçabilité
        c.execute("""
            UPDATE aria_rules
            SET active = false,
                source = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (f'merged_into_{winner_id}', loser_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[RulesOptimizer] apply_merge erreur : {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn: conn.close()


def run_layer_a_fusion(username: str, tenant_id: str, dry_run: bool = False) -> dict:
    """
    Couche A : fusion automatique des doublons.
    Passe 1 : cosine >= 0.93
    Passe 2 : texte normalisé identique (accents + flèches)
    """
    merged_count = 0
    already_merged = set()  # Évite de fusionner deux fois dans la même passe

    # Passe 1 : cosine
    candidates = _find_merge_candidates(username, tenant_id, SIMILARITY_THRESHOLD)
    for pair in candidates:
        id1, id2 = pair[0], pair[1]
        if id1 in already_merged or id2 in already_merged:
            continue
        winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, cat = _pick_winner(pair)
        if _apply_merge(winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, cat, dry_run):
            merged_count += 1
            already_merged.add(winner_id)
            already_merged.add(loser_id)

    # Passe 2 : texte normalisé (accents/flèches)
    # Utilise la même logique que save_rule() : TRANSLATE + REGEXP_REPLACE
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            WITH norm AS (
                SELECT id, category, confidence, reinforcements, source, rule,
                  LOWER(TRIM(REGEXP_REPLACE(
                    TRANSLATE(rule, 'àâäéèêëîïôöùûüÿçÀÂÄÉÈÊËÎÏÔÖÙÛÜŸÇ',
                                    'aaaeeeeiioouuuycAAAEEEEIIOOUUUYC'),
                    '→|⇒', '->', 'g'))) as normalized
                FROM aria_rules
                WHERE username = %s AND tenant_id = %s AND active = true
                  AND level != 'immuable'
            )
            SELECT a.id, b.id, a.category, b.category, a.rule, b.rule,
                   a.confidence, b.confidence, a.reinforcements, b.reinforcements,
                   a.source, b.source, 1.0 as similarity
            FROM norm a JOIN norm b ON a.id < b.id
              AND a.normalized = b.normalized
              AND a.category = b.category
        """, (username, tenant_id))
        text_candidates = c.fetchall()
    finally:
        if conn: conn.close()

    for pair in text_candidates:
        id1, id2 = pair[0], pair[1]
        if id1 in already_merged or id2 in already_merged:
            continue
        winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, cat = _pick_winner(pair)
        if _apply_merge(winner_id, loser_id, w_conf, l_conf, w_reinf, l_reinf, cat, dry_run):
            merged_count += 1
            already_merged.add(winner_id)
            already_merged.add(loser_id)

    return {"merged_count": merged_count, "candidates_found": len(candidates) + len(text_candidates)}


# ===== COUCHE B : CONTRADICTIONS DÉTECTÉES PAR OPUS =======================

def _detect_contradictions_opus(username: str, tenant_id: str) -> dict:
    """
    Appelle Opus pour analyser les règles actives et détecter les contradictions.
    Retourne un JSON structuré avec deux types :
    - "clear" : contradictions nettes, Opus tranche (garde la plus récente)
    - "ambiguous" : contradictions possibles, à mettre en question pending
    """
    import re
    from app.llm_client import llm_complete, log_llm_usage

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements, level, created_at
            FROM aria_rules
            WHERE username = %s AND tenant_id = %s AND active = true
              AND level != 'immuable'
            ORDER BY confidence DESC, reinforcements DESC
            LIMIT %s
        """, (username, tenant_id, OPUS_MAX_RULES))
        rows = c.fetchall()
    finally:
        if conn: conn.close()

    if len(rows) < 2:
        return {"clear": [], "ambiguous": [], "tokens_used": 0}

    rules_text = "\n".join([
        f"[id:{r[0]}][{r[1]}][conf:{r[2] and r[3] or 0:.2f}] {r[2]}"
        for r in rows
    ])

    prompt = f"""Tu es l'auditeur des règles de Raya pour {username}@{tenant_id}.
Analyse ces {len(rows)} règles actives et identifie UNIQUEMENT les CONTRADICTIONS réelles.

RÈGLES :
{rules_text}

Retourne un JSON strict (sans markdown) :
{{
  "clear": [
    {{"loser_id": 12, "winner_id": 45, "reason": "Règle 45 est plus récente et contredit directement 12 sur X"}}
  ],
  "ambiguous": [
    {{"rule_ids": [12, 45], "question": "Doit-on vouvoyer ou tutoyer le client X ? Règles 12 et 45 divergent selon le contexte."}}
  ]
}}

RÈGLES D'ARBITRAGE (pour "clear") :
- Deux règles en opposition stricte (A dit X, B dit l'inverse de X)
- Garder celle avec confidence la plus élevée OU la plus récente si confidence égale
- Motiver brièvement (1 phrase)

Pour "ambiguous" : mettre les cas où tu ne sais pas trancher (contexte manquant, nuance importante, plusieurs règles concernées).

Si aucune contradiction : retourne {{"clear": [], "ambiguous": []}}."""

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",  # Opus
            max_tokens=1500,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="rules_optimizer_contradictions")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        report = json.loads(raw)
        report["tokens_used"] = result.get("usage", {}).get("total_tokens", 0)
        return report
    except Exception as e:
        logger.error(f"[RulesOptimizer] Opus contradictions erreur : {e}")
        return {"clear": [], "ambiguous": [], "tokens_used": 0, "error": str(e)}


def run_layer_b_contradictions(username: str, tenant_id: str, dry_run: bool = False) -> dict:
    """
    Couche B : détection + résolution des contradictions via Opus.
    - Cas "clear" : Opus tranche seul → loser archivé avec source='contradicted_by_<winner_id>'
    - Cas "ambiguous" : insertion dans rules_pending_decisions pour question chat
    """
    result = _detect_contradictions_opus(username, tenant_id)
    clear = result.get("clear", [])
    ambiguous = result.get("ambiguous", [])
    tokens_used = result.get("tokens_used", 0)

    resolved_count = 0
    pending_count = 0

    if not dry_run:
        conn = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()

            # Résoudre les contradictions claires
            for item in clear:
                try:
                    loser_id = int(item.get("loser_id"))
                    winner_id = int(item.get("winner_id"))
                    reason = item.get("reason", "")[:500]
                    # Snapshot
                    c.execute("""
                        INSERT INTO aria_rules_history
                          (rule_id, username, tenant_id, category, rule,
                           confidence, reinforcements, active, change_type)
                        SELECT id, username, tenant_id, category, rule,
                               confidence, reinforcements, active, 'contradicted_optimizer'
                        FROM aria_rules WHERE id = %s
                    """, (loser_id,))
                    # Archivage du loser
                    c.execute("""
                        UPDATE aria_rules
                        SET active = false,
                            source = %s,
                            updated_at = NOW()
                        WHERE id = %s AND username = %s AND tenant_id = %s
                    """, (f'contradicted_by_{winner_id}',
                          loser_id, username, tenant_id))
                    if c.rowcount > 0:
                        resolved_count += 1
                        logger.info(f"[RulesOptimizer] Contradiction résolue : {loser_id} < {winner_id} ({reason[:60]})")
                except Exception as e:
                    logger.warning(f"[RulesOptimizer] clear item erreur : {e}")

            # Enregistrer les questions ambiguës
            for item in ambiguous:
                try:
                    rule_ids = item.get("rule_ids", [])
                    if not isinstance(rule_ids, list) or len(rule_ids) < 2:
                        continue
                    rule_ids_int = [int(x) for x in rule_ids]
                    question = item.get("question", "")[:1000]
                    if not question:
                        continue
                    c.execute("""
                        INSERT INTO rules_pending_decisions
                          (username, tenant_id, decision_type, rule_ids, question_text, status)
                        VALUES (%s, %s, 'contradiction', %s, %s, 'pending')
                    """, (username, tenant_id, rule_ids_int, question))
                    pending_count += 1
                except Exception as e:
                    logger.warning(f"[RulesOptimizer] ambiguous item erreur : {e}")

            conn.commit()
        except Exception as e:
            logger.error(f"[RulesOptimizer] Layer B erreur DB : {e}")
            if conn:
                conn.rollback()
        finally:
            if conn: conn.close()
    else:
        resolved_count = len(clear)
        pending_count = len(ambiguous)

    return {
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "tokens_used": tokens_used,
        "clear_detected": len(clear),
        "ambiguous_detected": len(ambiguous),
    }


# ===== COUCHE C : OUBLI DOUX ==============================================

def run_layer_c_oubli_doux(username: str, tenant_id: str, dry_run: bool = False) -> dict:
    """
    Couche C : oubli doux des règles inutilisées depuis 60 jours.
    - Règles 'moyenne' ou 'faible' avec last_reinforced_at < NOW() - 60 days
    - confidence -= 0.1 (min 0.10)
    - Jamais de suppression
    - Les 'immuable' et 'seed' sont protégées (mais seed est moyen par défaut donc OK)
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Compter les éligibles
        c.execute(f"""
            SELECT COUNT(*) FROM aria_rules
            WHERE username = %s AND tenant_id = %s
              AND active = true
              AND level IN ('moyenne', 'faible')
              AND source NOT IN ('seed', 'feedback_negative', 'onboarding')
              AND COALESCE(last_reinforced_at, updated_at, created_at)
                  < NOW() - INTERVAL '{OUBLI_DOUX_DAYS} days'
              AND confidence > {OUBLI_DOUX_MIN_CONFIDENCE}
        """, (username, tenant_id))
        eligible = c.fetchone()[0]

        if not dry_run and eligible > 0:
            c.execute(f"""
                UPDATE aria_rules
                SET confidence = GREATEST({OUBLI_DOUX_MIN_CONFIDENCE},
                                          confidence - {OUBLI_DOUX_DEGRADATION}),
                    updated_at = NOW()
                WHERE username = %s AND tenant_id = %s
                  AND active = true
                  AND level IN ('moyenne', 'faible')
                  AND source NOT IN ('seed', 'feedback_negative', 'onboarding')
                  AND COALESCE(last_reinforced_at, updated_at, created_at)
                      < NOW() - INTERVAL '{OUBLI_DOUX_DAYS} days'
                  AND confidence > {OUBLI_DOUX_MIN_CONFIDENCE}
            """, (username, tenant_id))
            forgotten = c.rowcount
            conn.commit()
        else:
            forgotten = eligible if dry_run else 0

        return {"forgotten_count": forgotten, "eligible": eligible}
    except Exception as e:
        logger.error(f"[RulesOptimizer] Layer C erreur : {e}")
        if conn: conn.rollback()
        return {"forgotten_count": 0, "eligible": 0, "error": str(e)}
    finally:
        if conn: conn.close()


# ===== ORCHESTRATION =======================================================

def _count_active_rules(username: str, tenant_id: str) -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM aria_rules
            WHERE username = %s AND tenant_id = %s AND active = true
        """, (username, tenant_id))
        return c.fetchone()[0]
    finally:
        if conn: conn.close()


def run_for_user(username: str, tenant_id: str, dry_run: bool = False) -> dict:
    """
    Lance les 3 couches d'optimisation pour un user+tenant donné.
    Journalise le résultat dans rules_optimization_log.
    """
    start = time.time()
    rules_before = _count_active_rules(username, tenant_id)

    # Couche A : fusion doublons (gratuit, rapide)
    result_a = run_layer_a_fusion(username, tenant_id, dry_run=dry_run)

    # Couche B : contradictions Opus (payant, lent)
    result_b = run_layer_b_contradictions(username, tenant_id, dry_run=dry_run)

    # Couche C : oubli doux (gratuit)
    result_c = run_layer_c_oubli_doux(username, tenant_id, dry_run=dry_run)

    rules_after = _count_active_rules(username, tenant_id)
    duration = time.time() - start

    # Résumé textuel
    parts = []
    if result_a["merged_count"] > 0:
        parts.append(f"{result_a['merged_count']} doublons fusionnés")
    if result_b["resolved_count"] > 0:
        parts.append(f"{result_b['resolved_count']} contradictions résolues")
    if result_b["pending_count"] > 0:
        parts.append(f"{result_b['pending_count']} questions en attente")
    if result_c["forgotten_count"] > 0:
        parts.append(f"{result_c['forgotten_count']} règles dégradées (inutilisées)")
    summary = " · ".join(parts) if parts else "Aucune optimisation nécessaire"

    # Journal
    if not dry_run:
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                INSERT INTO rules_optimization_log
                  (username, tenant_id, run_type, rules_before, rules_after,
                   merged_count, contradictions_resolved, contradictions_pending,
                   forgotten_count, summary_text, details_json,
                   tokens_used, duration_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                username, tenant_id, 'weekly', rules_before, rules_after,
                result_a["merged_count"],
                result_b["resolved_count"],
                result_b["pending_count"],
                result_c["forgotten_count"],
                summary,
                json.dumps({"layer_a": result_a, "layer_b": result_b, "layer_c": result_c}),
                result_b.get("tokens_used", 0),
                round(duration, 2),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[RulesOptimizer] Journal erreur : {e}")

    logger.info(f"[RulesOptimizer] {username}@{tenant_id} : {summary} ({duration:.1f}s)")
    return {
        "username": username, "tenant_id": tenant_id,
        "rules_before": rules_before, "rules_after": rules_after,
        "layer_a": result_a, "layer_b": result_b, "layer_c": result_c,
        "summary": summary, "duration_seconds": round(duration, 2),
        "dry_run": dry_run,
    }


def run_all(dry_run: bool = False) -> list:
    """
    Lance l'optimisation pour tous les users actifs qui ont au moins 10 règles.
    Appelé par le scheduler chaque dimanche 03h00.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Users actifs avec >= 10 règles actives (sinon pas d'intérêt)
        c.execute("""
            SELECT username, tenant_id, COUNT(*) as n
            FROM aria_rules
            WHERE active = true AND tenant_id IS NOT NULL
            GROUP BY username, tenant_id
            HAVING COUNT(*) >= 10
            ORDER BY n DESC
        """)
        targets = c.fetchall()
    finally:
        if conn: conn.close()

    results = []
    for username, tenant_id, n in targets:
        try:
            res = run_for_user(username, tenant_id, dry_run=dry_run)
            results.append(res)
        except Exception as e:
            logger.error(f"[RulesOptimizer] {username}@{tenant_id} échec : {e}")
            results.append({
                "username": username, "tenant_id": tenant_id, "error": str(e)
            })
    return results


def _job_rules_optimizer():
    """Wrapper APScheduler : dimanche 03h00."""
    try:
        results = run_all(dry_run=False)
        total_merged = sum(r.get("layer_a", {}).get("merged_count", 0) for r in results)
        total_resolved = sum(r.get("layer_b", {}).get("resolved_count", 0) for r in results)
        total_pending = sum(r.get("layer_b", {}).get("pending_count", 0) for r in results)
        logger.info(
            f"[Scheduler] rules_optimizer : {len(results)} users traités, "
            f"{total_merged} fusions, {total_resolved} contradictions résolues, "
            f"{total_pending} questions en attente"
        )
    except Exception as e:
        logger.error(f"[Scheduler] rules_optimizer erreur : {e}")
