"""
Gestionnaire de mémoire d'Aria — 3 niveaux, multi-utilisateurs.

Chaque utilisateur a sa propre mémoire (rules, insights, conversations, style, résumé).
Les contacts (aria_contacts) sont partagés — contacts entreprise Couffrant Solar.

Architecture auto-évolutive :
  Tout comportement d'Aria (tri mails, urgence, spam, regroupement, style, cycles)
  est piloté par aria_rules. Aucune règle métier n'est codée en dur.
  Seuls les garde-fous de sécurité (auth, suppression définitive, envoi sans confirmation)
  restent immuables dans le code.
"""

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
import json
import re
from datetime import datetime


# ─────────────────────────────────────────
# NIVEAU 1 — RÉSUMÉ CHAUD (par utilisateur)
# ─────────────────────────────────────────

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


def rebuild_hot_summary(username: str = 'guillaume') -> str:
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

        c.execute("SELECT name, summary FROM aria_contacts ORDER BY last_seen DESC LIMIT 15")
        contacts = [{'name': r[0], 'summary': r[1]} for r in c.fetchall()]

        c.execute("""
            SELECT user_input, aria_response FROM aria_memory
            WHERE username = %s ORDER BY id DESC LIMIT 8
        """, (username,))
        history = [{'q': r[0][:150], 'a': r[1][:200]} for r in c.fetchall()]
    finally:
        if conn: conn.close()

    display_name = username.capitalize()
    prompt = f"""Tu es l'assistant de {display_name} — Couffrant Solar.

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


# ─────────────────────────────────────────
# NIVEAU 1 — RÈGLES (par utilisateur)
# ─────────────────────────────────────────

def get_aria_rules(username: str = 'guillaume') -> str:
    """
    Retourne les règles actives d'Aria pour injection dans le system prompt.

    Section 1 — Règles de comportement/style : Aria les applique activement.
    Section 2 — Règles techniques (tri, spam, urgence, contacts) : Aria les voit
                pour éviter les doublons et pouvoir les modifier via FORGET+LEARN.
    Les paramètres memoire (synth_threshold...) ne sont pas affichés —
    ils sont utilisés directement par le code.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Section 1 : comportement, style, métier — Aria les applique
        behavior_categories = ('comportement', 'style', 'style_reponse', 'métier', 'préférence', 'auto', 'général')
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true AND username = %s
            AND category = ANY(%s)
            ORDER BY confidence DESC, reinforcements DESC, created_at DESC
            LIMIT 25
        """, (username, list(behavior_categories)))
        behavior_rows = c.fetchall()

        # Section 2 : règles techniques — Aria les connaît pour ne pas créer de doublons
        technical_categories = ('tri_mails', 'urgence', 'anti_spam', 'regroupement', 'contacts_cles')
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements
            FROM aria_rules
            WHERE active = true AND username = %s
            AND category = ANY(%s)
            ORDER BY category, confidence DESC, created_at DESC
        """, (username, list(technical_categories)))
        technical_rows = c.fetchall()

    finally:
        if conn: conn.close()

    parts = []

    if behavior_rows:
        parts.append("\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in behavior_rows]))

    if technical_rows:
        tech_lines = "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in technical_rows])
        parts.append(
            "— Règles techniques (tri, spam, urgence, contacts) —\n"
            "Tu les vois pour éviter les doublons et les modifier via FORGET+LEARN :\n"
            + tech_lines
        )

    return "\n\n".join(parts) if parts else ""


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


# ─────────────────────────────────────────
# NIVEAU 1 — INSIGHTS (par utilisateur)
# ─────────────────────────────────────────

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


# ─────────────────────────────────────────
# NIVEAU 2 — SYNTHÈSE AUTO (par utilisateur)
# ─────────────────────────────────────────

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

    prompt = f"""Tu es Aria, assistante de {display_name} (Couffrant Solar).
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
# NIVEAU 2 — CONTACTS (partagés)
# ─────────────────────────────────────────

def get_contact_card(name_or_email: str) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, email, company, role, summary, last_seen, last_subject
            FROM aria_contacts WHERE name ILIKE %s OR email ILIKE %s LIMIT 1
        """, (f'%{name_or_email}%', f'%{name_or_email}%'))
        row = c.fetchone()
        if not row: return ""
        return f"{row[0]} ({row[1]}) — {row[2]} — {row[3]}\nRésumé : {row[4]}\nDernier contact : {row[5]} | Sujet : {row[6]}"
    finally:
        if conn: conn.close()


def get_all_contact_cards() -> list:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT name, email, company, summary, last_seen FROM aria_contacts ORDER BY last_seen DESC LIMIT 30")
        return [{'name': r[0], 'email': r[1], 'company': r[2], 'summary': r[3], 'last_seen': str(r[4])} for r in c.fetchall()]
    finally:
        if conn: conn.close()


def rebuild_contacts() -> int:
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
            GROUP BY from_email HAVING COUNT(*) >= 2
            ORDER BY MAX(received_at) DESC LIMIT 50
        """)
        rows = c.fetchall()
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
            conn = None
            try:
                conn = get_pg_conn()
                c2 = conn.cursor()
                c2.execute("""
                    INSERT INTO aria_contacts (email, name, company, role, summary, last_seen, last_subject, mail_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (email) DO UPDATE SET
                        name=EXCLUDED.name, company=EXCLUDED.company, role=EXCLUDED.role,
                        summary=EXCLUDED.summary, last_seen=EXCLUDED.last_seen,
                        last_subject=EXCLUDED.last_subject, mail_count=EXCLUDED.mail_count, updated_at=NOW()
                """, (email, name, company, role, summary, str(last_seen), (subjects or [''])[0], mail_count))
                conn.commit()
            finally:
                if conn: conn.close()
            updated += 1
        except Exception as e:
            print(f"[Contacts] Erreur {email}: {e}")
    return updated


# ─────────────────────────────────────────
# NIVEAU 2 — STYLE (par utilisateur)
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


# ─────────────────────────────────────────
# PURGE
# ─────────────────────────────────────────

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
# RÈGLES PAR CATÉGORIE — API interne utilisée par les modules
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


def get_contacts_keywords(username: str = 'guillaume') -> list[str]:
    keywords = []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT name, email FROM aria_contacts ORDER BY last_seen DESC LIMIT 50")
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


def seed_default_rules(username: str = 'guillaume'):
    """
    Insère les règles par défaut pour un utilisateur si aucune règle n'existe encore.
    Idempotent : n'écrase jamais des règles existantes.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM aria_rules WHERE username = %s", (username,))
        count = c.fetchone()[0]
    finally:
        if conn: conn.close()

    if count > 0:
        return

    defaults = [
        ("tri_mails", "Mails contenant 'enedis', 'engie', 'raccordement', 'consuel', 'injection', 'tgbt', 'point de livraison' = catégorie raccordement, priorité haute"),
        ("tri_mails", "Mails contenant 'devis', 'offre', 'proposition', 'tarif', 'prix', 'commande', 'contrat', 'signature' = catégorie commercial, priorité moyenne"),
        ("tri_mails", "Mails contenant 'chantier', 'planning', 'intervention', 'installation', 'pose', 'mise en service', 'travaux' = catégorie chantier, priorité moyenne"),
        ("tri_mails", "Mails contenant 'facture', 'paiement', 'échéance', 'relance', 'avoir', 'règlement' = catégorie financier, priorité haute"),
        ("tri_mails", "Mails contenant 'réunion', 'meeting', 'invitation calendrier', 'visioconférence', 'teams.microsoft.com' = catégorie reunion, priorité moyenne"),
        ("tri_mails", "Mails de couffrant-solar.fr = catégorie interne, priorité moyenne"),
        ("tri_mails", "Mails contenant 'photovoltaïque', 'pv', 'onduleur', 'batterie', 'autoconsommation', 'kstar', 'solaire' = catégorie chantier, priorité moyenne"),
        ("urgence", "Mails contenant 'urgent', 'immédiat', 'asap', 'bloqué', 'blocage', 'alerte' = priorité haute"),
        ("urgence", "Mails d'Enedis sur raccordement en attente = priorité haute, réponse requise rapidement"),
        ("urgence", "Mails contenant 'mise en demeure', 'litige', 'avocat', 'tribunal', 'contentieux' = priorité haute, signaler immédiatement"),
        ("urgence", "Mails contenant 'retard chantier', 'annulation', 'panne' = priorité haute"),
        ("anti_spam", "noreply, no-reply, donotreply"),
        ("anti_spam", "newsletter, marketing, promotional, unsubscribe, se désabonner"),
        ("anti_spam", "linkedin.com, twitter.com, facebook.com, instagram.com"),
        ("anti_spam", "indeed.com, welcometothejungle, jobteaser"),
        ("anti_spam", "mailer-daemon, notification automatique"),
        ("anti_spam", "enquête satisfaction, avis client, survey"),
        ("anti_spam", "webinar, webinaire, calendly, zoom invitation"),
        ("style_reponse", "Commencer les réponses par 'Bonjour,' suivi d'une accroche contextualisée"),
        ("style_reponse", "Terminer les mails professionnels par 'Solairement,' comme signature"),
        ("style_reponse", "Réponses directes et courtes, maximum 5 lignes sauf explication technique"),
        ("style_reponse", "Pour les mails Enedis/raccordement, confirmer toujours la réception et donner un délai"),
        ("style_reponse", "Ne jamais inventer de dates, chiffres ou informations techniques absents du mail"),
        ("regroupement", "Regrouper les mails d'un même fil 'raccordement', 'enedis', 'consuel'"),
        ("regroupement", "Regrouper les notifications automatiques d'un même expéditeur"),
        ("regroupement", "Regrouper les échanges sur un même chantier client"),
        ("contacts_cles", "arlène, arlene, sabrina, benoit, pierre, maxence, charlotte, pinto"),
        ("contacts_cles", "enedis, consuel, adiwatt, socotec, triangle, eleria, edf"),
        ("memoire", "synth_threshold:15"),
        ("memoire", "rebuild_cycles:40"),
        ("memoire", "purge_days:90"),
        ("memoire", "keep_recent:5"),
    ]

    for category, rule in defaults:
        save_rule(category, rule, "default", 0.75, username)

    print(f"[Seed] {len(defaults)} règles par défaut créées pour {username}")
