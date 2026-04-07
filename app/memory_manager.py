"""
Gestionnaire de mémoire intelligent d'Aria — 3 couches + style

Couche 1 : aria_hot_summary — résumé chaud (~500 mots), toujours présent
Couche 2 : aria_contacts — fiches contacts, chargées à la demande
Style    : aria_style_examples — exemples de rédaction, enrichis en continu
"""

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
import json
from datetime import datetime


# ─────────────────────────────────────────
# COUCHE 1 — RÉSUMÉ CHAUD
# ─────────────────────────────────────────

def get_hot_summary() -> str:
    """Retourne le résumé chaud actuel (couche 1)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT content FROM aria_hot_summary
            ORDER BY updated_at DESC LIMIT 1
        """)
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

        # Mails récents (30 derniers)
        c.execute("""
            SELECT from_email, display_title, category, priority, short_summary,
                   received_at, mailbox_source, suggested_reply
            FROM mail_memory
            ORDER BY received_at DESC NULLS LAST
            LIMIT 30
        """)
        cols = [d[0] for d in c.description]
        mails = [dict(zip(cols, row)) for row in c.fetchall()]

        # Fiches contacts existantes
        c.execute("SELECT name, summary FROM aria_contacts ORDER BY last_seen DESC LIMIT 20")
        contacts = [{'name': r[0], 'summary': r[1]} for r in c.fetchall()]

        # Dernières conversations Aria
        c.execute("""
            SELECT user_input, aria_response FROM aria_memory
            ORDER BY id DESC LIMIT 10
        """)
        history = [{'q': r[0], 'a': r[1]} for r in c.fetchall()]
    finally:
        if conn:
            conn.close()

    prompt = f"""Tu es l'assistant de Guillaume Perrin, dirigeant de Couffrant Solar.

Voici les données disponibles :

Mails récents :
{json.dumps(mails, ensure_ascii=False, default=str)}

Fiches contacts connues :
{json.dumps(contacts, ensure_ascii=False)}

Dernières conversations :
{json.dumps(history, ensure_ascii=False)}

Génère un résumé opérationnel compact (~400 mots maximum) structuré ainsi :

1. SITUATION ACTUELLE — Ce qui est en cours, urgent, en attente de Guillaume
2. INTERLOCUTEURS CLÉS — Les 8-10 personnes/entités actives en ce moment avec leur sujet
3. POINTS D'ATTENTION — Ce qui risque de déraper si Guillaume n'agit pas
4. RÈGLES DE FONCTIONNEMENT — Ce qu'Aria a appris sur ses préférences et habitudes

Sois factuel, direct, sans blabla. Ce résumé sera lu par Aria à chaque conversation."""

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART,
        max_tokens=1000,
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
# COUCHE 2 — FICHES CONTACTS
# ─────────────────────────────────────────

def get_contact_card(name_or_email: str) -> str:
    """Retourne la fiche d'un contact si elle existe."""
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
    """Retourne toutes les fiches contacts (version courte)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, summary, last_seen
            FROM aria_contacts
            ORDER BY last_seen DESC
            LIMIT 30
        """)
        rows = c.fetchall()
        return [{'name': r[0], 'email': r[1], 'company': r[2], 'summary': r[3], 'last_seen': str(r[4])} for r in rows]
    finally:
        if conn:
            conn.close()


def rebuild_contacts() -> int:
    """Reconstruit les fiches contacts depuis les mails en base."""
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

        prompt = f"""Analyse ces échanges avec {email} et crée une fiche contact structurée :

Sujets traités : {subjects_text}
Extrait des mails : {preview_text[:500]}

Réponds en JSON avec ces champs :
- name : prénom et nom si détectable, sinon partie avant @ de l'email
- company : entreprise si détectable, sinon ""
- role : rôle/fonction si détectable, sinon ""
- summary : résumé en 2-3 lignes (qui c'est, sujet en cours, point d'attention)"""

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL_FAST,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            try:
                import re, json as _json
                raw_clean = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
                raw_clean = re.sub(r'\s*```$', '', raw_clean, flags=re.MULTILINE).strip()
                parsed = _json.loads(raw_clean)
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
                    INSERT INTO aria_contacts (email, name, company, role, summary, last_seen, last_subject, mail_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (email) DO UPDATE SET
                        name = EXCLUDED.name,
                        company = EXCLUDED.company,
                        role = EXCLUDED.role,
                        summary = EXCLUDED.summary,
                        last_seen = EXCLUDED.last_seen,
                        last_subject = EXCLUDED.last_subject,
                        mail_count = EXCLUDED.mail_count,
                        updated_at = NOW()
                """, (
                    email, name, company, role, summary,
                    str(last_seen), (subjects or [''])[0], mail_count
                ))
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
# STYLE — EXEMPLES DE RÉDACTION
# ─────────────────────────────────────────

def get_style_examples(context: str = "") -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if context:
            c.execute("""
                SELECT situation, example_text, quality_score
                FROM aria_style_examples
                WHERE situation ILIKE %s OR tags ILIKE %s
                ORDER BY quality_score DESC, used_count DESC
                LIMIT 5
            """, (f'%{context}%', f'%{context}%'))
        else:
            c.execute("""
                SELECT situation, example_text, quality_score
                FROM aria_style_examples
                ORDER BY quality_score DESC, used_count DESC
                LIMIT 8
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
    prompt = f"""En 5 mots maximum, décris la situation de ce mail envoyé par Guillaume :
Contenu : {corrected[:200]}
Situation : """
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
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
            SELECT subject, to_email, body_preview
            FROM sent_mail_memory
            WHERE body_preview IS NOT NULL AND length(body_preview) > 30
            ORDER BY sent_at DESC
            LIMIT %s
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
# PURGE MÉMOIRE
# ─────────────────────────────────────────

def purge_old_mails(days: int = 90) -> int:
    """Supprime les mails bruts de plus de N jours de la base."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Syntaxe correcte pour psycopg2 avec INTERVAL dynamique
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
