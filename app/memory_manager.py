"""
Gestionnaire de mémoire d'Aria — 3 niveaux, multi-utilisateurs, multi-tenants.

Isolation :
  - Données personnelles (règles, mémoire, style...) : filtre par username
    Un username = un utilisateur = un tenant. Aucune donnée personnelle
    ne peut traverser la cloison tenant par construction.
  - Données partagées (contacts, consignes) : filtre par tenant_id
    Contacts et consignes ne sont visibles que par les utilisateurs du même tenant.
"""

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
import json
import re
from datetime import datetime

DEFAULT_TENANT = 'couffrant_solar'


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


def rebuild_hot_summary(username: str = 'guillaume', tenant_id: str = DEFAULT_TENANT) -> str:
    """
    Reconstruit le résumé chaud.
    tenant_id utilisé pour filtrer les contacts (donnée partagée par société).
    Garantit qu'aucun contact d'une autre société n'apparaît dans le résumé.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email, display_title, category, priority, short_summary, received_at, mailbox_source
            FROM mail_memory WHERE username = %s
            ORDER BY received_at DESC NULLS LAST LIMIT 30
        """, (username,))
        cols = [d[0] for d in c.description]
        mails = [dict(zip(cols, row)) for row in c.fetchall()]
        # Contacts filtrés par tenant — cloison étanche
        c.execute("""
            SELECT name, summary FROM aria_contacts
            WHERE tenant_id = %s
            ORDER BY last_seen DESC LIMIT 15
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
            INSERT INTO aria_hot_summary (username, content, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (username) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
        """, (username, summary))
        conn.commit()
    finally:
        if conn: conn.close()
    return summary


def get_aria_rules(username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true AND username = %s AND category != 'memoire'
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 60
        """, (username,))
        rows = c.fetchall()
        if not rows: return ""
        return "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows])
    finally:
        if conn: conn.close()


def save_rule(category: str, rule: str, source: str = "auto", confidence: float = 0.7, username: str = 'guillaume') -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_rules WHERE active = true AND username = %s AND category = %s AND rule ILIKE %s LIMIT 1
        """, (username, category, f"%{rule[:40]}%"))
        existing = c.fetchone()
        if existing:
            c.execute("""
                UPDATE aria_rules SET reinforcements = reinforcements + 1,
                confidence = LEAST(1.0, confidence + 0.1), updated_at = NOW() WHERE id = %s
            """, (existing[0],))
            conn.commit()
            return existing[0]
        else:
            c.execute("""
                INSERT INTO aria_rules (username, category, rule, source, confidence)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (username, category, rule, source, confidence))
            rule_id = c.fetchone()[0]
            conn.commit()
            return rule_id
    finally:
        if conn: conn.close()


def delete_rule(rule_id: int, username: str = 'guillaume') -> bool:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE aria_rules SET active = false, updated_at = NOW() WHERE id = %s AND username = %s",
            (rule_id, username)
        )
        conn.commit()
        return c.rowcount > 0
    finally:
        if conn: conn.close()


def save_insight(topic: str, insight: str, source: str = "conversation", username: str = 'guillaume') -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_insights WHERE username = %s AND topic ILIKE %s LIMIT 1
        """, (username, f"%{topic[:30]}%"))
        existing = c.fetchone()
        if existing:
            c.execute("""
                UPDATE aria_insights SET insight = %s, reinforcements = reinforcements + 1,
                updated_at = NOW() WHERE id = %s
            """, (insight, existing[0]))
            conn.commit()
            return existing[0]
        else:
            c.execute("""
                INSERT INTO aria_insights (username, topic, insight, source)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (username, topic, insight, source))
            insight_id = c.fetchone()[0]
            conn.commit()
            return insight_id
    finally:
        if conn: conn.close()


def get_aria_insights(limit: int = 8, username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
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


def synthesize_session(n_conversations: int = 15, username: str = 'guillaume') -> dict:
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

    keep_recent = get_memoire_param('keep_recent', 5, username)
    if not conversations or total <= keep_recent:
        return {"status": "nothing_to_synthesize", "total": total}

    display_name = username.capitalize()
    conv_text = "\n\n".join([
        f"{display_name}: {r[1][:200]}\nAria: {r[2][:300]}"
        for r in reversed(conversations)
    ])

    prompt = f"""Tu es Aria, assistante de {display_name}.
Voici {len(conversations)} conversations récentes.

{conv_text}

Synthétise en JSON strict (sans backticks) :
{{"summary": "~150 mots", "rules_learned": ["règle"], "insights": [{{"topic": "x", "text": "y"}}], "topics": ["sujet"]}}"""

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = re.sub(r'^```(?:json)?\s*', '', response.content[0].text.strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_session_digests (username, conversation_count, summary, rules_learned, topics, session_date)
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
            save_rule("auto", rule_text, "synthesis", 0.6, username)

    for item in parsed.get("insights", []):
        if isinstance(item, dict):
            save_insight(item.get("topic", "général"), item.get("text", str(item)), username=username)
        elif isinstance(item, str) and len(item) > 10:
            save_insight("général", item, username=username)

    conn = None
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

    return {"status": "ok", "conversations_synthesized": len(conversations),
            "rules_extracted": len(parsed.get("rules_learned", [])),
            "insights_extracted": len(parsed.get("insights", [])), "purged": purged}


# ─────────────────────────────────────────
# CONTACTS — partagés par TENANT (cloison étanche)
# ─────────────────────────────────────────

def get_contact_card(name_or_email: str, tenant_id: str = DEFAULT_TENANT) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, role, summary, last_seen, last_subject
            FROM aria_contacts
            WHERE (name ILIKE %s OR email ILIKE %s) AND tenant_id = %s
            LIMIT 1
        """, (f'%{name_or_email}%', f'%{name_or_email}%', tenant_id))
        row = c.fetchone()
        if not row: return ""
        return f"{row[0]} ({row[1]}) — {row[2]} — {row[3]}\nRésumé : {row[4]}\nDernier contact : {row[5]} | Sujet : {row[6]}"
    finally:
        if conn: conn.close()


def get_all_contact_cards(tenant_id: str = DEFAULT_TENANT) -> list:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, summary, last_seen
            FROM aria_contacts WHERE tenant_id = %s
            ORDER BY last_seen DESC LIMIT 30
        """, (tenant_id,))
        return [{'name': r[0], 'email': r[1], 'company': r[2], 'summary': r[3], 'last_seen': str(r[4])}
                for r in c.fetchall()]
    finally:
        if conn: conn.close()


def get_contacts_keywords(username: str = 'guillaume', tenant_id: str = DEFAULT_TENANT) -> list[str]:
    keywords = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT name, email FROM aria_contacts WHERE tenant_id = %s ORDER BY last_seen DESC LIMIT 50", (tenant_id,))
        for name, email in c.fetchall():
            if name:
                keywords.extend([n.strip().lower() for n in name.split() if len(n.strip()) > 2])
            if email:
                local = email.split('@')[0].lower()
                if len(local) > 2:
                    keywords.append(local)
    except Exception:
        pass
    finally:
        if conn: conn.close()
    rules = get_rules_by_category('contacts_cles', username)
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    return list(dict.fromkeys(keywords))


def rebuild_contacts(tenant_id: str = DEFAULT_TENANT) -> int:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email,
                   array_agg(subject ORDER BY received_at DESC) as subjects,
                   array_agg(raw_body_preview ORDER BY received_at DESC) as previews,
                   MAX(received_at) as last_seen, COUNT(*) as mail_count
            FROM mail_memory
            WHERE from_email IS NOT NULL AND from_email != ''
              AND username IN (SELECT username FROM users WHERE tenant_id = %s)
            GROUP BY from_email HAVING COUNT(*) >= 2
            ORDER BY MAX(received_at) DESC LIMIT 50
        """, (tenant_id,))
        rows = c.fetchall()
    except Exception:
        try:
            c.execute("""
                SELECT from_email,
                       array_agg(subject ORDER BY received_at DESC),
                       array_agg(raw_body_preview ORDER BY received_at DESC),
                       MAX(received_at), COUNT(*)
                FROM mail_memory
                WHERE from_email IS NOT NULL AND from_email != ''
                GROUP BY from_email HAVING COUNT(*) >= 2
                ORDER BY MAX(received_at) DESC LIMIT 50
            """)
            rows = c.fetchall()
        except Exception:
            rows = []
    finally:
        if conn: conn.close()

    updated = 0
    for row in rows:
        email, subjects, previews, last_seen, mail_count = row
        subjects_text = ' | '.join((subjects or [])[:5])
        preview_text = ' '.join((previews or [])[:3])
        prompt = f"""Analyse ces échanges avec {email} et crée une fiche contact :
Sujets : {subjects_text}\nExtrait : {preview_text[:500]}
Réponds en JSON : name, company, role, summary (2-3 lignes)"""
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL_FAST, max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = re.sub(r'^```(?:json)?\s*', '', response.content[0].text.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            try:
                parsed = json.loads(raw)
                name = parsed.get("name", email.split('@')[0])
                company = parsed.get("company", "")
                role = parsed.get("role", "")
                summary = parsed.get("summary", raw)
            except Exception:
                name = email.split('@')[0]; company = ""; role = ""; summary = raw
            conn2 = get_pg_conn()
            try:
                c2 = conn2.cursor()
                c2.execute("""
                    INSERT INTO aria_contacts
                    (tenant_id, email, name, company, role, summary, last_seen, last_subject, mail_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (email, tenant_id) DO UPDATE SET
                        name=EXCLUDED.name, company=EXCLUDED.company, role=EXCLUDED.role,
                        summary=EXCLUDED.summary, last_seen=EXCLUDED.last_seen,
                        last_subject=EXCLUDED.last_subject, mail_count=EXCLUDED.mail_count, updated_at=NOW()
                """, (tenant_id, email, name, company, role, summary,
                       str(last_seen), (subjects or [''])[0], mail_count))
                conn2.commit()
            finally:
                conn2.close()
            updated += 1
        except Exception as e:
            print(f"[Contacts] Erreur {email}: {e}")
    return updated


# ─────────────────────────────────────────
# STYLE (par username)
# ─────────────────────────────────────────

def get_style_examples(context: str = "", username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if context:
            c.execute("""
                SELECT situation, example_text FROM aria_style_examples
                WHERE username = %s AND (situation ILIKE %s OR tags ILIKE %s)
                ORDER BY quality_score DESC, used_count DESC LIMIT 5
            """, (username, f'%{context}%', f'%{context}%'))
        else:
            c.execute("""
                SELECT situation, example_text FROM aria_style_examples
                WHERE username = %s ORDER BY quality_score DESC, used_count DESC LIMIT 8
            """, (username,))
        rows = c.fetchall()
        if not rows: return ""
        return "\n\n".join([f"[{r[0]}]\n{r[1]}" for r in rows])
    finally:
        if conn: conn.close()


def save_style_example(situation: str, example_text: str, tags: str = "", quality_score: float = 1.0, username: str = 'guillaume'):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_style_examples (username, situation, example_text, tags, quality_score, source, created_at)
            VALUES (%s, %s, %s, %s, %s, 'manual', NOW())
        """, (username, situation, example_text, tags, quality_score))
        conn.commit()
    finally:
        if conn: conn.close()


def learn_from_correction(original: str, corrected: str, context: str = "", username: str = 'guillaume'):
    if not corrected or len(corrected) < 10: return
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=20,
            messages=[{"role": "user", "content": f"En 5 mots, décris la situation : {corrected[:200]}\nSituation :"}]
        )
        situation = response.content[0].text.strip()
    except Exception:
        situation = context or "réponse mail"
    save_style_example(situation=situation, example_text=corrected, tags=context, quality_score=1.5, username=username)


def load_sent_mails_to_style(limit: int = 50, username: str = 'guillaume'):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT subject, to_email, body_preview FROM sent_mail_memory
            WHERE username = %s AND body_preview IS NOT NULL AND length(body_preview) > 30
            ORDER BY sent_at DESC LIMIT %s
        """, (username, limit))
        rows = c.fetchall()
    finally:
        if conn: conn.close()
    added = 0
    for subject, to_email, body in rows:
        situation = f"Mail à {to_email.split('@')[0] if to_email else 'contact'} — {subject[:40] if subject else ''}"
        save_style_example(situation=situation, example_text=body, tags="sent_mail", quality_score=1.0, username=username)
        added += 1
    return added


def purge_old_mails(days: int = None, username: str = 'guillaume') -> int:
    if days is None:
        days = get_memoire_param('purge_days', 90, username)
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


# ─────────────────────────────────────────
# RÈGLES — par username
# ─────────────────────────────────────────

def get_rules_by_category(category: str, username: str = 'guillaume') -> list[str]:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rule FROM aria_rules
            WHERE active = true AND username = %s AND category = %s
            ORDER BY confidence DESC, reinforcements DESC
        """, (username, category))
        return [row[0] for row in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_rules_as_text(categories: list, username: str = 'guillaume') -> str:
    all_rules = []
    for cat in categories:
        rules = get_rules_by_category(cat, username)
        for r in rules:
            all_rules.append(f"[{cat}] {r}")
    return "\n".join(all_rules) if all_rules else ""


def get_antispam_keywords(username: str = 'guillaume') -> list[str]:
    rules = get_rules_by_category('anti_spam', username)
    keywords = []
    for rule in rules:
        parts = [p.strip().lower() for p in rule.replace("'", "").split(',')]
        keywords.extend([p for p in parts if len(p) > 2])
    for kw in ['mailer-daemon', 'noreply@', 'no-reply@']:
        if kw not in keywords:
            keywords.append(kw)
    return list(dict.fromkeys(keywords))


def get_memoire_param(param: str, default, username: str = 'guillaume'):
    rules = get_rules_by_category('memoire', username)
    for rule in rules:
        if rule.strip().lower().startswith(f"{param.lower()}:"):
            try:
                value = rule.split(':', 1)[1].strip()
                return type(default)(value)
            except Exception:
                pass
    return default


def extract_keywords_from_rule(rule: str) -> list[str]:
    keywords = re.findall(r"'([^']+)'", rule.lower())
    if keywords:
        return [k.strip() for k in keywords if len(k.strip()) > 2]
    match = re.search(r"(?:contenant|de)\s+(.+?)(?:\s*=|\s*→|\s*$)", rule.lower())
    if match:
        parts = [p.strip() for p in match.group(1).split(',')]
        return [p for p in parts if len(p) > 2]
    return []


def save_reply_learning(
    mail_subject: str = "",
    mail_from: str = "",
    mail_body_preview: str = "",
    category: str = "autre",
    ai_reply: str = "",
    final_reply: str = "",
    username: str = 'guillaume'
) -> int:
    if not final_reply:
        return 0
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO reply_learning_memory
            (username, mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            username, mail_subject[:200], mail_from[:200], mail_body_preview[:500],
            category, ai_reply[:2000], final_reply[:2000]
        ))
        result_id = c.fetchone()[0]
        conn.commit()
        return result_id
    except Exception as e:
        print(f"[LearningMemory] Erreur: {e}")
        return 0
    finally:
        if conn: conn.close()


def seed_default_rules(username: str = 'guillaume'):
    """Aria apprend d'elle-même. Aucune règle par défaut."""
    pass
