"""
Modèle d'urgence Raya — Phase 7.

Score 0-100 par message entrant. Combine :
  - Règles apprises (aria_rules catégorie 'urgence') → gratuit
  - Contacts connus (aria_contacts) → gratuit
  - Patterns temporels (aria_patterns) → gratuit
  - VIP boost (notification_prefs) → gratuit (7-5)
  - Phase de maturité → ajuste les seuils
  - Score LLM (Haiku) si les règles ne suffisent pas

Score de certitude 0-1 :
  >= 0.8 → décision finale
  < 0.8  → escalade Sonnet, puis Opus si toujours incertain
"""
import re
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.urgency")

# Seuils d'alerte (défauts, configurables par user via aria_rules)
THRESHOLD_SILENT    = 30   # 0-30  : silencieux
THRESHOLD_NORMAL    = 60   # 30-60 : résumé au prochain échange
THRESHOLD_IMPORTANT = 85   # 60-85 : WhatsApp
                           # 85+   : critique (appel, futur)


def score_mail_urgency(sender: str, subject: str, preview: str,
                       username: str, tenant_id: str = None) -> dict:
    """
    Calcule le score d'urgence d'un mail.

    Retourne :
    {
        "score": int (0-100),
        "certainty": float (0-1),
        "level": str (silent/normal/important/critical),
        "reasons": list[str],
        "method": str (rules/haiku/sonnet/opus),
    }
    """
    score = 0
    certainty = 0.0
    reasons = []

    # === ÉTAGE 1 : Règles apprises (gratuit) ===
    rule_score, rule_reasons = _score_by_rules(sender, subject, preview, username, tenant_id)
    score += rule_score
    reasons += rule_reasons

    # === ÉTAGE 2 : Contacts connus (gratuit) ===
    contact_score, contact_reasons = _score_by_contacts(sender, username, tenant_id)
    score += contact_score
    reasons += contact_reasons

    # === ÉTAGE 3 : Patterns (gratuit) ===
    pattern_score, pattern_reasons = _score_by_patterns(sender, subject, username, tenant_id)
    score += pattern_score
    reasons += pattern_reasons

    # Certitude basée sur le nombre de signaux
    signal_count = len(reasons)
    if signal_count >= 3:
        certainty = 0.9
    elif signal_count >= 2:
        certainty = 0.7
    elif signal_count >= 1:
        certainty = 0.5
    else:
        certainty = 0.3

    # === ÉTAGE 4 : LLM si certitude insuffisante ===
    if certainty < 0.8:
        llm_score, llm_certainty, llm_reasons = _score_by_llm(
            sender, subject, preview, username, tenant_id, score
        )
        # Pondération : 60% règles, 40% LLM
        score = int(score * 0.6 + llm_score * 0.4)
        certainty = max(certainty, llm_certainty)
        reasons += llm_reasons

    # === VIP boost (7-5) ===
    try:
        from app.notification_prefs import is_vip_sender, get_notification_prefs
        if is_vip_sender(sender, username):
            prefs = get_notification_prefs(username)
            vip_boost = prefs.get("vip_boost", 30)
            score += vip_boost
            reasons.append(f"Contact VIP (+{vip_boost})")
    except Exception:
        pass

    # Cap à 100
    score = min(100, max(0, score))

    # Niveau d'alerte
    level = get_alert_level(score)

    method = "rules" if certainty >= 0.8 and signal_count >= 2 else "haiku"

    return {
        "score": score,
        "certainty": round(certainty, 2),
        "level": level,
        "reasons": reasons,
        "method": method,
    }


def _score_by_rules(sender, subject, preview, username, tenant_id):
    """Score basé sur les règles d'urgence apprises."""
    score = 0
    reasons = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rule, confidence FROM aria_rules
            WHERE username = %s AND active = true
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category IN ('urgence', 'Tri mails', 'mail_filter')
              AND confidence >= 0.4
            ORDER BY confidence DESC LIMIT 20
        """, (username, tenant_id))
        rules = c.fetchall()
        conn.close()

        text = f"{sender} {subject} {preview}".lower()
        for rule_text, confidence in rules:
            rule_lower = rule_text.lower()
            keywords = [w.strip() for w in rule_lower.split() if len(w.strip()) > 3]
            matches = sum(1 for kw in keywords[:5] if kw in text)
            if matches >= 2:
                if any(w in rule_lower for w in ['urgent', 'critique', 'important', 'priorit']):
                    score += int(30 * confidence)
                    reasons.append(f"Règle urgence: {rule_text[:60]}")
                elif any(w in rule_lower for w in ['ignorer', 'spam', 'newsletter', 'bloquer']):
                    score -= 20
                    reasons.append(f"Règle filtre: {rule_text[:60]}")
    except Exception as e:
        logger.error(f"[Urgency] Erreur rules: {e}")
    return score, reasons


def _score_by_contacts(sender, username, tenant_id):
    """Score basé sur les contacts connus."""
    score = 0
    reasons = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, role, mail_count, tags FROM aria_contacts
            WHERE email = %s AND tenant_id = %s
            LIMIT 1
        """, (sender, tenant_id or 'couffrant_solar'))
        row = c.fetchone()
        conn.close()

        if row:
            name, role, mail_count, tags = row
            score += 15
            reasons.append(f"Contact connu: {name or sender}")
            if role and any(w in (role or '').lower() for w in ['client', 'direction', 'banque', 'avocat']):
                score += 20
                reasons.append(f"Rôle: {role}")
            if mail_count and mail_count > 20:
                score += 5
        else:
            if not any(p in sender.lower() for p in ['noreply', 'no-reply', 'newsletter']):
                score += 10
                reasons.append("Expéditeur inconnu (potentiellement nouveau)")
    except Exception as e:
        logger.error(f"[Urgency] Erreur contacts: {e}")
    return score, reasons


def _score_by_patterns(sender, subject, username, tenant_id=None):
    """Score basé sur les patterns détectés."""
    score = 0
    reasons = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT pattern_type, description, confidence FROM aria_patterns
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND active = true AND confidence >= 0.5
            ORDER BY confidence DESC LIMIT 10
        """, (username, tenant_id))
        patterns = c.fetchall()
        conn.close()

        text = f"{sender} {subject}".lower()
        for ptype, desc, conf in patterns:
            desc_lower = desc.lower()
            keywords = [w for w in desc_lower.split() if len(w) > 3]
            if any(kw in text for kw in keywords[:3]):
                if ptype == 'relational':
                    score += int(15 * conf)
                    reasons.append(f"Pattern relationnel: {desc[:50]}")
                elif ptype == 'temporal':
                    score += int(10 * conf)
                    reasons.append(f"Pattern temporel: {desc[:50]}")
    except Exception as e:
        logger.error(f"[Urgency] Erreur patterns: {e}")
    return score, reasons


def _score_by_llm(sender, subject, preview, username, tenant_id, current_score):
    """Score LLM (Haiku) si les règles ne suffisent pas."""
    score = 50  # défaut neutre
    certainty = 0.6
    reasons = []
    try:
        from app.llm_client import llm_complete
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Mail reçu :\nDe : {sender}\nSujet : {subject}\n"
                f"Aperçu : {preview[:300]}\n\n"
                f"Score d'urgence actuel basé sur les règles : {current_score}/100\n\n"
                f"Évalue l'urgence de ce mail sur 100 (0=spam, 50=routine, 80=important, 95=critique).\n"
                f"Réponds UNIQUEMENT par un nombre entre 0 et 100."
            )}],
            model_tier="fast",
            max_tokens=5,
            system="Tu es un classificateur d'urgence. Réponds UNIQUEMENT par un nombre entre 0 et 100.",
        )
        text = result["text"].strip()
        match = re.search(r'\d+', text)
        if match:
            score = min(100, max(0, int(match.group())))
            certainty = 0.85
            reasons.append(f"Estimation Haiku: {score}/100")
    except Exception as e:
        logger.error(f"[Urgency] Erreur LLM: {e}")
    return score, certainty, reasons


def get_alert_level(score: int) -> str:
    """Retourne le niveau d'alerte pour un score donné."""
    if score >= THRESHOLD_IMPORTANT:
        return "critical"
    elif score >= THRESHOLD_NORMAL:
        return "important"
    elif score >= THRESHOLD_SILENT:
        return "normal"
    return "silent"
