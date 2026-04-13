"""
Module de routage Raya — Phase 3a + 3b.

Centralise tous les micro-appels Haiku de classification :
  - route_query_tier()      : SIMPLE → smart (Sonnet) / COMPLEXE → deep (Opus)
  - route_mail_action()     : IGNORER / STOCKER / ANALYSER (pour webhook)
  - detect_session_theme()  : détecte si les échanges portent sur un sujet cohérent (B8)
  - detect_query_domains()  : détecte les domaines pertinents par mots-clés (5B-1)
  - execute_create_action() : ACTION:CREATE_PDF / ACTION:CREATE_EXCEL (TOOL-CREATE-FILES)

Garde-fou économique :
  Le nombre d'appels Opus par user par jour est limité (configurable via
  règle mémoire opus_daily_limit:N). Par défaut : 20 appels/jour.
  Au-delà du quota → fallback Sonnet automatiquement.

Tous les futurs micro-appels de classification Haiku doivent passer par ce module.
Pas de duplication d'appels Haiku ailleurs dans le code.
"""
import os
from app.llm_client import llm_complete

# Prompt système partagé pour tous les routages — compact et déterministe
_ROUTER_SYSTEM = (
    "Tu es un classificateur binaire. "
    "Réponds UNIQUEMENT par le mot demandé, rien d'autre."
)


def route_query_tier(
    query: str,
    username: str,
    tenant_id: str,
    history_len: int = 0,
) -> str:
    """
    Classifie la question en 'smart' (Sonnet) ou 'deep' (Opus).

    Heuristiques avant le micro-appel Haiku :
      - Question courte ou salutation  → smart directement (pas de Haiku)
      - Quota Opus dépassé             → smart (garde-fou économique)

    Sinon : micro-appel Haiku (max_tokens=3) retourne SIMPLE ou COMPLEXE.
    """
    query = (query or "").strip()

    # 1. Question vide ou très courte → smart
    if len(query) < 20:
        return "smart"

    # 2. Salutations et commandes simples → smart
    _SIMPLE_PATTERNS = (
        "bonjour", "bonsoir", "salut", "merci", "ok", "d'accord",
        "oui", "non", "vas-y", "confirme", "annule", "stop",
    )
    query_lower = query.lower()
    if any(query_lower.startswith(p) for p in _SIMPLE_PATTERNS) and len(query) < 60:
        return "smart"

    # 3. Garde-fou économique : vérifier le quota Opus du jour
    if _opus_quota_exceeded(username, tenant_id):
        return "smart"

    # 4. Micro-appel Haiku pour la classification
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Question : {query[:400]}\n\n"
                f"Cette question nécessite-t-elle une réflexion approfondie, "
                f"une analyse complexe ou une synthèse ? "
                f"Réponds SIMPLE ou COMPLEXE."
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=3,
        )
        verdict = result["text"].strip().upper()
        return "deep" if "COMPLEXE" in verdict else "smart"
    except Exception:
        return "smart"


def detect_session_theme(history: list) -> str | None:
    """
    Détecte si les derniers échanges portent sur un sujet cohérent (B8).

    Si oui → retourne le thème en 3-5 mots (ex: "chantier Dupont raccordement").
    Sinon  → retourne None.
    """
    if len(history) < 3:
        return None

    recent = history[-5:]
    exchanges = "\n".join([
        f"Q: {h.get('user_input', '')[:100]}\nR: {h.get('aria_response', '')[:60]}"
        for h in recent
    ])

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Voici les derniers échanges :\n{exchanges}\n\n"
                f"Ces échanges portent-ils TOUS sur un sujet cohérent et précis ?\n"
                f"Si oui : nomme ce sujet en 3-5 mots maximum (ex: 'chantier Dupont raccordement').\n"
                f"Si non (sujets variés ou conversation générale) : réponds AUCUN"
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=12,
        )
        verdict = result["text"].strip()
        if not verdict or "AUCUN" in verdict.upper() or len(verdict) < 4:
            return None
        theme = verdict.strip('."\'')
        return theme[:60] if len(theme) > 3 else None
    except Exception:
        return None


def detect_query_domains(query: str) -> list[str]:
    """
    Détecte les domaines pertinents dans la question de l'utilisateur.
    Retourne une liste parmi : mail, drive, teams, calendar, memory, workflow.
    Si aucun domaine détecté → retourne tous (fallback sûr).
    Gratuit (mots-clés, pas d'appel LLM).
    """
    if not query or len(query.strip()) < 3:
        return ["mail", "drive", "teams", "calendar", "memory", "workflow"]

    q = query.lower()
    domains = set()

    _DOMAIN_KEYWORDS = {
        "mail": ["mail", "email", "e-mail", "courrier", "inbox", "boîte", "boite",
                 "répondre", "repondre", "envoyer", "transférer", "transferer",
                 "archiver", "supprimer le mail", "corbeille", "pièce jointe"],
        "drive": ["drive", "fichier", "dossier", "sharepoint", "document",
                  "onedrive", "pdf", "excel", "devis", "facture fichier",
                  "chercher dans", "trouver le"],
        "teams": ["teams", "chat", "canal", "channel", "conversation teams",
                  "message teams", "groupe teams", "appel teams"],
        "calendar": ["calendrier", "agenda", "rdv", "rendez-vous", "réunion",
                     "reunion", "événement", "evenement", "planning", "créneau",
                     "creneau", "dispo"],
        "memory": ["apprends", "retiens", "oublie", "règle", "regle", "mémoire",
                   "memoire", "synthèse", "synthese", "insight"],
    }

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            domains.add(domain)

    if any(w in q for w in ["confirme", "annule", "valide", "action", "en attente"]):
        domains.add("workflow")

    if not domains:
        return ["mail", "drive", "teams", "calendar", "memory", "workflow"]

    domains.add("memory")
    return list(domains)


def route_mail_action(sender: str, subject: str, preview: str) -> str:
    """
    Triage mail via Haiku : IGNORER / STOCKER_SIMPLE / ANALYSER.
    """
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Mail reçu :\nDe : {sender}\nSujet : {subject}\n"
                f"Aperçu : {preview[:300]}\n\n"
                f"Catégorise ce mail : IGNORER (spam/notification auto) | "
                f"STOCKER_SIMPLE (info utile mais pas d'action) | "
                f"ANALYSER (nécessite attention/action). "
                f"Réponds par un seul mot."
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=5,
        )
        verdict = result["text"].strip().upper()
        if "IGNORER" in verdict:
            return "IGNORER"
        if "STOCKER" in verdict:
            return "STOCKER_SIMPLE"
        return "ANALYSER"
    except Exception:
        return "ANALYSER"


# ─── CRÉATION DE FICHIERS (TOOL-CREATE-FILES) ───

def execute_create_action(action_str: str, username: str, tenant_id: str) -> str:
    """
    Traite les actions de création de fichiers générés par Raya.

    Formats supportés :
      ACTION:CREATE_PDF:titre|contenu
        → Génère un PDF et retourne un lien Markdown de téléchargement.
        → contenu peut contenir \\n et des lignes "col1|col2" pour des tableaux.

      ACTION:CREATE_EXCEL:titre|headers|lignes
        → Génère un Excel et retourne un lien Markdown de téléchargement.
        → headers : colonnes séparées par ;
        → lignes  : lignes séparées par \\n, colonnes par ;

    Retourne un lien Markdown cliquable ou un message d'erreur.
    """
    base_url = os.getenv("APP_BASE_URL", "https://app.raya-ia.fr").rstrip("/")

    # Parsing du format ACTION:TYPE:params
    parts = action_str.split(":", 2)
    if len(parts) < 3:
        return "❌ Action de création malformée."

    action_type = parts[1].upper()   # CREATE_PDF ou CREATE_EXCEL
    params_raw  = parts[2]           # tout ce qui suit le 2e ":"

    # ── CREATE_PDF ──
    if action_type == "CREATE_PDF":
        # Format : titre|contenu  (le contenu peut contenir des |)
        sep = params_raw.find("|")
        if sep == -1:
            title   = params_raw.strip()
            content = ""
        else:
            title   = params_raw[:sep].strip()
            content = params_raw[sep + 1:].strip()

        if not title:
            return "❌ Titre manquant pour la création du PDF."

        try:
            from app.connectors.file_creator import create_pdf
            result = create_pdf(title=title, content=content, username=username)
            file_id  = result["file_id"]
            filename = result["filename"]
            url = f"{base_url}/download/{file_id}"
            return f"[📄 Télécharger {filename}]({url})"
        except Exception as e:
            return f"❌ Erreur création PDF : {str(e)[:120]}"

    # ── CREATE_EXCEL ──
    if action_type == "CREATE_EXCEL":
        # Format : titre|headers_csv|lignes
        # headers séparés par ;, lignes séparées par \n, colonnes par ;
        sub_parts = params_raw.split("|", 2)
        title        = sub_parts[0].strip() if len(sub_parts) > 0 else ""
        headers_raw  = sub_parts[1].strip() if len(sub_parts) > 1 else ""
        rows_raw     = sub_parts[2].strip() if len(sub_parts) > 2 else ""

        if not title:
            return "❌ Titre manquant pour la création de l'Excel."

        headers = [h.strip() for h in headers_raw.split(";") if h.strip()]
        data: list = []
        if rows_raw:
            for line in rows_raw.split("\n"):
                line = line.strip()
                if line:
                    data.append([c.strip() for c in line.split(";")])

        try:
            from app.connectors.file_creator import create_excel
            result = create_excel(
                title=title,
                data=data,
                headers=headers,
                username=username,
            )
            file_id  = result["file_id"]
            filename = result["filename"]
            url = f"{base_url}/download/{file_id}"
            return f"[📊 Télécharger {filename}]({url})"
        except Exception as e:
            return f"❌ Erreur création Excel : {str(e)[:120]}"

    return f"❌ Type de création inconnu : {action_type}"


# ─── GARDE-FOU ÉCONOMIQUE ───

def _opus_daily_limit(username: str) -> int:
    try:
        from app.rule_engine import get_memoire_param
        return get_memoire_param(username, "opus_daily_limit", 20)
    except Exception:
        return 20


def _opus_calls_today(username: str, tenant_id: str) -> int:
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM llm_usage
            WHERE username = %s
              AND tenant_id = %s
              AND model ILIKE '%%opus%%'
              AND purpose = 'raya_main_conversation'
              AND created_at > NOW() - INTERVAL '1 day'
        """, (username, tenant_id))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _opus_quota_exceeded(username: str, tenant_id: str) -> bool:
    limit = _opus_daily_limit(username)
    calls = _opus_calls_today(username, tenant_id)
    if calls >= limit:
        print(f"[Router] Quota Opus atteint pour {username} ({calls}/{limit}) — fallback Sonnet")
        return True
    return False


def get_routing_stats(username: str, tenant_id: str) -> dict:
    """Stats de routage du jour pour /admin/costs (Phase 3b)."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT model, COUNT(*) as calls,
                   SUM(input_tokens + output_tokens) as total_tokens
            FROM llm_usage
            WHERE username = %s
              AND tenant_id = %s
              AND purpose = 'raya_main_conversation'
              AND created_at > NOW() - INTERVAL '1 day'
            GROUP BY model
        """, (username, tenant_id))
        rows = c.fetchall()
        conn.close()
        return {
            "quota_limit":      _opus_daily_limit(username),
            "opus_calls_today": _opus_calls_today(username, tenant_id),
            "by_model": [{"model": r[0], "calls": r[1], "tokens": r[2]} for r in rows],
        }
    except Exception:
        return {}
