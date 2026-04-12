"""
Détection d'anomalies croisées Odoo ≈ Mails (8-ANOMALIES).

Pour chaque utilisateur avec Odoo connecté :
  1. Récupère devis/factures Odoo récents (30 jours)
  2. Récupère mails récents mentionnant des montants (mail_memory)
  3. Utilise Haiku pour extraire les montants des mails
  4. Croise par fournisseur/client : montants différents = anomalie
  5. Crée une proactive_alert type 'info' si anomalie détectée

Conôle : SCHEDULER_ANOMALY_ENABLED (défaut: false).
Fréquence : toutes les 6h.
Silencieux si Odoo non connecté.
"""
import json
import re
from app.logging_config import get_logger

logger = get_logger("raya.anomaly")

# Seuil de différence considérée comme anomalie (en %)
ANOMALY_THRESHOLD_PCT = 10.0
# Montant minimal pour déclencher une comparaison (filtrer le bruit)
MIN_AMOUNT = 100.0


def _job_anomaly_detection():
    """Détecte les incohérences de montants entre Odoo et les mails. (8-ANOMALIES)"""
    try:
        from app.database import get_pg_conn
        from app.app_security import get_user_tools

        conn = get_pg_conn()
        c = conn.cursor()
        # Utilisateurs actifs ces 7 derniers jours
        c.execute("""
            SELECT DISTINCT username FROM aria_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
        """)
        active_users = [r[0] for r in c.fetchall()]
        conn.close()

        processed = 0
        for username in active_users:
            try:
                tools = get_user_tools(username)
                odoo_tool = tools.get('odoo', {})
                if not odoo_tool.get('enabled', False) or odoo_tool.get('access_level', 'none') == 'none':
                    continue
                _check_user_anomalies(username)
                processed += 1
            except Exception as e:
                logger.error(f"[Anomaly] Erreur {username}: {e}")

        if processed > 0:
            logger.info(f"[Anomaly] {processed} utilisateur(s) analysé(s)")

    except Exception as e:
        logger.error(f"[Anomaly] ERREUR job global: {e}")


def _check_user_anomalies(username: str):
    """Vérifie les anomalies Odoo vs mails pour un utilisateur."""
    from app.database import get_pg_conn
    from app.app_security import get_tenant_id

    tenant_id = get_tenant_id(username)

    # 1. Récupérer les devis/factures Odoo récents
    odoo_records = _fetch_odoo_amounts(username)
    if not odoo_records:
        return

    # 2. Récupérer les mails récents avec montants potentiels
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, from_email, subject, short_summary, raw_body_preview, received_at
        FROM mail_memory
        WHERE username = %s
          AND created_at > NOW() - INTERVAL '30 days'
          AND (raw_body_preview ILIKE '%€%'
            OR raw_body_preview ILIKE '%EUR%'
            OR raw_body_preview ILIKE '%montant%'
            OR raw_body_preview ILIKE '%devis%'
            OR raw_body_preview ILIKE '%facture%'
            OR raw_body_preview ILIKE '%k€%'
            OR subject ILIKE '%devis%'
            OR subject ILIKE '%facture%')
        ORDER BY received_at DESC
        LIMIT 50
    """, (username,))
    mail_rows = c.fetchall()
    conn.close()

    if not mail_rows:
        return

    # 3. Extraire les montants des mails via Haiku
    mail_amounts = _extract_amounts_from_mails(mail_rows, username)

    # 4. Croiser avec les données Odoo
    anomalies = _cross_check(odoo_records, mail_amounts)

    # 5. Créer les alertes
    if anomalies:
        from app.proactive_alerts import create_alert
        conn = get_pg_conn()
        c = conn.cursor()
        for anomaly in anomalies:
            # Dédupliquer : pas d'alerte pour la même anomalie en moins de 7 jours
            c.execute("""
                SELECT COUNT(*) FROM proactive_alerts
                WHERE username = %s AND source_type = 'anomaly'
                  AND source_id = %s
                  AND created_at > NOW() - INTERVAL '7 days'
            """, (username, anomaly['source_id']))
            if c.fetchone()[0] > 0:
                continue

            create_alert(
                username=username, tenant_id=tenant_id,
                alert_type="info", priority="high",
                title=f"⚠️ Anomalie détectée : {anomaly['partner'][:40]}",
                body=(
                    f"Montant Odoo : {anomaly['odoo_amount']:.0f}€ ({anomaly['odoo_ref']})\n"
                    f"Montant mail : {anomaly['mail_amount']:.0f}€ ({anomaly['mail_subject'][:60]})\n"
                    f"Différence : {anomaly['diff_pct']:.1f}%"
                ),
                source_type="anomaly",
                source_id=anomaly['source_id'],
            )
            logger.info(f"[Anomaly] Alerte créée pour {username} : {anomaly['partner']} — {anomaly['diff_pct']:.1f}%")
        conn.close()


def _fetch_odoo_amounts(username: str) -> list:
    """
    Récupère les devis et factures Odoo des 30 derniers jours.
    Retourne une liste de dicts {partner, amount, ref, type}.
    """
    try:
        from app.connectors.odoo_connector import odoo_search_read
        from app.app_security import get_user_tools

        tools = get_user_tools(username)
        odoo_cfg = tools.get('odoo', {}).get('config', {})
        shared_user = odoo_cfg.get('shared_user')
        effective_username = shared_user or username

        records = []

        # Devis (sale.order) et factures (account.move)
        for model, amount_field, state_field, active_states in [
            ('sale.order', 'amount_total', 'state', ['draft', 'sent', 'sale']),
            ('account.move', 'amount_total', 'state', ['draft', 'posted']),
        ]:
            try:
                results = odoo_search_read(
                    model=model,
                    domain=[
                        ['write_date', '>=', _days_ago_str(30)],
                        [state_field, 'in', active_states],
                    ],
                    fields=['name', 'partner_id', amount_field, 'write_date'],
                    username=effective_username,
                    limit=100,
                )
                for r in (results or []):
                    partner = r.get('partner_id', [None, ''])
                    partner_name = partner[1] if isinstance(partner, list) else str(partner)
                    amount = float(r.get(amount_field, 0) or 0)
                    if amount >= MIN_AMOUNT:
                        records.append({
                            'partner': partner_name.lower().strip(),
                            'partner_display': partner_name,
                            'amount': amount,
                            'ref': r.get('name', '?'),
                            'model': model,
                        })
            except Exception as e:
                logger.debug(f"[Anomaly] Odoo {model} erreur: {e}")

        return records
    except Exception as e:
        logger.debug(f"[Anomaly] _fetch_odoo_amounts échoué: {e}")
        return []


def _extract_amounts_from_mails(mail_rows: list, username: str) -> list:
    """
    Utilise Haiku pour extraire les montants et partenaires des mails.
    Retourne une liste de dicts {partner, amount, subject, mail_id}.
    """
    try:
        from app.llm_client import llm_complete

        # Préparer le texte des mails
        mails_text = "\n---\n".join([
            f"ID:{r[0]} | De:{r[1]} | Sujet:{r[2]} | Résumé:{r[3] or ''} | Préview:{(r[4] or '')[:300]}"
            for r in mail_rows
        ])

        prompt = f"""Analyse ces mails et extrais les montants financiers mentionnés.
Pour chaque mail avec un montant, donne :
- L'ID du mail
- Le nom du fournisseur/client (si mentionné)
- Le montant en euros (nombre seul, sans symbole)
- L'objet du mail

Mails :
{mails_text}

Réponds en JSON strict (sans backticks) :
{{"results": [
  {{"mail_id": 123, "partner": "nom entreprise ou vide", "amount": 1500.0, "subject": "objet mail"}}
]}}
Si aucun montant clair : {{"results": []}}
Seulement les montants >= {MIN_AMOUNT}€ et clairement identifiés."""

        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="fast",  # Haiku
            max_tokens=800,
        )

        raw = result["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)

        extracted = []
        for item in parsed.get("results", []):
            partner = (item.get("partner") or "").lower().strip()
            amount = float(item.get("amount", 0) or 0)
            if amount >= MIN_AMOUNT:
                extracted.append({
                    'partner': partner,
                    'amount': amount,
                    'subject': item.get("subject", ""),
                    'mail_id': item.get("mail_id"),
                })
        return extracted

    except Exception as e:
        logger.debug(f"[Anomaly] Extraction montants échouée: {e}")
        # Fallback regex simple
        return _extract_amounts_regex(mail_rows)


def _extract_amounts_regex(mail_rows: list) -> list:
    """Fallback regex pour extraire les montants si Haiku échoue."""
    results = []
    amount_pattern = re.compile(r'(\d{1,3}(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)\s*(?:€|EUR|k€)')
    for r in mail_rows:
        text = f"{r[2] or ''} {r[3] or ''} {r[4] or ''}"
        matches = amount_pattern.findall(text)
        for m in matches:
            try:
                amount_str = m.replace(' ', '').replace('.', '').replace(',', '.')
                if 'k' in text[text.find(m):text.find(m)+10].lower():
                    amount = float(amount_str) * 1000
                else:
                    amount = float(amount_str)
                if amount >= MIN_AMOUNT:
                    results.append({
                        'partner': (r[1] or '').lower().split('@')[-1].split('.')[0],
                        'amount': amount,
                        'subject': r[2] or '',
                        'mail_id': r[0],
                    })
            except Exception:
                pass
    return results


def _cross_check(odoo_records: list, mail_amounts: list) -> list:
    """
    Croise les montants Odoo et mail par partenaire.
    Retourne les anomalies détectées.
    """
    anomalies = []
    for odoo in odoo_records:
        odoo_partner = odoo['partner']
        if not odoo_partner:
            continue
        for mail in mail_amounts:
            mail_partner = mail['partner']
            if not mail_partner:
                continue
            # Match partiel sur le nom du partenaire (au moins 4 chars communs)
            if len(odoo_partner) < 3 or len(mail_partner) < 3:
                continue
            # Vérifier si les noms se ressemblent
            if not _partners_match(odoo_partner, mail_partner):
                continue
            # Comparer les montants
            diff = abs(odoo['amount'] - mail['amount'])
            diff_pct = (diff / max(odoo['amount'], mail['amount'])) * 100
            if diff_pct >= ANOMALY_THRESHOLD_PCT and diff >= MIN_AMOUNT:
                anomalies.append({
                    'partner': odoo['partner_display'],
                    'odoo_amount': odoo['amount'],
                    'odoo_ref': odoo['ref'],
                    'mail_amount': mail['amount'],
                    'mail_subject': mail['subject'],
                    'diff_pct': diff_pct,
                    'source_id': f"odoo:{odoo['ref']}:mail:{mail['mail_id']}",
                })
    return anomalies


def _partners_match(a: str, b: str) -> bool:
    """Vérifie si deux noms de partenaires sont similaires."""
    # Match exact ou inclusion
    if a in b or b in a:
        return True
    # Match sur les premiers mots significatifs
    words_a = set(w for w in a.split() if len(w) >= 4)
    words_b = set(w for w in b.split() if len(w) >= 4)
    if words_a and words_b and words_a & words_b:
        return True
    return False


def _days_ago_str(days: int) -> str:
    """Retourne une date ISO pour les filtres Odoo."""
    from datetime import datetime, timedelta
    return (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
