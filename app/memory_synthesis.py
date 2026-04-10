"""
Mémoire : synthèse des sessions et résumé chaud.
Vectorisation automatique des insights et conversations.

Phase 3a :
  - rebuild_hot_summary    → model_tier="deep" (Opus)
  - synthesize_session     → model_tier="deep" (Opus) + prompt enrichi des règles existantes
    Opus compare les nouvelles règles candidates avec celles déjà en base
    pour éviter les doublons sémantiques.

Signatures canoniques utilisées ici (depuis rule_engine) :
  get_memoire_param(username, param, default, tenant_id=None)
  get_rules_by_category(username, category, tenant_id=None)
"""
import json
import re

from app.database import get_pg_conn
from app.llm_client import llm_complete, log_llm_usage
from app.rule_engine import get_rules_by_category, get_memoire_param
from app.memory_rules import save_rule

DEFAULT_TENANT = 'couffrant_solar'


def _embed(text: str):
    """Wrapper embedding avec dégradation gracieuse."""
    try:
        from app.embedding import embed
        return embed(text)
    except Exception:
        return None


def _vec_str(embedding) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(x) for x in embedding) + "]"


def get_hot_summary(username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT content FROM aria_hot_summary WHERE username = %s", (username,))
        row = c.fetchone()
        return row[0] if row else ""
    finally:
        if conn: conn.close()


def rebuild_hot_summary(username: str = 'guillaume',
                        tenant_id: str = DEFAULT_TENANT) -> str:
    """
    Reconstruit le résumé opérationnel chaud (hot_summary).
    Phase 3a : utilise model_tier="deep" (Opus) pour une meilleure synthèse.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email, display_title, category, priority, short_summary,
                   received_at, mailbox_source
            FROM mail_memory WHERE username = %s
            ORDER BY received_at DESC NULLS LAST LIMIT 30
        """, (username,))
        cols = [d[0] for d in c.description]
        mails = [dict(zip(cols, row)) for row in c.fetchall()]
        c.execute("""
            SELECT name, summary FROM aria_contacts
            WHERE tenant_id = %s ORDER BY last_seen DESC LIMIT 15
        """, (tenant_id,))
        contacts = [{'name': r[0], 'summary': r[1]} for r in c.fetchall()]
        c.execute("""
            SELECT user_input, aria_response FROM aria_memory
            WHERE username = %s ORDER BY id DESC LIMIT 8
        """, (username,))
        history = [{'q': r[0][:150], 'a': r[1][:200]} for r in c.fetchall()]
    finally:
        if conn: conn.close()

    display_name = username.capitalize()
    prompt = f"""Tu es l'assistant de {display_name}.

Mails récents :
{json.dumps(mails, ensure_ascii=False, default=str)}

Contacts actifs :
{json.dumps(contacts, ensure_ascii=False)}

Dernières conversations :
{json.dumps(history, ensure_ascii=False)}

Génère un résumé opérationnel compact (~350 mots) :
1. SITUATION ACTUELLE — Ce qui est en cours, urgent, en attente
2. INTERLOCUTEURS CLÉS — Les personnes/entités actives
3. POINTS D'ATTENTION — Ce qui risque de déraper

Factuel, direct, sans blabla."""

    result = llm_complete(
        messages=[{"role": "user", "content": prompt}],
        model_tier="deep",   # Opus — meilleure synthèse contextuelle
        max_tokens=800,
    )
    summary = result["text"]
    log_llm_usage(result, username=username, tenant_id=tenant_id,
                  purpose="rebuild_hot_summary")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_hot_summary (username, content, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (username) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
        """, (username, summary))
        conn.commit()
    finally:
        if conn: conn.close()
    return summary


def get_aria_insights(limit: int = 8, username: str = 'guillaume',
                      tenant_id: str = None) -> str:
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


def save_insight(topic: str, insight: str, source: str = "conversation",
                 username: str = None, tenant_id: str = None) -> int:
    """
    Sauvegarde un insight avec vectorisation automatique.
    Déduplication par égalité exacte normalisée sur topic.
    username obligatoire. tenant_id optionnel (défaut couffrant_solar).
    """
    if not username:
        raise ValueError("save_insight : username obligatoire")
    if not topic or not insight:
        raise ValueError("save_insight : topic et insight obligatoires")

    topic_clean = topic.strip()
    effective_tenant = tenant_id or DEFAULT_TENANT
    embed_text = f"[{topic_clean}] {insight}"
    vec = _vec_str(_embed(embed_text))

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_insights
            WHERE username = %s AND LOWER(TRIM(topic)) = LOWER(TRIM(%s))
            LIMIT 1
        """, (username, topic_clean))
        existing = c.fetchone()
        if existing:
            if vec:
                c.execute("""
                    UPDATE aria_insights SET insight=%s,
                    reinforcements=reinforcements+1, updated_at=NOW(),
                    embedding=%s::vector WHERE id=%s
                """, (insight, vec, existing[0]))
            else:
                c.execute("""
                    UPDATE aria_insights SET insight=%s,
                    reinforcements=reinforcements+1, updated_at=NOW()
                    WHERE id=%s
                """, (insight, existing[0]))
            conn.commit()
            return existing[0]

        if vec:
            c.execute("""
                INSERT INTO aria_insights (username, tenant_id, topic, insight, source, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id
            """, (username, effective_tenant, topic_clean, insight, source, vec))
        else:
            c.execute("""
                INSERT INTO aria_insights (username, tenant_id, topic, insight, source)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (username, effective_tenant, topic_clean, insight, source))
        insight_id = c.fetchone()[0]
        conn.commit()
        return insight_id
    finally:
        if conn: conn.close()


def _load_existing_rules_summary(username: str, tenant_id: str) -> str:
    """
    Charge un résumé compact des règles existantes pour le prompt de synthèse.
    Opus peut ainsi éviter de générer des règles redondantes.
    Limité aux 40 règles les plus confiantes (hors catégorie memoire).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT category, rule FROM aria_rules
            WHERE active = true
              AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category != 'memoire'
            ORDER BY confidence DESC, reinforcements DESC
            LIMIT 40
        """, (username, tenant_id))
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n".join([f"[{r[0]}] {r[1]}" for r in rows])
    except Exception:
        return ""
    finally:
        if conn: conn.close()


def synthesize_session(n_conversations: int = 15, username: str = 'guillaume',
                       tenant_id: str = None) -> dict:
    """
    Synthèse des conversations récentes par Opus (model_tier="deep").

    Phase 3a :
      - Tier migré de "fast" vers "deep" pour une meilleure extraction de règles
      - Prompt enrichi des règles existantes → Opus évite les doublons sémantiques
      - log_llm_usage() pour suivi des coûts
    """
    effective_tenant = tenant_id or DEFAULT_TENANT
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, user_input, aria_response, created_at FROM aria_memory
            WHERE username = %s ORDER BY id DESC LIMIT %s
        """, (username, n_conversations))
        conversations = c.fetchall()
        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
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

    # Charge les règles existantes pour qu'Opus évite les doublons sémantiques
    existing_rules = _load_existing_rules_summary(username, effective_tenant)
    existing_rules_section = f"""
Règles déjà en mémoire (ne pas dupliquer) :
{existing_rules}
""" if existing_rules else ""

    prompt = f"""Tu es Raya, assistante de {display_name}.
Voici {len(conversations)} conversations récentes à synthétiser.
{existing_rules_section}
CONVERSATIONS :
{conv_text}

Synthétise en JSON strict (sans backticks ni markdown) :
{{"summary": "résumé opérationnel ~150 mots", "rules_learned": ["règle nouvelle ou enrichissante, PAS déjà en mémoire"], "insights": [{{"topic": "x", "text": "y"}}], "topics": ["sujet principal"]}}

Pour rules_learned : ne propose que des règles NOUVELLES ou significativement différentes de celles déjà en mémoire. Préfère la qualité à la quantité."""

    parsed = None
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",   # Opus — extraction de règles de qualité
            max_tokens=1200,
        )
        log_llm_usage(result, username=username, tenant_id=effective_tenant,
                      purpose="synthesize_session")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[synthesize_session] Erreur Opus: {e} — fallback smart")
        # Fallback Sonnet si Opus échoue (rate limit, JSON malformé...)
        try:
            result = llm_complete(
                messages=[{"role": "user", "content": prompt}],
                model_tier="smart", max_tokens=1200,
            )
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
        """, (
            username, len(conversations), parsed.get("summary", ""),
            json.dumps(parsed.get("rules_learned", []), ensure_ascii=False),
            json.dumps(parsed.get("topics", []), ensure_ascii=False),
        ))
        conn.commit()
    finally:
        if conn: conn.close()

    for rule_text in parsed.get("rules_learned", []):
        if rule_text and len(rule_text) > 10:
            save_rule("auto", rule_text, "synthesis", 0.6, username,
                      tenant_id=effective_tenant)

    for item in parsed.get("insights", []):
        if isinstance(item, dict):
            save_insight(item.get("topic", "général"), item.get("text", str(item)),
                         username=username, tenant_id=effective_tenant)
        elif isinstance(item, str) and len(item) > 10:
            save_insight("général", item, username=username,
                         tenant_id=effective_tenant)

    _vectorize_conversations_batch(conversations, username)

    conn = None
    purged = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM aria_memory WHERE username = %s AND id NOT IN (
                SELECT id FROM aria_memory WHERE username = %s ORDER BY id DESC LIMIT %s
            )
        """, (username, username, keep_recent))
        purged = c.rowcount
        conn.commit()
    finally:
        if conn: conn.close()

    return {
        "status": "ok",
        "conversations_synthesized": len(conversations),
        "rules_extracted": len(parsed.get("rules_learned", [])),
        "insights_extracted": len(parsed.get("insights", [])),
        "purged": purged,
    }


def _vectorize_conversations_batch(conversations: list, username: str):
    """Vectorise les conversations avant qu'elles soient purgées."""
    try:
        from app.embedding import embed_batch, is_available
        if not is_available(): return

        texts = [f"{r[1][:300]}\n{r[2][:300]}" for r in conversations]
        embeddings = embed_batch(texts)

        conn = get_pg_conn()
        c = conn.cursor()
        for (conv_id, _, _, _), emb in zip(conversations, embeddings):
            if emb is None: continue
            vec = "[" + ",".join(str(x) for x in emb) + "]"
            c.execute(
                "UPDATE aria_memory SET embedding=%s::vector WHERE id=%s",
                (vec, conv_id)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Embedding] Erreur vectorize_conversations: {e}")


def purge_old_mails(days: int = None, username: str = 'guillaume') -> int:
    if days is None:
        days = get_memoire_param(username, 'purge_days', 90)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM mail_memory
            WHERE username = %s AND created_at < NOW() - (%s || ' days')::INTERVAL
            AND mailbox_source IN ('outlook', 'gmail_perso')
        """, (username, str(days)))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        if conn: conn.close()
