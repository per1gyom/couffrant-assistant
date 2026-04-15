"""
Regles et helpers de detection d'anomalies.
Extrait de anomaly_detection.py -- SPLIT-F6.
"""
import re
from app.logging_config import get_logger
logger=get_logger("raya.anomaly")


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

