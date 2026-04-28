"""
Memoire : synthese des sessions et resume chaud.
Vectorisation automatique des insights et conversations.

Phase 3a :
  - rebuild_hot_summary    -> model_tier="deep" (Opus)
  - synthesize_session     -> model_tier="deep" (Opus) + prompt enrichi des regles existantes
    Opus compare les nouvelles regles candidates avec celles deja en base
    pour eviter les doublons semantiques.
5G-6 : rebuild_hot_summary adapte selon la phase de maturite.
8-TON : section "Ton et communication" ajoutee au hot_summary.

Signatures canoniques utilisees ici (depuis rule_engine) :
  get_memoire_param(username, param, default, tenant_id=None)
  get_rules_by_category(username, category, tenant_id=None)
"""
import json
import re

from app.database import get_pg_conn
from app.memory_save import save_insight, _load_existing_rules_summary  # noqa
from app.synthesis_engine import rebuild_hot_summary, _vectorize_conversations_batch  # noqa
from app.llm_client import llm_complete, log_llm_usage
from app.rule_engine import get_rules_by_category, get_memoire_param
from app.memory_rules import save_rule

DEFAULT_TENANT = 'couffrant_solar'


def get_hot_summary(username: str, tenant_id: str = None) -> str:
    # F.8 (audit isolation user-user, LOT 1.4) : retire le default
    # username='guillaume' (anti-pattern multi-user). Aligne sur le
    # pattern memory_rules.save_rule, token_manager, etc.
    if not username:
        raise ValueError("get_hot_summary : username obligatoire")
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT content FROM aria_hot_summary "
            "WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)",
            (username, tenant_id))
        row = c.fetchone()
        return row[0] if row else ""
    finally:
        if conn: conn.close()


def get_aria_insights(limit: int = 8, username: str = None,
                      tenant_id: str = None) -> str:
    # F.8 (audit isolation user-user, LOT 1.4) : retire le default
    # username='guillaume' (anti-pattern multi-user).
    if not username:
        raise ValueError("get_aria_insights : username obligatoire")
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute("""
                SELECT topic, insight, reinforcements FROM aria_insights
                WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY reinforcements DESC, updated_at DESC LIMIT %s
            """, (username, tenant_id, limit))
        else:
            c.execute("""
                SELECT topic, insight, reinforcements FROM aria_insights
                WHERE username = %s
                ORDER BY reinforcements DESC, updated_at DESC LIMIT %s
            """, (username, limit))
        rows = c.fetchall()
        if not rows: return ""
        return "\n".join([f"[{r[0]}] {r[1]}" for r in rows])
    finally:
        if conn: conn.close()


def synthesize_session(n_conversations: int = 15, username: str = None,
                       tenant_id: str = None) -> dict:
    """Synthese de session : compresse les anciennes conversations en
    insights puis archive les originales.

    HOTFIX 26/04 (etape A.5 part 2) : retire le default username='guillaume'
    (anti-pattern multi-tenant) et log un WARNING si tenant_id absent
    (le fallback DEFAULT_TENANT est conserve pour compat mais signale
    toute dependance silencieuse). Aligne sur le pattern token_manager.py
    et memory_rules.py."""
    if not username:
        raise ValueError("synthesize_session : username obligatoire")
    from app.logging_config import get_logger
    logger = get_logger("raya.memory")
    if tenant_id is None:
        logger.warning(
            "[synthesize_session] Appel SANS tenant_id pour user '%s' "
            "-> fallback DEFAULT_TENANT='%s'. Caller a durcir.",
            username, DEFAULT_TENANT,
        )
    effective_tenant = tenant_id or DEFAULT_TENANT
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, user_input, aria_response, created_at FROM aria_memory
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY id DESC LIMIT %s
        """, (username, effective_tenant, n_conversations))
        conversations = c.fetchall()
        c.execute(
            "SELECT COUNT(*) FROM aria_memory "
            "WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)",
            (username, effective_tenant))
        total = c.fetchone()[0]
    finally:
        if conn: conn.close()

    keep_recent = get_memoire_param(username, 'keep_recent', 5)
    if not conversations or total <= keep_recent:
        return {"status": "nothing_to_synthesize", "total": total}

    display_name = username.capitalize()
    conv_text = "\n\n".join([
        f"{display_name}: {r[1][:200]}\nRaya: {r[2][:300]}"
        for r in reversed(conversations)
    ])

    existing_rules = _load_existing_rules_summary(username, effective_tenant)
    existing_rules_section = f"""\nRegles deja en memoire (ne pas dupliquer) :\n{existing_rules}\n""" if existing_rules else ""

    prompt = f"""Tu es Raya, assistante de {display_name}.
Voici {len(conversations)} conversations recentes a synthetiser.
{existing_rules_section}
CONVERSATIONS :
{conv_text}

Synthetise en JSON strict (sans backticks ni markdown) :
{{"summary": "resume operationnel ~150 mots", "rules_learned": ["regle nouvelle ou enrichissante, PAS deja en memoire"], "insights": [{{"topic": "x", "text": "y"}}], "topics": ["sujet principal"]}}

Pour rules_learned : ne propose que des regles NOUVELLES. Prefere la qualite a la quantite."""

    parsed = None
    try:
        result = llm_complete(messages=[{"role": "user", "content": prompt}],
                              model_tier="deep", max_tokens=1200)
        log_llm_usage(result, username=username, tenant_id=effective_tenant, purpose="synthesize_session")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[synthesize_session] Erreur Opus: {e} — fallback smart")
        try:
            result = llm_complete(messages=[{"role": "user", "content": prompt}],
                                  model_tier="smart", max_tokens=1200)
            raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
        except Exception as e2:
            return {"status": "error", "message": str(e2)}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_session_digests
            (username, conversation_count, summary, rules_learned, topics, session_date)
            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
        """, (username, len(conversations), parsed.get("summary", ""),
               json.dumps(parsed.get("rules_learned", []), ensure_ascii=False),
               json.dumps(parsed.get("topics", []), ensure_ascii=False)))
        conn.commit()
    finally:
        if conn: conn.close()

    rules_learned = parsed.get("rules_learned", [])
    # Confiance initiale plus basse pour l'auto-synthèse (0.5) :
    # le mécanisme de reinforcements dans save_rule élèvera la confiance
    # si la même règle réapparaît dans de futures synthèses.
    base_confidence = 0.5
    for rule_text in rules_learned:
        if rule_text and len(rule_text) > 10:
            # Phase 3 : on passe par le validateur Sonnet pour categoriser
            # proprement au lieu de forcer category="auto" en dur.
            # Si le validateur crashe (pas d'embedding, pas de LLM), fallback
            # sur comportement historique pour ne rien perdre.
            try:
                from app.rule_validator import validate_rule_before_save, apply_validation_result
                result = validate_rule_before_save(
                    username, effective_tenant, "auto", rule_text
                )
                if result.get("decision") != "CONFLICT":
                    apply_validation_result(result, username, effective_tenant)
                # CONFLICT : on ignore silencieusement en synthese (pas d'utilisateur
                # en face pour trancher). Le dimanche soir Opus fera le menage.
            except Exception as e:
                print(f"[memory_synthesis] validator error, fallback auto: {e}")
                save_rule("auto", rule_text, "synthesis", base_confidence, username, tenant_id=effective_tenant)

    for item in parsed.get("insights", []):
        if isinstance(item, dict):
            save_insight(item.get("topic", "general"), item.get("text", str(item)),
                         username=username, tenant_id=effective_tenant)
        elif isinstance(item, str) and len(item) > 10:
            save_insight("general", item, username=username, tenant_id=effective_tenant)

    _vectorize_conversations_batch(conversations, username)

    conn = None
    purged = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Archivage doux : flag archived=true au lieu de DELETE irréversible.
        # Les conversations restent récupérables en cas d'erreur de synthèse.
        c.execute("""
            UPDATE aria_memory SET archived = true
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND id NOT IN (
                SELECT id FROM aria_memory
                WHERE username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY id DESC LIMIT %s
            ) AND (archived IS NULL OR archived = false)
        """, (username, effective_tenant, username, effective_tenant, keep_recent))
        purged = c.rowcount
        conn.commit()
    except Exception:
        # Si la colonne archived n'existe pas encore, fallback sur l'ancien DELETE
        try:
            if conn: conn.rollback()
            c.execute("""
                DELETE FROM aria_memory WHERE username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                  AND id NOT IN (
                    SELECT id FROM aria_memory WHERE username = %s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                    ORDER BY id DESC LIMIT %s
                )
            """, (username, effective_tenant, username, effective_tenant, keep_recent))
            purged = c.rowcount
            conn.commit()
        except Exception:
            pass
    finally:
        if conn: conn.close()

    return {
        "status": "ok",
        "conversations_synthesized": len(conversations),
        "rules_extracted": len(parsed.get("rules_learned", [])),
        "insights_extracted": len(parsed.get("insights", [])),
        "purged": purged,
    }


def purge_old_mails(days: int = None, username: str = None,
                    tenant_id: str = None) -> int:
    # F.8 (audit isolation user-user, LOT 1.4) : retire le default
    # username='guillaume' (anti-pattern multi-user).
    if not username:
        raise ValueError("purge_old_mails : username obligatoire")
    if days is None:
        days = get_memoire_param(username, 'purge_days', 90)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM mail_memory
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND created_at < NOW() - (%s || ' days')::INTERVAL
              AND mailbox_source IN ('outlook', 'gmail_perso')
        """, (username, tenant_id, str(days)))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        if conn: conn.close()
