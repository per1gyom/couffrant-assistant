"""
Mémoire : style rédactionnel par utilisateur.
"""
from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_FAST


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


def save_style_example(situation: str, example_text: str, tags: str = "",
                       quality_score: float = 1.0, username: str = 'guillaume'):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_style_examples
            (username, situation, example_text, tags, quality_score, source, created_at)
            VALUES (%s, %s, %s, %s, %s, 'manual', NOW())
        """, (username, situation, example_text, tags, quality_score))
        conn.commit()
    finally:
        if conn: conn.close()


def learn_from_correction(original: str, corrected: str,
                          context: str = "", username: str = None):
    """
    Stocke un exemple de style UNIQUEMENT s'il y a eu une vraie correction
    (Guillaume édite la réponse de Raya avant l'envoi).

    Une réponse envoyée telle quelle n'est PAS une correction et ne doit pas être
    stockée comme exemple — sinon le few-shot devient "ce qu'on a déjà envoyé"
    au lieu de "ce qu'on a corrigé", et le coût Haiku est gaspillé à chaque envoi.
    """
    if not username:
        raise ValueError("learn_from_correction : username obligatoire")
    # Pas une vraie correction : original absent (envoi direct sans édition)
    if not original or not original.strip():
        return
    if not corrected or len(corrected) < 10:
        return
    # Pas une vraie correction : texte identique
    if original.strip() == corrected.strip():
        return

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=20,
            messages=[{"role": "user", "content": f"En 5 mots, décris la situation : {corrected[:200]}\nSituation :"}]
        )
        situation = response.content[0].text.strip()
    except Exception:
        situation = context or "réponse mail"
    save_style_example(situation=situation, example_text=corrected,
                       tags=context, quality_score=1.5, username=username)


def load_sent_mails_to_style(limit: int = 50, username: str = 'guillaume') -> int:
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
        save_style_example(situation=situation, example_text=body,
                           tags="sent_mail", quality_score=1.0, username=username)
        added += 1
    return added


def save_reply_learning(
    mail_subject: str = "", mail_from: str = "", mail_body_preview: str = "",
    category: str = "autre", ai_reply: str = "", final_reply: str = "",
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
