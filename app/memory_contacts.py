"""
Mémoire : contacts partagés par tenant.
Vectorisation automatique au moment de l'insertion.
"""
import json
import re

from app.database import get_pg_conn
from app.llm_client import llm_complete

DEFAULT_TENANT = 'couffrant_solar'


def _embed(text: str):
    try:
        from app.embedding import embed
        return embed(text)
    except Exception:
        return None


def _vec_str(embedding) -> str | None:
    if embedding is None: return None
    return "[" + ",".join(str(x) for x in embedding) + "]"


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
            # Fallback : filtre direct sur tenant_id de mail_memory
            # (au lieu du JOIN users qui a echoue).
            # IMPORTANT : JAMAIS de requete sans filtre, risque de fuite
            # cross-tenant critique.
            c.execute("""
                SELECT from_email,
                       array_agg(subject ORDER BY received_at DESC),
                       array_agg(raw_body_preview ORDER BY received_at DESC),
                       MAX(received_at), COUNT(*)
                FROM mail_memory
                WHERE from_email IS NOT NULL AND from_email != ''
                  AND tenant_id = %s
                GROUP BY from_email HAVING COUNT(*) >= 2
                ORDER BY MAX(received_at) DESC LIMIT 50
            """, (tenant_id,))
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
            result = llm_complete(
                messages=[{"role": "user", "content": prompt}],
                model_tier="fast",
                max_tokens=200,
            )
            raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            try:
                parsed = json.loads(raw)
                name = parsed.get("name", email.split('@')[0])
                company = parsed.get("company", "")
                role = parsed.get("role", "")
                summary = parsed.get("summary", raw)
            except Exception:
                name = email.split('@')[0]; company = ""; role = ""; summary = raw

            # Vectorise la fiche contact
            embed_text = f"{name} ({email}) — {company} — {role}\n{summary}"
            vec = _vec_str(_embed(embed_text))

            conn2 = get_pg_conn()
            try:
                c2 = conn2.cursor()
                if vec:
                    c2.execute("""
                        INSERT INTO aria_contacts
                        (tenant_id, email, name, company, role, summary, last_seen,
                         last_subject, mail_count, updated_at, embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s::vector)
                        ON CONFLICT (email, tenant_id) DO UPDATE SET
                            name=EXCLUDED.name, company=EXCLUDED.company, role=EXCLUDED.role,
                            summary=EXCLUDED.summary, last_seen=EXCLUDED.last_seen,
                            last_subject=EXCLUDED.last_subject, mail_count=EXCLUDED.mail_count,
                            updated_at=NOW(), embedding=EXCLUDED.embedding
                    """, (tenant_id, email, name, company, role, summary,
                           str(last_seen), (subjects or [''])[0], mail_count, vec))
                else:
                    c2.execute("""
                        INSERT INTO aria_contacts
                        (tenant_id, email, name, company, role, summary, last_seen,
                         last_subject, mail_count, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                        ON CONFLICT (email, tenant_id) DO UPDATE SET
                            name=EXCLUDED.name, company=EXCLUDED.company, role=EXCLUDED.role,
                            summary=EXCLUDED.summary, last_seen=EXCLUDED.last_seen,
                            last_subject=EXCLUDED.last_subject, mail_count=EXCLUDED.mail_count,
                            updated_at=NOW()
                    """, (tenant_id, email, name, company, role, summary,
                           str(last_seen), (subjects or [''])[0], mail_count))
                conn2.commit()
            finally:
                conn2.close()
            updated += 1
        except Exception as e:
            print(f"[Contacts] Erreur {email}: {e}")
    return updated
