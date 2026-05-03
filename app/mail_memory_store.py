import json
from datetime import datetime
from app.database import get_pg_conn


def init_mail_db():
    from app.database import init_postgres
    init_postgres()


def _resolve_tenant_id(username: str) -> str | None:
    """Helper : resout le tenant_id d un username via users.
    Utilise comme fallback dans insert_mail() quand tenant_id n est pas
    fourni explicitement, pour eviter d inserer des mails avec tenant_id NULL.
    """
    if not username:
        return None
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT tenant_id FROM users WHERE username=%s LIMIT 1",
                  (username,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        if conn: conn.close()


def mail_exists(message_id: str, username: str = None,
                tenant_id: str = None) -> bool:
    """Verifie si un mail (message_id, username) existe deja en base.

    FIX BUG DOUBLONS 01/05/2026 (Etape 3.4 polling delta) :
    ─────────────────────────────────────────────────────────
    L ancienne logique etait :
      WHERE message_id=%s AND username=%s AND (tenant_id=%s OR tenant_id IS NULL)

    Probleme : si on appelle avec tenant_id=None (cas du polling delta qui
    appelle process_incoming_mail qui appelle mail_exists sans tenant_id),
    la condition devient (tenant_id = NULL OR tenant_id IS NULL).

    Or `tenant_id = NULL` retourne TOUJOURS unknown en SQL (jamais vrai).
    Donc le filtre se reduit a `tenant_id IS NULL`, ce qui ne match QUE les
    mails qui ont tenant_id NULL en base. Les mails existants avec
    tenant_id rempli (ex: 'couffrant_solar') NE matchent PAS, donc
    mail_exists retourne False et on re-insere -> doublon.

    Nouvelle logique : si tenant_id n est pas specifie a l appel, on
    n applique aucun filtre dessus (match juste sur message_id + username).
    Si tenant_id est fourni, on garde l ancien comportement pour la
    compatibilite multi-tenant.
    """
    conn = get_pg_conn()
    c = conn.cursor()
    if tenant_id is None:
        c.execute(
            "SELECT 1 FROM mail_memory WHERE message_id = %s AND username = %s",
            (message_id, username))
    else:
        c.execute(
            "SELECT 1 FROM mail_memory WHERE message_id = %s AND username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (message_id, username, tenant_id))
    result = c.fetchone()
    conn.close()
    return result is not None


def insert_mail(data: dict):
    """
    Insère un mail en base.
    Génère automatiquement un vecteur sémantique si OPENAI_API_KEY est configuré.
    Le texte vectorisé est : sujet + résumé + aperçu corps.

    FIX BUG TENANT_ID NULL 01/05/2026 (Etape 3.4 polling delta) :
    ─────────────────────────────────────────────────────────────
    Les mails inseres par le polling delta avaient tenant_id=NULL en base.
    Cause : insert_mail() ne lisait PAS tenant_id du dict 'data' et ne
    l incluait pas dans le INSERT (la colonne etait remplie ulterieurement
    par la migration backfill au demarrage de l app).

    Effet de bord : entre 2 redemarrages, les mails inseres ont tenant_id
    NULL, ce qui empeche mail_exists() de les reconnaitre dans certains
    contextes -> doublons.

    Fix : on lit data.get("tenant_id"), avec fallback sur _resolve_tenant_id
    via la table users si non fourni. La colonne est ainsi toujours
    correctement remplie a l insertion.
    """
    # Texte à vectoriser : ce qui représente le mieux le contenu du mail
    subject = data.get("subject") or ""
    summary = data.get("short_summary") or ""
    preview = data.get("raw_body_preview") or ""
    from_email = data.get("from_email") or ""
    embed_text = f"De : {from_email}\nSujet : {subject}\n{summary}\n{preview}".strip()

    embedding = None
    try:
        from app.embedding import embed
        embedding = embed(embed_text)
    except Exception:
        pass

    # Resolution du tenant_id : explicite dans data, sinon via users
    username = data.get("username", "guillaume")
    tenant_id = data.get("tenant_id")
    if not tenant_id:
        tenant_id = _resolve_tenant_id(username)

    conn = get_pg_conn()
    c = conn.cursor()

    if embedding is not None:
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        c.execute("""
            INSERT INTO mail_memory (
                username, message_id, thread_id, received_at, from_email, subject,
                display_title, category, priority, reason, suggested_action,
                short_summary, references_json, group_hints_json, confidence,
                needs_review, raw_body_preview, analysis_status, created_at,
                needs_reply, reply_urgency, reply_reason, suggested_reply_subject,
                suggested_reply, response_type, missing_fields, confidence_level,
                mailbox_source, tenant_id, mailbox_email, connection_id, embedding
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s::vector
            ) ON CONFLICT DO NOTHING
        """, (
            username, data["message_id"],
            data.get("thread_id"), data.get("received_at"),
            data.get("from_email"), data.get("subject"),
            data.get("display_title"), data.get("category"),
            data.get("priority"), data.get("reason"),
            data.get("suggested_action"), data.get("short_summary"),
            json.dumps(data.get("references", [])),
            json.dumps(data.get("group_hints", [])),
            data.get("confidence", 0.0),
            int(data.get("needs_review", False)),
            data.get("raw_body_preview"),
            data.get("analysis_status", "pending"),
            datetime.utcnow().isoformat(),
            int(data.get("needs_reply", False)),
            data.get("reply_urgency"), data.get("reply_reason"),
            data.get("suggested_reply_subject"), data.get("suggested_reply"),
            data.get("response_type"),
            json.dumps(data.get("missing_fields", [])),
            data.get("confidence_level"),
            data.get("mailbox_source", "outlook"),
            tenant_id,
            data.get("mailbox_email"),
            data.get("connection_id"),
            vec_str,
        ))
    else:
        c.execute("""
            INSERT INTO mail_memory (
                username, message_id, thread_id, received_at, from_email, subject,
                display_title, category, priority, reason, suggested_action,
                short_summary, references_json, group_hints_json, confidence,
                needs_review, raw_body_preview, analysis_status, created_at,
                needs_reply, reply_urgency, reply_reason, suggested_reply_subject,
                suggested_reply, response_type, missing_fields, confidence_level,
                mailbox_source, tenant_id, mailbox_email, connection_id
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s
            ) ON CONFLICT DO NOTHING
        """, (
            username, data["message_id"],
            data.get("thread_id"), data.get("received_at"),
            data.get("from_email"), data.get("subject"),
            data.get("display_title"), data.get("category"),
            data.get("priority"), data.get("reason"),
            data.get("suggested_action"), data.get("short_summary"),
            json.dumps(data.get("references", [])),
            json.dumps(data.get("group_hints", [])),
            data.get("confidence", 0.0),
            int(data.get("needs_review", False)),
            data.get("raw_body_preview"),
            data.get("analysis_status", "pending"),
            datetime.utcnow().isoformat(),
            int(data.get("needs_reply", False)),
            data.get("reply_urgency"), data.get("reply_reason"),
            data.get("suggested_reply_subject"), data.get("suggested_reply"),
            data.get("response_type"),
            json.dumps(data.get("missing_fields", [])),
            data.get("confidence_level"),
            data.get("mailbox_source", "outlook"),
            tenant_id,
            data.get("mailbox_email"),
            data.get("connection_id"),
        ))

    conn.commit()
    conn.close()
