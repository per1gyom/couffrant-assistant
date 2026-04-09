"""
Mémoire : contacts partagés par tenant.
Les contacts sont visibles par tous les utilisateurs d'une même société.
"""
import json
import re

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_FAST

DEFAULT_TENANT = 'couffrant_solar'


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
        return [{'name': r[0], 'email': r[1], 'company': r[2],
                 'summary': r[3], 'last_seen': str(r[4])}
                for r in c.fetchall()]
    finally:
        if conn: conn.close()


def get_contacts_keywords(username: str = 'guillaume', tenant_id: str = DEFAULT_TENANT) -> list:
    keywords = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT name, email FROM aria_contacts WHERE tenant_id = %s ORDER BY last_seen DESC LIMIT 50",
                  (tenant_id,))
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

    from app.memory_rules import get_rules_by_category
    for rule in get_rules_by_category('contacts_cles', username):
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
