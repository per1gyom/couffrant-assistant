"""
Endpoints setup 2FA — chantier 29/04 LOT 2.

Permet a un user (super_admin ou tenant_admin) d activer la 2FA sur
son compte, generer ses codes recovery, et regenerer ces codes.

NE TOUCHE PAS au login flow — ce sera LOT 3.
NE FORCE PAS l activation — ce sera LOT 3 (avec periode de grace 7j).

Endpoints :
  GET  /admin/2fa/status              (require_user) — etat de sa 2FA
  GET  /admin/2fa/setup               (require_admin) — page HTML d activation
  POST /admin/2fa/setup/start         (require_admin) — initie setup, genere QR
  POST /admin/2fa/setup/verify        (require_admin) — valide 1er code, active
  POST /admin/2fa/setup/cancel        (require_admin) — annule setup en cours
  POST /admin/2fa/recovery-codes/regenerate (require_admin) — regen 8 codes

Decisions Q1-Q7 actees :
  Q1=B : super_admin + tenant_admin (admin Raya inclus)
  Q2=B : 8 codes recovery, format XXXXX-XXXXX
  Q3=B : 7j de grace (info exposee dans /status, pas force ici)
  Q5=B : fenetre TOTP +-90s (gere dans app/totp.py)

Stockage transitoire du secret pendant le setup :
  Le secret base32 brut est mis en session (request.session["totp_setup_secret"])
  pendant que le user scanne le QR + tape le code. Si abandon ou expiration
  session, le secret part avec elle, jamais ecrit en DB.
  Validite max : 10 minutes apres /setup/start (anti-stale).
"""
import base64
import json
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth_events import log_auth_event
from app.database import get_pg_conn
from app.logging_config import get_logger
from app.routes.deps import require_admin, require_user
from app.totp import (
    consume_recovery_code,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_provisioning_uri,
    generate_qr_code_png,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_codes_batch,
    verify_totp_code,
)

logger = get_logger("raya.two_factor")

router = APIRouter(prefix="/admin/2fa", tags=["admin", "2fa"])

# Duree max d un setup en cours (secondes)
SETUP_SESSION_MAX_AGE = 10 * 60  # 10 min
# Periode de grace 7j apres creation du compte (Q3=B)
GRACE_PERIOD_DAYS = 7
# Scopes obliges d activer la 2FA (Q1=B)
SCOPES_REQUIRING_2FA = ("super_admin", "admin", "tenant_admin")


# --- HELPERS PRIVES ---

def _client_ip(request: Request) -> str:
    """Extrait l IP client (fiable en cas de proxy Railway)."""
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if request.client else "unknown"


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:512]


def _fetch_user_2fa_state(username: str, tenant_id: str) -> Optional[dict]:
    """
    Lit l etat 2FA d un user en DB.
    Retourne None si user introuvable.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT
                totp_secret_encrypted,
                totp_enabled_at,
                COALESCE(jsonb_array_length(recovery_codes_hashes), 0) AS recovery_remaining,
                COALESCE(recovery_codes_used_count, 0),
                created_at,
                scope
            FROM users
            WHERE username = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "totp_secret_encrypted": row[0],
            "totp_enabled_at": row[1],
            "recovery_remaining": row[2],
            "recovery_used_count": row[3],
            "created_at": row[4],
            "scope": row[5],
        }
    except Exception as e:
        logger.error("[2FA] _fetch_user_2fa_state error: %s", str(e)[:200])
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _save_2fa_activation(
    username: str,
    tenant_id: str,
    encrypted_secret: str,
    recovery_hashes: list,
) -> bool:
    """
    Persiste en DB : secret chiffre + 8 hashes recovery + timestamp activation.
    Reset recovery_codes_used_count a 0.
    Atomique.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET totp_secret_encrypted = %s,
                totp_enabled_at = NOW(),
                recovery_codes_hashes = %s::jsonb,
                recovery_codes_used_count = 0
            WHERE username = %s AND tenant_id = %s
            """,
            (encrypted_secret, json.dumps(recovery_hashes), username, tenant_id),
        )
        conn.commit()
        return c.rowcount == 1
    except Exception as e:
        logger.error("[2FA] _save_2fa_activation error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _save_recovery_codes_only(
    username: str,
    tenant_id: str,
    recovery_hashes: list,
) -> bool:
    """Met a jour uniquement les codes recovery (regeneration)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET recovery_codes_hashes = %s::jsonb,
                recovery_codes_used_count = 0
            WHERE username = %s AND tenant_id = %s
              AND totp_enabled_at IS NOT NULL
            """,
            (json.dumps(recovery_hashes), username, tenant_id),
        )
        conn.commit()
        return c.rowcount == 1
    except Exception as e:
        logger.error("[2FA] _save_recovery_codes_only error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _calc_grace_period(created_at, scope: str) -> dict:
    """
    Calcule l etat de la periode de grace.
    Renvoie {grace_active: bool, grace_ends_at: str|None, days_left: int|None}.
    """
    if scope not in SCOPES_REQUIRING_2FA or created_at is None:
        return {"grace_active": False, "grace_ends_at": None, "days_left": None}
    from datetime import datetime, timedelta
    grace_ends = created_at + timedelta(days=GRACE_PERIOD_DAYS)
    now = datetime.utcnow()
    if grace_ends > now:
        delta = grace_ends - now
        return {
            "grace_active": True,
            "grace_ends_at": grace_ends.isoformat(),
            "days_left": delta.days + (1 if delta.seconds > 0 else 0),
        }
    return {"grace_active": False, "grace_ends_at": grace_ends.isoformat(), "days_left": 0}


# --- GET /admin/2fa/status ---

@router.get("/status")
def get_2fa_status(
    request: Request,
    user: dict = Depends(require_user),
):
    """
    Retourne l etat 2FA du user courant.
    Accessible a tous les users connectes (incl. tenant_user) pour
    qu ils sachent si leur compte est protege ou non.
    """
    state = _fetch_user_2fa_state(user["username"], user["tenant_id"])
    if state is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    enabled = state["totp_enabled_at"] is not None
    grace = _calc_grace_period(state["created_at"], user["scope"])
    must_setup = (
        user["scope"] in SCOPES_REQUIRING_2FA
        and not enabled
    )
    setup_in_progress = bool(request.session.get("totp_setup_secret"))

    return {
        "enabled": enabled,
        "enabled_at": state["totp_enabled_at"].isoformat() if state["totp_enabled_at"] else None,
        "recovery_codes_remaining": state["recovery_remaining"],
        "recovery_codes_used_count": state["recovery_used_count"],
        "scope": user["scope"],
        "must_setup": must_setup,
        "grace_active": grace["grace_active"],
        "grace_ends_at": grace["grace_ends_at"],
        "grace_days_left": grace["days_left"],
        "setup_in_progress": setup_in_progress,
    }


# --- POST /admin/2fa/setup/start ---

@router.post("/setup/start")
def start_2fa_setup(
    request: Request,
    user: dict = Depends(require_admin),
):
    """
    Initie la procedure d activation 2FA.
    Genere un secret TOTP + URI otpauth + QR PNG (base64).
    Le secret est mis en session, pas encore en DB.
    """
    state = _fetch_user_2fa_state(user["username"], user["tenant_id"])
    if state is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if state["totp_enabled_at"] is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "2FA deja activee. Pour la regenerer, demandez un reset a "
                "votre super_admin."
            ),
        )

    secret = generate_totp_secret()
    request.session["totp_setup_secret"] = secret
    request.session["totp_setup_started_at"] = time.time()

    uri = generate_provisioning_uri(user["username"], secret)
    qr_png_bytes = generate_qr_code_png(uri)
    qr_b64 = base64.b64encode(qr_png_bytes).decode("ascii")

    log_auth_event(
        username=user["username"],
        tenant_id=user["tenant_id"],
        event_type="2fa_setup_started",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )

    return {
        "secret_b32": secret,
        "provisioning_uri": uri,
        "qr_png_base64": qr_b64,
        "issuer": "Raya",
        "username": user["username"],
        "max_age_seconds": SETUP_SESSION_MAX_AGE,
    }


# --- POST /admin/2fa/setup/verify ---

@router.post("/setup/verify")
def verify_2fa_setup(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_admin),
):
    """
    Valide le 1er code TOTP et active definitivement la 2FA.
    Retourne les 8 codes de recovery EN CLAIR (a afficher 1 fois).
    """
    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code TOTP requis")

    secret = request.session.get("totp_setup_secret")
    started_at = request.session.get("totp_setup_started_at", 0)

    if not secret:
        raise HTTPException(
            status_code=400,
            detail="Aucun setup en cours. Recommencer via /setup/start.",
        )
    if (time.time() - started_at) > SETUP_SESSION_MAX_AGE:
        # Expiration : on vide pour repartir propre
        request.session.pop("totp_setup_secret", None)
        request.session.pop("totp_setup_started_at", None)
        raise HTTPException(
            status_code=400,
            detail="Setup expire (>10 min). Recommencer via /setup/start.",
        )

    if not verify_totp_code(secret, code):
        log_auth_event(
            username=user["username"],
            tenant_id=user["tenant_id"],
            event_type="2fa_setup_failed",
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "invalid_code"},
        )
        raise HTTPException(status_code=400, detail="Code invalide. Reessayer.")

    # Code OK : on active la 2FA
    try:
        encrypted = encrypt_totp_secret(secret)
    except RuntimeError as e:
        # TOKEN_ENCRYPTION_KEY absent en prod = blocage net
        logger.error("[2FA] Echec chiffrement secret: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Configuration serveur incomplete (chiffrement). Contactez le support.",
        )

    recovery_codes = generate_recovery_codes(8)
    recovery_hashes = hash_recovery_codes_batch(recovery_codes)

    saved = _save_2fa_activation(
        username=user["username"],
        tenant_id=user["tenant_id"],
        encrypted_secret=encrypted,
        recovery_hashes=recovery_hashes,
    )
    if not saved:
        raise HTTPException(status_code=500, detail="Echec persistance DB")

    # Vide la session de setup
    request.session.pop("totp_setup_secret", None)
    request.session.pop("totp_setup_started_at", None)
    # Note la derniere validation 2FA dans la session (pour LOT 4/5)
    request.session["last_2fa_validated_at"] = time.time()

    log_auth_event(
        username=user["username"],
        tenant_id=user["tenant_id"],
        event_type="2fa_setup_completed",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"recovery_codes_count": len(recovery_codes)},
    )

    return {
        "success": True,
        "message": "2FA activee. Sauvegardez ces 8 codes de recuperation maintenant — ils ne seront plus jamais affiches.",
        "recovery_codes": recovery_codes,
    }


# --- POST /admin/2fa/setup/cancel ---

@router.post("/setup/cancel")
def cancel_2fa_setup(
    request: Request,
    user: dict = Depends(require_admin),
):
    """Annule un setup en cours, vide la session."""
    had_setup = bool(request.session.get("totp_setup_secret"))
    request.session.pop("totp_setup_secret", None)
    request.session.pop("totp_setup_started_at", None)
    return {"success": True, "had_setup_in_progress": had_setup}


# --- POST /admin/2fa/recovery-codes/regenerate ---

@router.post("/recovery-codes/regenerate")
def regenerate_recovery_codes(
    request: Request,
    user: dict = Depends(require_admin),
):
    """
    Regenere 8 nouveaux codes de recuperation. L ancien lot est invalide.
    Le user doit avoir la 2FA activee.
    """
    state = _fetch_user_2fa_state(user["username"], user["tenant_id"])
    if state is None or state["totp_enabled_at"] is None:
        raise HTTPException(
            status_code=400,
            detail="2FA non activee. Activez-la d abord via /admin/2fa/setup.",
        )

    new_codes = generate_recovery_codes(8)
    new_hashes = hash_recovery_codes_batch(new_codes)

    saved = _save_recovery_codes_only(
        username=user["username"],
        tenant_id=user["tenant_id"],
        recovery_hashes=new_hashes,
    )
    if not saved:
        raise HTTPException(status_code=500, detail="Echec persistance DB")

    log_auth_event(
        username=user["username"],
        tenant_id=user["tenant_id"],
        event_type="recovery_codes_regenerated",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"new_codes_count": 8},
    )

    return {
        "success": True,
        "message": "8 nouveaux codes de recuperation generes. L ancien lot est invalide.",
        "recovery_codes": new_codes,
    }


# --- GET /admin/2fa/setup (page HTML) ---

_SETUP_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Activer la 2FA — Raya</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 720px; margin: 32px auto; padding: 0 20px; color: #1a1a2e; background: #fafafa; }
    h1 { color: #1a1a2e; margin-bottom: 8px; }
    h2 { margin-top: 32px; color: #2d3748; font-size: 1.15em; }
    .card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 16px 0; }
    .info { background: #e0f2fe; border-left: 4px solid #0ea5e9; padding: 12px 16px; border-radius: 4px; margin: 16px 0; }
    .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px 16px; border-radius: 4px; margin: 16px 0; }
    .success { background: #d1fae5; border-left: 4px solid #10b981; padding: 12px 16px; border-radius: 4px; margin: 16px 0; }
    .error { background: #fee2e2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 4px; margin: 16px 0; }
    button { background: #1a1a2e; color: white; border: 0; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 15px; font-weight: 500; }
    button:hover { background: #2d3748; }
    button:disabled { background: #94a3b8; cursor: not-allowed; }
    button.secondary { background: white; color: #1a1a2e; border: 1px solid #cbd5e1; }
    button.secondary:hover { background: #f1f5f9; }
    button.danger { background: #dc2626; }
    button.danger:hover { background: #b91c1c; }
    input[type=text] { padding: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 18px; font-family: ui-monospace, monospace; letter-spacing: 0.2em; text-align: center; width: 200px; }
    .qr-block { text-align: center; padding: 16px; }
    .qr-block img { max-width: 280px; border: 8px solid white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .secret-text { font-family: ui-monospace, monospace; font-size: 14px; background: #f1f5f9; padding: 10px; border-radius: 6px; word-break: break-all; user-select: all; }
    .recovery-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 16px 0; font-family: ui-monospace, monospace; }
    .recovery-grid div { background: #fffbeb; border: 1px dashed #f59e0b; padding: 10px; border-radius: 4px; font-size: 16px; text-align: center; user-select: all; }
    .step { background: #f8fafc; padding: 12px 16px; border-radius: 6px; margin: 8px 0; }
    .step-num { display: inline-block; width: 28px; height: 28px; background: #1a1a2e; color: white; border-radius: 50%; text-align: center; line-height: 28px; margin-right: 8px; font-weight: 600; }
    .hidden { display: none; }
    code { background: #f1f5f9; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>Authentification a deux facteurs (2FA)</h1>
  <p>Securise ton compte Raya avec un code temporaire genere par ton telephone.</p>

  <div id="status-block" class="card">Chargement de l etat...</div>

  <!-- BLOC 1 : pas encore active, on peut activer -->
  <div id="block-not-enabled" class="card hidden">
    <h2>Activer la 2FA</h2>
    <div class="step"><span class="step-num">1</span>Installer une app d authentification : <b>Microsoft Authenticator</b>, <b>Google Authenticator</b>, <b>Authy</b> ou <b>1Password</b>.</div>
    <div class="step"><span class="step-num">2</span>Cliquer sur <i>Demarrer</i> ci-dessous pour generer un QR code.</div>
    <div class="step"><span class="step-num">3</span>Scanner le QR code avec l app, puis taper le code a 6 chiffres affiche.</div>
    <div class="step"><span class="step-num">4</span>Sauvegarder les 8 codes de recuperation hors ligne (Bitwarden, papier, note Apple verrouillee).</div>
    <button onclick="startSetup()" id="btn-start">Demarrer l activation</button>
  </div>

  <!-- BLOC 2 : setup en cours, QR code affiche -->
  <div id="block-qr" class="card hidden">
    <h2>Scanner le QR code</h2>
    <div class="qr-block">
      <img id="qr-img" alt="QR code 2FA">
    </div>
    <p>Si l app ne peut pas scanner, copier ce secret manuellement :</p>
    <div class="secret-text" id="secret-text"></div>
    <h2>Entrer le code a 6 chiffres</h2>
    <input type="text" id="code-input" maxlength="6" placeholder="000000" inputmode="numeric" autocomplete="one-time-code">
    <button onclick="verifySetup()" id="btn-verify">Valider</button>
    <button onclick="cancelSetup()" class="secondary">Annuler</button>
  </div>

  <!-- BLOC 3 : 2FA activee, codes recovery a afficher -->
  <div id="block-recovery" class="card hidden">
    <div class="success">
      <b>2FA activee.</b> Voici tes 8 codes de recuperation. <b>Sauvegarde-les MAINTENANT</b> dans Bitwarden ou autre — ils ne seront plus jamais affiches.
    </div>
    <div class="recovery-grid" id="recovery-grid"></div>
    <button onclick="copyAllCodes()" class="secondary">Copier les 8 codes</button>
    <button onclick="window.location.reload()">J ai sauvegarde mes codes</button>
  </div>

  <!-- BLOC 4 : 2FA deja active, options -->
  <div id="block-already-enabled" class="card hidden">
    <div class="success">
      <b>2FA active</b> sur ce compte (depuis <span id="enabled-since"></span>).
      Codes de recuperation restants : <b id="recovery-remaining"></b> / 8.
    </div>
    <button onclick="regenerateCodes()" class="secondary">Regenerer les codes de recuperation</button>
    <p style="color: #64748b; font-size: 0.9em; margin-top: 16px;">Pour desactiver la 2FA, demande a ton super_admin.</p>
  </div>

  <div id="msg-block"></div>

  <script>
    async function loadStatus() {
      try {
        const r = await fetch('/admin/2fa/status');
        const d = await r.json();
        renderStatus(d);
      } catch (e) {
        showMsg('error', 'Erreur chargement statut : ' + e.message);
      }
    }

    function renderStatus(d) {
      const sb = document.getElementById('status-block');
      let txt = '';
      if (d.enabled) {
        txt = '<b>Statut :</b> 2FA active depuis ' + new Date(d.enabled_at).toLocaleDateString('fr-FR') + '.';
        document.getElementById('block-not-enabled').classList.add('hidden');
        document.getElementById('block-already-enabled').classList.remove('hidden');
        document.getElementById('enabled-since').textContent = new Date(d.enabled_at).toLocaleDateString('fr-FR');
        document.getElementById('recovery-remaining').textContent = d.recovery_codes_remaining;
      } else if (d.must_setup) {
        const grace = d.grace_active ? ' (periode de grace : ' + d.grace_days_left + ' jour(s) restant(s))' : '';
        txt = '<b>Statut :</b> 2FA <b>non activee</b>. Obligatoire pour ton role <code>' + d.scope + '</code>' + grace + '.';
        document.getElementById('block-not-enabled').classList.remove('hidden');
        document.getElementById('block-already-enabled').classList.add('hidden');
      } else {
        txt = '<b>Statut :</b> 2FA non activee. Optionnelle pour ton role <code>' + d.scope + '</code>, mais recommandee.';
        document.getElementById('block-not-enabled').classList.remove('hidden');
        document.getElementById('block-already-enabled').classList.add('hidden');
      }
      sb.innerHTML = txt;
    }

    async function startSetup() {
      const btn = document.getElementById('btn-start');
      btn.disabled = true;
      btn.textContent = 'Generation du QR...';
      try {
        const r = await fetch('/admin/2fa/setup/start', { method: 'POST' });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(err.detail || 'HTTP ' + r.status);
        }
        const d = await r.json();
        document.getElementById('qr-img').src = 'data:image/png;base64,' + d.qr_png_base64;
        document.getElementById('secret-text').textContent = d.secret_b32;
        document.getElementById('block-not-enabled').classList.add('hidden');
        document.getElementById('block-qr').classList.remove('hidden');
        document.getElementById('code-input').focus();
      } catch (e) {
        showMsg('error', 'Erreur : ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Demarrer l activation';
      }
    }

    async function verifySetup() {
      const code = document.getElementById('code-input').value.trim();
      if (!/^\d{6}$/.test(code)) {
        showMsg('error', 'Le code doit faire 6 chiffres.');
        return;
      }
      const btn = document.getElementById('btn-verify');
      btn.disabled = true;
      btn.textContent = 'Verification...';
      try {
        const r = await fetch('/admin/2fa/setup/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code })
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(err.detail || 'HTTP ' + r.status);
        }
        const d = await r.json();
        const grid = document.getElementById('recovery-grid');
        grid.innerHTML = d.recovery_codes.map(function(c) { return '<div>' + c + '</div>'; }).join('');
        document.getElementById('block-qr').classList.add('hidden');
        document.getElementById('block-recovery').classList.remove('hidden');
        showMsg('success', '2FA activee !');
      } catch (e) {
        showMsg('error', 'Code invalide : ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Valider';
      }
    }

    async function cancelSetup() {
      await fetch('/admin/2fa/setup/cancel', { method: 'POST' });
      window.location.reload();
    }

    async function regenerateCodes() {
      if (!confirm('Regenerer les codes de recuperation ? L ancien lot deviendra invalide.')) return;
      try {
        const r = await fetch('/admin/2fa/recovery-codes/regenerate', { method: 'POST' });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(err.detail || 'HTTP ' + r.status);
        }
        const d = await r.json();
        const grid = document.getElementById('recovery-grid');
        grid.innerHTML = d.recovery_codes.map(function(c) { return '<div>' + c + '</div>'; }).join('');
        document.getElementById('block-already-enabled').classList.add('hidden');
        document.getElementById('block-recovery').classList.remove('hidden');
      } catch (e) {
        showMsg('error', 'Erreur : ' + e.message);
      }
    }

    function copyAllCodes() {
      const codes = Array.from(document.querySelectorAll('#recovery-grid div')).map(function(d) { return d.textContent; }).join('\\n');
      navigator.clipboard.writeText(codes).then(function() {
        showMsg('success', '8 codes copies dans le presse-papier.');
      });
    }

    function showMsg(kind, txt) {
      const el = document.getElementById('msg-block');
      el.innerHTML = '<div class="' + kind + '">' + txt + '</div>';
      setTimeout(function() { el.innerHTML = ''; }, 5000);
    }

    loadStatus();
  </script>
</body>
</html>
"""


@router.get("/setup", response_class=HTMLResponse)
def setup_page(
    request: Request,
    user: dict = Depends(require_admin),
):
    """Page HTML de setup 2FA. Reservee aux admin/super_admin/tenant_admin."""
    return HTMLResponse(content=_SETUP_HTML)
