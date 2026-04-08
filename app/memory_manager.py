"""
Gestionnaire de mémoire intelligent d'Aria — 3 niveaux

Niveau 1 (contexte immédiat, injecté à chaque réponse) :
  - aria_hot_summary  : résumé opérationnel courant
  - aria_contacts     : fiches contacts actifs
  - aria_rules        : règles apprises par Aria (elle-même les gère)
  - aria_insights     : insights sur Guillaume et son contexte

Niveau 2 (mémoire active, fenêtre glissante) :
  - aria_memory       : 20 conversations max, synthétisé au-delà
  - mail_memory       : 90j, purgé en continu
  - aria_style_examples : style rédactionnel

Niveau 3 (archive froide, consultable sur demande) :
  - aria_session_digests : synthèses des conversations passées
  - sent_mail_memory     : mails envoyés
  - aria_profile         : profil Guillaume
"""

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
import json
import re
from datetime import datetime


# ─────────────────────────────────────────
# NIVEAU 1 — RÉSUMÉ CHAUD
# ─────────────────────────────────────────

def get_hot_summary() -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT content FROM aria_hot_summary ORDER BY updated_at DESC LIMIT 1")
        row = c.fetchone()
        return row[0] if row else ""
    finally:
        if conn:
            conn.close()


def rebuild_hot_summary() -> str:
    """Reconstruit le résumé chaud depuis les données disponibles."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        c.execute("""
            SELECT from_email, display_title, category, priority, short_summary,
                   received_at, mailbox_source
            FROM mail_memory ORDER BY received_at DESC NULLS LAST LIMIT 30
        """)
        cols = [d[0] for d in c.description]
        mails = [dict(zip(cols, row)) for row in c.fetchall()]

        c.execute("SELECT name, summary FROM aria_contacts ORDER BY last_seen DESC LIMIT 15")
        contacts = [{'name': r[0], 'summary': r[1]} for r in c.fetchall()]

        c.execute("""
            SELECT user_input, aria_response FROM aria_memory ORDER BY id DESC LIMIT 8
        """)
        history = [{'q': r[0][:150], 'a': r[1][:200]} for r in c.fetchall()]
    finally:
        if conn:
            conn.close()

    prompt = f"""Tu es l'assistant de Guillaume Perrin, Couffrant Solar.

Mails récents :
{json.dumps(mails, ensure_ascii=False, default=str)}

Contacts actifs :
{json.dumps(contacts, ensure_ascii=False)}

Dernières conversations :
{json.dumps(history, ensure_ascii=False)}

Génère un résumé opérationnel compact (~350 mots) :

1. SITUATION ACTUELLE — Ce qui est en cours, urgent, en attente
2. INTERLOCUTEURS CLÉS — Les 8-10 personnes/entités actives en ce moment
3. POINTS D'ATTENTION — Ce qui risque de déraper

Factuel, direct, sans blabla."""

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART, max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    summary = response.content[0].text

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_hot_summary (content, updated_at)
            VALUES (%s, NOW())
            ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
        """, (summary,))
        conn.commit()
    finally:
        if conn:
            conn.close()
    return summary


# ─────────────────────────────────────────
# NIVEAU 1 — RÈGLES APPRISES (Aria les gère elle-même)
# ─────────────────────────────────────────

def get_aria_rules() -> str:
    """Charge les règles actives d'Aria. Injecté dans chaque réponse."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 25
        """)
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows])
    finally:
        if conn:
            conn.close()


def save_rule(category: str, rule: str, source: str = "auto", confidence: float = 0.7) -> int:
    """Aria sauvegarde une règle apprise. Si similaire existe, renforce."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Vérifie si une règle très similaire existe déjà
        c.execute("""
            SELECT id FROM aria_rules
            WHERE active = true AND rule ILIKE %s
            LIMIT 1
        """, (f"%{rule[:40]}%",))
        existing = c.fetchone()
        if existing:
            c.execute("""
                UPDATE aria_rules SET
                    reinforcements = reinforcements + 1,
                    confidence = LEAST(1.0, confidence + 0.1),
                    updated_at = NOW()
                WHERE id = %s
            """, (existing[0],))
            conn.commit()
            return existing[0]
        else:
            c.execute("""
                INSERT INTO aria_rules (category, rule, source, confidence)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (category, rule, source, confidence))
            rule_id = c.fetchone()[0]
            conn.commit()
            return rule_id
    finally:
        if conn:
            conn.close()


def delete_rule(rule_id: int) -> bool:
    """Aria désactive une règle obsolète (soft delete — jamais supprimé en dur)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE aria_rules SET active = false, updated_at = NOW() WHERE id = %s",
            (rule_id,)
        )
        conn.commit()
        return c.rowcount > 0
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────
# NIVEAU 1 — INSIGHTS
# ─────────────────────────────────────────

def save_insight(topic: str, insight: str, source: str = "conversation") -> int:
    """Aria sauvegarde un insight sur Guillaume ou le contexte métier."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_insights WHERE topic ILIKE %s LIMIT 1
        """, (f"%{topic[:30]}%",))
        existing = c.fetchone()
        if existing:
            c.execute("""
                UPDATE aria_insights SET
                    insight = %s,
                    reinforcements = reinforcements + 1,
                    updated_at = NOW()
                WHERE id = %s
            """, (insight, existing[0]))
            conn.commit()
            return existing[0]
        else:
            c.execute("""
                INSERT INTO aria_insights (topic, insight, source)
                VALUES (%s, %s, %s) RETURNING id
            """, (topic, insight, source))
            insight_id = c.fetchone()[0]
            conn.commit()
            return insight_id
    finally:
        if conn:
            conn.close()


def get_aria_insights(limit: int = 8) -> str:
    """Charge les insights les plus renforcés."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT topic, insight, reinforcements
            FROM aria_insights
            ORDER BY reinforcements DESC, updated_at DESC
            LIMIT %s
        """, (limit,))
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n".join([f"[{r[0]}] {r[1]}" for r in rows])
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────
# NIVEAU 2 — SYNTHÈSE AUTO (conversations → mémoire durable)
# ─────────────────────────────────────────

def synthesize_session(n_conversations: int = 15) -> dict:
    """
    Synthétise les N dernières conversations brutes en :
    - Un digest archivé (aria_session_digests)
    - Des règles extractées (aria_rules)
    - Des insights (aria_insights)
    Puis purge les conversations synthétisées.
    Garde toujours les 5 plus récentes en brut.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, user_input, aria_response, created_at
            FROM aria_memory
            ORDER BY id DESC
            LIMIT %s
        """, (n_conversations,))
        conversations = c.fetchall()
        c.execute("SELECT COUNT(*) FROM aria_memory")
        total = c.fetchone()[0]
    finally:
        if conn:
            conn.close()

    if not conversations or total <= 5:
        return {"status": "nothing_to_synthesize", "total": total}

    conv_text = "\n\n".join([
        f"Guillaume: {r[1][:200]}\nAria: {r[2][:300]}"
        for r in reversed(conversations)
    ])

    prompt = f"""Tu es Aria, assistante de Guillaume Perrin (Couffrant Solar).
Voici tes {len(conversations)} dernières conversations avec Guillaume.

{conv_text}

Synthétise en JSON strict (sans backticks, sans texte avant/après) :
{{
  "summary": "résumé factuel ~150 mots de ce qui s'est passé",
  "rules_learned": ["règle 1", "règle 2"],  -- préférences et habitudes de Guillaume, max 5
  "insights": [{"topic": "sujet", "text": "insight"}],  -- contexte métier, max 5
  "topics": ["sujet1", "sujet2"]  -- thèmes abordés
}}"""

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Archivage du digest
        c.execute("""
            INSERT INTO aria_session_digests
                (conversation_count, summary, rules_learned, topics, session_date)
            VALUES (%s, %s, %s, %s, CURRENT_DATE)
        """, (
            len(conversations),
            parsed.get("summary", ""),
            json.dumps(parsed.get("rules_learned", []), ensure_ascii=False),
            json.dumps(parsed.get("topics", []), ensure_ascii=False),
        ))

        conn.commit()
    finally:
        if conn:
            conn.close()

    # Sauvegarde des règles apprises
    for rule_text in parsed.get("rules_learned", []):
        if rule_text and len(rule_text) > 10:
            save_rule("auto", rule_text, "synthesis", 0.6)

    # Sauvegarde des insights
    for item in parsed.get("insights", []):
        if isinstance(item, dict):
            save_insight(item.get("topic", "général"), item.get("text", str(item)))
        elif isinstance(item, str) and len(item) > 10:
            save_insight("général", item)

    # Purge les conversations synthétisées (garde les 5 plus récentes)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM aria_memory
            WHERE id NOT IN (
                SELECT id FROM aria_memory ORDER BY id DESC LIMIT 5
            )
        """)
        purged = c.rowcount
        conn.commit()
    finally:
        if conn:
            conn.close()

    return {
        "status": "ok",
        "conversations_synthesized": len(conversations),
        "rules_extracted": len(parsed.get("rules_learned", [])),
        "insights_extracted": len(parsed.get("insights", [])),
        "purged": purged,
    }


# ─────────────────────────────────────────
# NIVEAU 2 — CONTACTS
# ─────────────────────────────────────────

def get_contact_card(name_or_email: str) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, role, summary, last_seen, last_subject
            FROM aria_contacts
            WHERE name ILIKE %s OR email ILIKE %s
            LIMIT 1
        """, (f'%{name_or_email}%', f'%{name_or_email}%'))
        row = c.fetchone()
        if not row:
            return ""
        return f"""{row[0]} ({row[1]}) — {row[2]} — {row[3]}
Résumé : {row[4]}
Dernier contact : {row[5]} | Sujet : {row[6]}"""
    finally:
        if conn:
            conn.close()


def get_all_contact_cards() -> list:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, summary, last_seen
            FROM aria_contacts ORDER BY last_seen DESC LIMIT 30
        """)
        return [{'name': r[0], 'email': r[1], 'company': r[2], 'summary': r[3], 'last_seen': str(r[4])} for r in c.fetchall()]
    finally:
        if conn:
            conn.close()


def rebuild_contacts() -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email,
                   array_agg(subject ORDER BY received_at DESC) as subjects,
                   array_agg(raw_body_preview ORDER BY received_at DESC) as previews,
                   MAX(received_at) as last_seen,
                   COUNT(*) as mail_count
            FROM mail_memory
            WHERE from_email IS NOT NULL AND from_email != ''
            GROUP BY from_email
            HAVING COUNT(*) >= 2
            ORDER BY MAX(received_at) DESC
            LIMIT 50
        """)
        rows = c.fetchall()
    finally:
        if conn:
            conn.close()

    updated = 0
    for row in rows:
        email, subjects, previews, last_seen, mail_count = row
        subjects_text = ' | '.join((subjects or [])[:5])
        preview_text = ' '.join((previews or [])[:3])

        prompt = f"""Analyse ces échanges avec {email} et crée une fiche contact :

Sujets : {subjects_text}
Extrait : {preview_text[:500]}

Réponds en JSON avec : name, company, role, summary (2-3 lignes)"""

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL_FAST, max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            try:
                parsed = json.loads(raw)
                name = parsed.get("name", email.split('@')[0])
                company = parsed.get("company", "")
                role = parsed.get("role", "")
                summary = parsed.get("summary", raw)
            except Exception:
                name = email.split('@')[0]
                company = ""
                role = ""
                summary = raw

            conn = None
            try:
                conn = get_pg_conn()
                c2 = conn.cursor()
                c2.execute("""
                    INSERT INTO aria_contacts
                        (email, name, company, role, summary, last_seen, last_subject, mail_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (email) DO UPDATE SET
                        name = EXCLUDED.name, company = EXCLUDED.company,
                        role = EXCLUDED.role, summary = EXCLUDED.summary,
                        last_seen = EXCLUDED.last_seen, last_subject = EXCLUDED.last_subject,
                        mail_count = EXCLUDED.mail_count, updated_at = NOW()
                """, (email, name, company, role, summary,
                       str(last_seen), (subjects or [''])[0], mail_count))
                conn.commit()
            finally:
                if conn:
                    conn.close()
            updated += 1
        except Exception as e:
            print(f"[Contacts] Erreur {email}: {e}")
            continue

    return updated


# ─────────────────────────────────────────
# NIVEAU 2 — STYLE RÉDACTIONNEL
# ─────────────────────────────────────────

def get_style_examples(context: str = "") -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if context:
            c.execute("""
                SELECT situation, example_text FROM aria_style_examples
                WHERE situation ILIKE %s OR tags ILIKE %s
                ORDER BY quality_score DESC, used_count DESC LIMIT 5
            """, (f'%{context}%', f'%{context}%'))
        else:
            c.execute("""
                SELECT situation, example_text FROM aria_style_examples
                ORDER BY quality_score DESC, used_count DESC LIMIT 8
            """)
        rows = c.fetchall()
        if not rows:
            return ""
        return "\n\n".join([f"[{r[0]}]\n{r[1]}" for r in rows])
    finally:
        if conn:
            conn.close()


def save_style_example(situation: str, example_text: str, tags: str = "", quality_score: float = 1.0):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_style_examples (situation, example_text, tags, quality_score, source, created_at)
            VALUES (%s, %s, %s, %s, 'manual', NOW())
        """, (situation, example_text, tags, quality_score))
        conn.commit()
    finally:
        if conn:
            conn.close()


def learn_from_correction(original: str, corrected: str, context: str = ""):
    if not corrected or len(corrected) < 10:
        return
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=20,
            messages=[{"role": "user", "content": f"En 5 mots, décris la situation : {corrected[:200]}\nSituation :"}]
        )
        situation = response.content[0].text.strip()
    except Exception:
        situation = context or "réponse mail"
    save_style_example(situation=situation, example_text=corrected, tags=context, quality_score=1.5)


def load_sent_mails_to_style(limit: int = 50):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT subject, to_email, body_preview FROM sent_mail_memory
            WHERE body_preview IS NOT NULL AND length(body_preview) > 30
            ORDER BY sent_at DESC LIMIT %s
        """, (limit,))
        rows = c.fetchall()
    finally:
        if conn:
            conn.close()

    added = 0
    for subject, to_email, body in rows:
        situation = f"Mail à {to_email.split('@')[0] if to_email else 'contact'} — {subject[:40] if subject else ''}"
        save_style_example(situation=situation, example_text=body, tags="sent_mail", quality_score=1.0)
        added += 1
    return added


# ─────────────────────────────────────────
# PURGE
# ─────────────────────────────────────────

def purge_old_mails(days: int = 90) -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM mail_memory
            WHERE created_at < NOW() - (%s || ' days')::INTERVAL
            AND mailbox_source IN ('outlook', 'gmail_perso')
        """, (str(days),))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        if conn:
            conn.close()
