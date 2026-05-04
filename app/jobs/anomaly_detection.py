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
from app.jobs.anomaly_rules import _partners_match, _days_ago_str, _cross_check, _extract_amounts_regex  # noqa

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
        # CROSS-TENANT INTENTIONNEL (etape A.5 part 2 du 26/04) :
        # Ce job tourne en boucle scheduler et traite TOUS les users
        # actifs tous tenants confondus. Le SELECT ne filtre donc
        # volontairement pas par tenant_id. Les fonctions appelees en
        # aval doivent re-resoudre le tenant_id depuis le username.
        # Voir docs/tests_isolation_26avril.md scenario 1.2.
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
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND created_at > NOW() - INTERVAL '30 days'
          AND deleted_at IS NULL
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
    """, (username, tenant_id))
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
                WHERE username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                  AND source_type = 'anomaly'
                  AND source_id = %s
                  AND created_at > NOW() - INTERVAL '7 days'
            """, (username, tenant_id, anomaly['source_id']))
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

