"""
Endpoints profil de l'utilisateur connecté.
  GET  /profile
  PUT  /profile/email
  PUT  /profile/password
  PUT  /profile/display-name
"""
from fastapi import APIRouter, Request, Body, Depends

from app.database import get_pg_conn
from app.app_security import authenticate, hash_password
from app.security_auth import validate_password_strength
from app.routes.deps import require_user

router = APIRouter()


@router.get("/profile")
def get_profile(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Essai avec tous les champs (enrichi en Phase 2 pour /settings)
        try:
            c.execute(
                """
                SELECT u.username, u.email, u.scope, u.tenant_id, u.display_name,
                       u.deletion_requested_at, u.phone, u.last_login, u.created_at,
                       u.settings, t.name AS tenant_name
                FROM users u
                LEFT JOIN tenants t ON t.id = u.tenant_id
                WHERE u.username = %s
                """,
                (username,)
            )
            row = c.fetchone()
            if not row:
                return {"error": "Utilisateur introuvable."}
            scope = row[2] or ""
            # Rôles cumulatifs (cohérent avec docs/architecture_roles_cumulatifs.md)
            is_tenant_admin = scope in ("tenant_admin", "admin", "super_admin")
            is_super_admin = scope in ("admin", "super_admin")
            return {
                "username": row[0],
                "email": row[1] or "",
                "scope": scope,
                "tenant_id": row[3] or "",
                "display_name": row[4] or "",
                "deletion_requested_at": str(row[5]) if row[5] else None,
                "phone": row[6] or "",
                "last_login": row[7].isoformat() if row[7] else None,
                "created_at": row[8].isoformat() if row[8] else None,
                "settings": row[9] or {},
                "tenant_name": row[10] or row[3] or "",
                "is_user": True,
                "is_tenant_admin": is_tenant_admin,
                "is_super_admin": is_super_admin,
            }
        except Exception:
            # Fallback sans colonnes optionnelles (rétrocompatibilité)
            c.execute("SELECT username, email, scope, tenant_id FROM users WHERE username=%s", (username,))
            row = c.fetchone()
            if not row:
                return {"error": "Utilisateur introuvable."}
            return {"username": row[0], "email": row[1] or "", "scope": row[2] or "", "tenant_id": row[3] or ""}
    except Exception as e:
        return {"error": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/email")
def update_profile_email(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    username = user["username"]
    email = payload.get("email", "").strip()
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        conn.commit()
        return {"status": "ok", "message": "Email mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/display-name")
def update_profile_display_name(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Permet à l'utilisateur de définir son nom d'affichage personnalisé."""
    username = user["username"]
    display_name = payload.get("display_name", "").strip()
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET display_name=%s WHERE username=%s",
            (display_name or None, username)
        )
        conn.commit()
        return {"status": "ok", "message": "Nom d'affichage mis à jour.", "display_name": display_name or ""}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/password")
def update_profile_password(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    username = user["username"]
    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")
    if not current_password or not new_password:
        return {"status": "error", "message": "Mot de passe actuel et nouveau requis."}
    ok, msg = validate_password_strength(new_password)
    if not ok:
        return {"status": "error", "message": msg}
    if not authenticate(username, current_password):
        return {"status": "error", "message": "Mot de passe actuel incorrect."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET password_hash=%s WHERE username=%s",
            (hash_password(new_password), username)
        )
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/phone")
def update_profile_phone(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Phase 2 /settings — numero de telephone (optionnel, alertes urgentes)."""
    username = user["username"]
    phone = (payload.get("phone") or "").strip()
    # Validation simple : on laisse l'utilisateur libre sur le format
    # mais on limite la longueur pour eviter les abus
    if len(phone) > 30:
        return {"status": "error", "message": "Numero trop long (max 30 caracteres)."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET phone=%s WHERE username=%s",
            (phone or None, username)
        )
        conn.commit()
        return {"status": "ok", "message": "Telephone mis a jour.", "phone": phone or ""}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/settings")
def update_profile_settings(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Phase 2 /settings — preferences d'affichage (toggles).

    Attendu : {settings: {email_notifications: bool, show_response_time: bool, compact_mode: bool}}
    Stocke en JSONB dans users.settings pour extensibilite future.
    """
    username = user["username"]
    new_settings = payload.get("settings", {})
    if not isinstance(new_settings, dict):
        return {"status": "error", "message": "Format invalide."}
    # Whitelist des cles autorisees (securite)
    allowed_keys = {
        "email_notifications",
        "show_response_time",
        "compact_mode",
        "auto_speak",
    }
    filtered = {k: v for k, v in new_settings.items() if k in allowed_keys}
    import json
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Merge avec les settings existants (on ne remplace pas tout)
        c.execute("SELECT settings FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        current = (row[0] if row else {}) or {}
        merged = {**current, **filtered}
        c.execute(
            "UPDATE users SET settings=%s WHERE username=%s",
            (json.dumps(merged), username)
        )
        conn.commit()
        return {"status": "ok", "message": "Preferences mises a jour.", "settings": merged}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.get("/profile/data-stats")
def get_data_stats(request: Request, user: dict = Depends(require_user)):
    """Phase 3 /settings — stats RGPD (ce que Raya a collecte sur toi).

    Retourne les compteurs pour l'onglet Mes donnees, utilises dans le
    bloc 'Ce que Raya a collecte sur toi'.

    Audit isolation 28/04 : ajout du filtre tenant_id sur toutes les
    requetes pour proteger contre une eventuelle homonymie cross-tenant
    (findings I.1-I.4).
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    stats = {
        "rules": 0,
        "mails_analyzed": 0,
        "conversations": 0,
        "contacts": 0,
        "account_age_days": 0,
        "created_at": None,
    }
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Regles apprises
        try:
            c.execute(
                "SELECT COUNT(*) FROM aria_rules WHERE username=%s AND tenant_id=%s",
                (username, tenant_id),
            )
            stats["rules"] = c.fetchone()[0] or 0
        except Exception:
            pass
        # Mails analyses (sent + received)
        try:
            c.execute(
                "SELECT COUNT(*) FROM sent_mail_memory WHERE username=%s AND tenant_id=%s",
                (username, tenant_id),
            )
            stats["mails_analyzed"] = c.fetchone()[0] or 0
        except Exception:
            pass
        # Conversations (sessions distinctes de chat avec Raya)
        try:
            c.execute(
                "SELECT COUNT(*) FROM aria_session_digests WHERE username=%s AND tenant_id=%s",
                (username, tenant_id),
            )
            stats["conversations"] = c.fetchone()[0] or 0
        except Exception:
            pass
        # Contacts uniques (destinataires distincts)
        try:
            c.execute(
                "SELECT COUNT(DISTINCT LOWER(to_email)) FROM sent_mail_memory "
                "WHERE username=%s AND tenant_id=%s AND to_email IS NOT NULL",
                (username, tenant_id),
            )
            stats["contacts"] = c.fetchone()[0] or 0
        except Exception:
            pass
        # Age du compte
        try:
            c.execute("SELECT created_at FROM users WHERE username=%s", (username,))
            row = c.fetchone()
            if row and row[0]:
                from datetime import datetime
                created = row[0]
                delta = datetime.utcnow() - created
                stats["account_age_days"] = max(0, delta.days)
                stats["created_at"] = created.isoformat()
        except Exception:
            pass
        return stats
    except Exception as e:
        return {"error": str(e)[:100], **stats}
    finally:
        if conn: conn.close()


@router.get("/profile/connections")
def get_connections(request: Request, user: dict = Depends(require_user)):
    """Phase 5 /settings — statut des connexions OAuth de l'utilisateur.

    Retourne la liste des providers connectes pour l'utilisateur,
    leur statut (ok / expiring_soon / expired / missing), et la derniere
    mise a jour du token. Le refresh_token permet le rafraichissement
    automatique tant qu'il n'est pas revoque cote fournisseur.
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT provider, expires_at, updated_at,
                   (refresh_token IS NOT NULL) AS has_refresh_token
            FROM oauth_tokens
            WHERE username = %s AND tenant_id = %s
            ORDER BY provider
            """,
            (username, tenant_id)
        )
        rows = c.fetchall()
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        connections = []
        for row in rows:
            provider, expires_at, updated_at, has_refresh = row
            if expires_at is None:
                status = "no_expiry"
            elif expires_at < now:
                # Expire cote API mais refresh_token dispo => auto-refreshable
                status = "refreshable" if has_refresh else "expired"
            elif expires_at < now + timedelta(days=3):
                status = "expiring_soon"
            else:
                status = "ok"
            connections.append({
                "provider": provider,
                "status": status,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "has_refresh_token": bool(has_refresh),
            })
        # Enrichir avec les providers supportes mais non connectes
        known_providers = {row["provider"] for row in [dict(zip(["provider"], [c[0]])) for c in rows]}
        known_providers = {r[0] for r in rows}
        for provider in ("google", "microsoft"):
            if provider not in known_providers:
                connections.append({
                    "provider": provider,
                    "status": "missing",
                    "expires_at": None,
                    "updated_at": None,
                    "has_refresh_token": False,
                })
        return {"connections": connections}
    except Exception as e:
        return {"error": str(e)[:150], "connections": []}
    finally:
        if conn: conn.close()


@router.post("/profile/extract-signatures")
def extract_my_signatures(request: Request, user: dict = Depends(require_user)):
    """Phase 5 /settings — l'utilisateur declenche lui-meme l'extraction de
    ses signatures depuis ses derniers mails Microsoft envoyes.
    Wrapper de /admin/extract-signatures avec require_user.
    """
    username = user["username"]
    tenant_id = user.get("tenant_id") or "couffrant_solar"
    try:
        from app.token_manager import get_valid_microsoft_token
        token = get_valid_microsoft_token(username)
    except Exception as e:
        return {"ok": False, "status": "error",
                "message": f"Token Microsoft indisponible : {str(e)[:100]}"}
    try:
        from app.email_signature import extract_and_save_signature
        result = extract_and_save_signature(username, tenant_id, token)
        if not isinstance(result, dict):
            return {"status": "ok", "ok": True, "result": str(result)}
        # Harmonisation du format de retour pour le toast
        if result.get("ok", True) and "count" not in result:
            # extract_and_save_signature peut renvoyer "signatures_found" ou similaires
            count = result.get("signatures_found") or result.get("count") or 1
            result["count"] = count
        result.setdefault("status", "ok" if result.get("ok", True) else "error")
        return result
    except Exception as e:
        return {"ok": False, "status": "error", "message": str(e)[:150]}


# Tarifs Anthropic (USD par 1M tokens) — sources docs Anthropic
LLM_PRICES = {
    "claude-opus-4-7":      {"in": 15.00, "out": 75.00},
    "claude-opus-4-6":      {"in": 15.00, "out": 75.00},
    "claude-opus-4-5":      {"in": 15.00, "out": 75.00},
    "claude-sonnet-4-6":    {"in":  3.00, "out": 15.00},
    "claude-sonnet-4-5":    {"in":  3.00, "out": 15.00},
    "claude-haiku-4-5":     {"in":  1.00, "out":  5.00},
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    # Fallback : mid-tier
    "unknown":              {"in":  3.00, "out": 15.00},
}


def _calc_cost_usd(model, in_tok, out_tok):
    """Calcule le cout en USD d'un appel LLM."""
    prices = LLM_PRICES.get(model or "unknown", LLM_PRICES["unknown"])
    cost = (in_tok or 0) * prices["in"] / 1_000_000
    cost += (out_tok or 0) * prices["out"] / 1_000_000
    return round(cost, 4)


@router.get("/usage/me")
def get_usage_me(request: Request, user: dict = Depends(require_user)):
    """Phase 6 /settings — stats de consommation tokens de l'utilisateur.

    Retourne : today / week / month / year avec tokens + cost_usd
               + repartition par modele + par origine (purpose)
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Agregat par periode : utilise NOW() puis delta en JS/server
        # On recupere tous les appels des 365 derniers jours et on aggrege en Python
        c.execute(
            """
            SELECT created_at, model, input_tokens, output_tokens, purpose
            FROM llm_usage
            WHERE username = %s AND tenant_id = %s
              AND created_at > NOW() - INTERVAL '365 days'
            ORDER BY created_at DESC
            """,
            (username, tenant_id)
        )
        rows = c.fetchall()
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=6)      # 7 derniers jours glissants
        month_start = today_start - timedelta(days=29)    # 30 derniers jours glissants
        year_start = today_start - timedelta(days=364)    # 365 derniers jours glissants

        # Initialisation des agregats
        periods = {
            "today": {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0},
            "week":  {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0},
            "month": {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0},
            "year":  {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0},
        }
        by_model = {}    # model -> {tokens_in, tokens_out, cost_usd, calls}
        by_purpose = {}  # purpose -> {tokens_in, tokens_out, cost_usd, calls}

        for created_at, model, in_tok, out_tok, purpose in rows:
            in_tok = in_tok or 0
            out_tok = out_tok or 0
            cost = _calc_cost_usd(model, in_tok, out_tok)
            # Periode
            if created_at >= today_start:
                p = periods["today"]
                p["tokens_in"] += in_tok; p["tokens_out"] += out_tok
                p["cost_usd"] += cost; p["calls"] += 1
            if created_at >= week_start:
                p = periods["week"]
                p["tokens_in"] += in_tok; p["tokens_out"] += out_tok
                p["cost_usd"] += cost; p["calls"] += 1
            if created_at >= month_start:
                p = periods["month"]
                p["tokens_in"] += in_tok; p["tokens_out"] += out_tok
                p["cost_usd"] += cost; p["calls"] += 1
            if created_at >= year_start:
                p = periods["year"]
                p["tokens_in"] += in_tok; p["tokens_out"] += out_tok
                p["cost_usd"] += cost; p["calls"] += 1
            # Par modele (sur les 30 derniers jours pour pertinence)
            if created_at >= month_start:
                m = model or "unknown"
                if m not in by_model:
                    by_model[m] = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}
                by_model[m]["tokens_in"] += in_tok
                by_model[m]["tokens_out"] += out_tok
                by_model[m]["cost_usd"] += cost
                by_model[m]["calls"] += 1
                # Par origine (sur les 30 derniers jours)
                pur = purpose or "autre"
                if pur not in by_purpose:
                    by_purpose[pur] = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}
                by_purpose[pur]["tokens_in"] += in_tok
                by_purpose[pur]["tokens_out"] += out_tok
                by_purpose[pur]["cost_usd"] += cost
                by_purpose[pur]["calls"] += 1

        # Arrondi des couts pour l'affichage
        for p in periods.values():
            p["cost_usd"] = round(p["cost_usd"], 2)
            p["tokens_total"] = p["tokens_in"] + p["tokens_out"]
        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 2)
            m["tokens_total"] = m["tokens_in"] + m["tokens_out"]
        for pur in by_purpose.values():
            pur["cost_usd"] = round(pur["cost_usd"], 2)
            pur["tokens_total"] = pur["tokens_in"] + pur["tokens_out"]

        return {
            "username": username,
            "periods": periods,
            "by_model": by_model,
            "by_purpose": by_purpose,
        }
    except Exception as e:
        return {"error": str(e)[:150]}
    finally:
        if conn: conn.close()


@router.post("/profile/request-quota-adjustment")
def request_quota_adjustment(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Phase 6 /settings — l'utilisateur demande a son admin d'ajuster
    ses quotas de tokens. Logge la demande dans activity_log (pour
    l'admin puisse la voir) et, plus tard, envoi d'un mail.
    """
    import json as _json
    from app.logging_config import get_logger
    _logger = get_logger("raya.quota_request")
    username = user["username"]
    tenant_id = user.get("tenant_id", "")
    message = (payload.get("message") or "").strip()
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        detail = _json.dumps({"message": message, "timestamp": str(request.headers.get("x-date", ""))})
        c.execute(
            """
            INSERT INTO activity_log (username, tenant_id, action_type, action_target, action_detail, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (username, tenant_id, "quota_adjustment_request", "admin", detail, "user_settings")
        )
        conn.commit()
        _logger.info("[quota] Demande ajustement quota : %s (%s)", username, message[:80])
        return {
            "status": "ok",
            "message": "Ta demande a ete enregistree. Ton admin sera notifie."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}
    finally:
        if conn: conn.close()
