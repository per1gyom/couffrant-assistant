"""
Backup externe Raya vers Google Drive Saiyan Backups.

Phase 2 du plan_backups_29avril.md.

Architecture :
1. _generate_pg_dump()         : pg_dump format custom -Fc (fallback CSV si indispo)
2. _collect_secrets()          : exporte les env vars Railway (denylist explicite)
3. _create_archive()           : tar.gz avec dump.* + secrets.env + manifest.json
4. _encrypt_archive()          : Fernet via app.crypto_backup
5. _upload_to_drive()          : upload resumable vers Shared Drive Saiyan Backups
6. _rotate_old_backups()       : garde les 30 derniers jours, supprime au-dela
7. _run_backup_external_inner(): orchestrateur (sans timeout, ne pas appeler direct)
8. run_backup_external()       : wrapper avec timeout 10 min via ThreadPoolExecutor

Variables Railway requises :
- GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON : contenu JSON du service account
- GOOGLE_DRIVE_BACKUP_FOLDER_ID     : ID du Shared Drive Saiyan Backups
- BACKUP_ENCRYPTION_KEY             : cle Fernet (cf crypto_backup.py)

Variables optionnelles :
- BACKUP_ALERT_EMAIL   : mail destinataire alerte si echec (def admin@raya-ia.fr)
- BACKUP_KEEP_DAYS     : nb de backups gardes (def 30)
"""
import io
import os
import json
import gzip
import tarfile
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.logging_config import get_logger

logger = get_logger("raya.backup_external")


# Variables systeme exclues du backup secrets (denylist)
SECRETS_DENYLIST_PREFIX = (
    "RAILWAY_",       # variables Railway recreees au deploiement
    "_",              # variables privees (convention)
)
SECRETS_DENYLIST_EXACT = {
    "BACKUP_ENCRYPTION_KEY",  # CRITIQUE : auto-reference, faille securite
    "PATH", "PWD", "HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL",
    "PORT", "HOSTNAME", "PYTHONPATH", "PYTHONUNBUFFERED", "PYTHONHOME",
    "OLDPWD", "TMPDIR", "TZ",
}

DEFAULT_KEEP_DAYS = 30
BACKUP_FILENAME_PREFIX = "raya_backup_"

_drive_service = None
_drive_loaded = False


def _get_drive_service():
    """Lazy load du client Drive via service account JSON."""
    global _drive_service, _drive_loaded
    if _drive_loaded:
        return _drive_service
    _drive_loaded = True
    sa_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_json:
        logger.warning("[BackupExt] GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON absente.")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        sa_info = json.loads(sa_json)
        scopes = ["https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=scopes,
        )
        _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        logger.info(f"[BackupExt] Drive client OK (SA: {sa_info.get('client_email')})")
        return _drive_service
    except Exception as e:
        logger.error(f"[BackupExt] Echec init Drive client: {e}")
        return None


def _generate_pg_dump() -> tuple[bytes, str]:
    """
    Genere un pg_dump complet de la DB en format custom compresse (-Fc).

    Le format custom (-Fc) :
    - Compresse automatiquement (gzip level 6) => fichier ~3-4x plus petit
      qu un dump SQL plain text non compresse
    - Restoration via pg_restore (parallel jobs possible, restore selectif
      table par table, etc.)
    - Format binaire (pas lisible texte mais c est OK)

    Fallback CSV via COPY TO STDOUT si pg_dump indisponible.

    Retourne (bytes_dump, format_name) ou format_name est :
    - "custom"       : pg_dump -Fc reussi (preferent, ~250 MB pour 2 GB DB)
    - "csv_fallback" : pg_dump indispo ou erreur, retombe sur CSV (~1.5 GB)
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL absente, impossible de dumper")

    # Tentative pg_dump format custom (-Fc) compresse
    try:
        result = subprocess.run(
            ["pg_dump", "--no-password", "--no-owner", "--no-acl", "-Fc", db_url],
            capture_output=True,
            timeout=600,  # 10 min max pour 2 GB
        )
        if result.returncode == 0 and result.stdout:
            logger.info(
                f"[BackupExt] pg_dump OK (format custom -Fc) : "
                f"{len(result.stdout):,} bytes"
            )
            return (result.stdout, "custom")
        logger.warning(
            f"[BackupExt] pg_dump exit {result.returncode}: "
            f"{result.stderr[:200].decode(errors='replace')}"
        )
    except FileNotFoundError:
        logger.info("[BackupExt] pg_dump absent du PATH, fallback CSV.")
    except subprocess.TimeoutExpired:
        logger.error("[BackupExt] pg_dump timeout 600s, fallback CSV.")
    except Exception as e:
        logger.error(f"[BackupExt] pg_dump erreur: {e}, fallback CSV.")

    # Fallback : CSV via COPY TO STDOUT
    return (_generate_csv_fallback(), "csv_fallback")


def _generate_csv_fallback() -> bytes:
    """
    Fallback : COPY TO STDOUT CSV de toutes les tables publiques.
    Genere un .csv concatene avec marqueurs de tables.
    Restoration : plus complexe mais possible (script de re-import).
    """
    from app.database import get_pg_conn

    buf = io.StringIO()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    buf.write(f"-- Raya CSV Backup (pg_dump fallback) {ts}\n\n")

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [r[0] for r in c.fetchall()]
        buf.write(f"-- Tables exportees : {len(tables)}\n")
        buf.write(f"-- {', '.join(tables)}\n\n")
        for t in tables:
            buf.write(f"\n-- TABLE: {t}\n")
            try:
                tbuf = io.StringIO()
                c.copy_expert(f'COPY "{t}" TO STDOUT WITH CSV HEADER', tbuf)
                tbuf.seek(0)
                buf.write(tbuf.read())
            except Exception as e:
                buf.write(f"-- ERREUR table {t}: {e}\n")
    finally:
        conn.close()

    return buf.getvalue().encode("utf-8")


def _collect_secrets() -> dict:
    """
    Collecte toutes les variables d environnement Railway, avec denylist
    explicite pour exclure :
    - BACKUP_ENCRYPTION_KEY (auto-reference, faille de securite)
    - Variables systeme Linux (PATH, HOME, etc.)
    - Variables Railway internes (RAILWAY_*)
    - Variables privees (commencent par _)

    Retourne {included: {NAME: VALUE}, excluded_names: [NAME, ...]}.
    Le manifest contiendra les NAMES exclus (sans valeurs).
    """
    included = {}
    excluded = []
    for name, value in os.environ.items():
        # Exclusion par prefixe (ex RAILWAY_, _)
        if any(name.startswith(p) for p in SECRETS_DENYLIST_PREFIX):
            excluded.append(name)
            continue
        # Exclusion par nom exact
        if name in SECRETS_DENYLIST_EXACT:
            excluded.append(name)
            continue
        included[name] = value
    return {"included": included, "excluded_names": sorted(excluded)}


def _format_secrets_env(secrets: dict) -> bytes:
    """Formate les secrets en .env (KEY=VALUE par ligne, valeurs quotees)."""
    lines = ["# Raya secrets bundle - DO NOT commit anywhere\n"]
    lines.append(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append(f"# Included: {len(secrets['included'])} vars\n")
    lines.append(f"# Excluded: {len(secrets['excluded_names'])} vars (denylist)\n\n")
    for name in sorted(secrets["included"]):
        # Echappement basique : remplace " par \"
        val = secrets["included"][name].replace('"', '\\"')
        lines.append(f'{name}="{val}"\n')
    return "".join(lines).encode("utf-8")


def _create_archive(dump_bytes: bytes, secrets: dict, dump_format: str) -> tuple[bytes, dict]:
    """
    Cree une archive tar.gz contenant :
    - dump.pgcustom ou dump.sql (selon format), le pg_dump complet
    - secrets.env, les variables d environnement filtrees
    - manifest.json, metadonnees : date, taille, hash, version, format

    dump_format determine le nom du fichier dans l archive et la procedure
    de restauration :
    - "custom"       => dump.pgcustom, restorer via 'pg_restore'
    - "csv_fallback" => dump.sql, restorer via script custom (cf docs)

    Retourne (archive_bytes, manifest_dict).
    """
    ts_iso = datetime.now(timezone.utc).isoformat()
    secrets_bytes = _format_secrets_env(secrets)

    # Nom du fichier dump selon le format (= indication claire pour la restoration)
    if dump_format == "custom":
        dump_filename = "dump.pgcustom"
    else:
        dump_filename = "dump.sql"

    # Manifest (avec dump_format pour orienter la restoration)
    manifest = {
        "version": "1.1",  # bump : ajout dump_format + dump_filename
        "created_at_utc": ts_iso,
        "source": "Raya production (Railway)",
        "dump_format": dump_format,
        "dump_filename": dump_filename,
        "dump_size_bytes": len(dump_bytes),
        "dump_sha256": hashlib.sha256(dump_bytes).hexdigest(),
        "secrets_count_included": len(secrets["included"]),
        "secrets_count_excluded": len(secrets["excluded_names"]),
        "secrets_excluded_names": secrets["excluded_names"],
    }
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode()

    # Build tar.gz en memoire
    archive_buf = io.BytesIO()
    with tarfile.open(fileobj=archive_buf, mode="w:gz") as tar:
        for filename, content in [
            (dump_filename, dump_bytes),
            ("secrets.env", secrets_bytes),
            ("manifest.json", manifest_bytes),
        ]:
            info = tarfile.TarInfo(name=filename)
            info.size = len(content)
            info.mtime = int(datetime.now(timezone.utc).timestamp())
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(content))

    return archive_buf.getvalue(), manifest


def _upload_to_drive(encrypted_bytes: bytes, filename: str) -> dict:
    """
    Upload resumable vers le Shared Drive Saiyan Backups.
    Resumable = adapte aux gros fichiers (~600 MB) avec reprise en cas de coupure.
    Retourne {file_id, name, size, web_view_link}.
    """
    from googleapiclient.http import MediaIoBaseUpload

    drive = _get_drive_service()
    if drive is None:
        raise RuntimeError("Drive client non disponible")

    folder_id = os.getenv("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_BACKUP_FOLDER_ID absente")

    media = MediaIoBaseUpload(
        io.BytesIO(encrypted_bytes),
        mimetype="application/octet-stream",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )
    metadata = {
        "name": filename,
        "parents": [folder_id],
        "description": "Raya backup chiffre Fernet (BACKUP_ENCRYPTION_KEY)",
    }
    request = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, size, webViewLink",
        supportsAllDrives=True,
    )
    # Execute resumable upload (boucle interne progress)
    response = None
    while response is None:
        status, response = request.next_chunk()
    logger.info(f"[BackupExt] Upload Drive OK : {response['name']} "
                f"({int(response.get('size', 0)):,} bytes)")
    return response


def list_backups_on_drive() -> list:
    """
    Liste les backups presents sur le Shared Drive Saiyan Backups.
    Public (utilise par endpoint /admin/backup/external/list).
    Retourne [{id, name, size, createdTime}, ...] tries du plus recent au plus ancien.
    """
    drive = _get_drive_service()
    if drive is None:
        raise RuntimeError("Drive client non disponible")

    folder_id = os.getenv("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "").strip()
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and name contains '{BACKUP_FILENAME_PREFIX}'"
    )
    results = drive.files().list(
        q=query,
        fields="files(id, name, size, createdTime, webViewLink)",
        orderBy="createdTime desc",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="drive",
        driveId=folder_id,
    ).execute()
    return results.get("files", [])


def _rotate_old_backups(keep_days: int = DEFAULT_KEEP_DAYS) -> dict:
    """
    Supprime les backups au-dela du seuil keep_days.
    Retourne {kept: N, deleted: M, deleted_names: [...]}.
    """
    drive = _get_drive_service()
    backups = list_backups_on_drive()
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    deleted = []
    for f in backups:
        created = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00"))
        if created < cutoff:
            try:
                drive.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
                deleted.append(f["name"])
                logger.info(f"[BackupExt] Rotation : supprime {f['name']}")
            except Exception as e:
                logger.warning(f"[BackupExt] Rotation echec sur {f['name']}: {e}")
    return {"kept": len(backups) - len(deleted), "deleted": len(deleted),
            "deleted_names": deleted}


# Compteur d echecs consecutifs (in-memory, suffit car le scheduler tourne dans un seul process)
_consecutive_failures = 0


def _send_alert_mail(subject: str, body: str) -> None:
    """
    Envoie une alerte mail SMTP si echec backup.
    Pattern calque sur microsoft_webhook._send_revoked_alert.
    """
    recipient = os.getenv("BACKUP_ALERT_EMAIL", "admin@raya-ia.fr").strip()
    if not recipient:
        logger.warning("[BackupExt] BACKUP_ALERT_EMAIL absente, pas d alerte.")
        return
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-ia.fr")
    if not (smtp_host and smtp_user and smtp_pass):
        logger.warning("[BackupExt] SMTP non configure, alerte non envoyee.")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, [recipient], msg.as_string())
        logger.info(f"[BackupExt] Alerte mail envoyee a {recipient}")
    except Exception as e:
        logger.error(f"[BackupExt] Echec envoi alerte mail: {e}")


def _run_backup_external_inner(force: bool = False) -> dict:
    """
    Implementation interne de l orchestrateur du backup externe.

    NE PAS APPELER DIRECTEMENT depuis le scheduler ou les endpoints.
    Utiliser run_backup_external() (le wrapper avec timeout) a la place.

    force=True : ignore le check de configuration et tente quand meme.
                 (utile pour debug)

    Retourne {ok: bool, ...details}.
    """
    global _consecutive_failures
    started_at = datetime.now(timezone.utc)
    logger.info(f"[BackupExt] === DEBUT backup externe {started_at.isoformat()} ===")

    # Pre-checks rapides
    from app.crypto_backup import is_configured as backup_crypto_configured
    if not force and not backup_crypto_configured():
        return {"ok": False, "error": "BACKUP_ENCRYPTION_KEY non configuree"}
    if not force and _get_drive_service() is None:
        return {"ok": False, "error": "Drive client non disponible (SA JSON ?)"}

    try:
        # 1. pg_dump (retourne tuple bytes + format pour le manifest)
        logger.info("[BackupExt] 1/5 Generation pg_dump...")
        dump_bytes, dump_format = _generate_pg_dump()
        # 2. Secrets
        logger.info("[BackupExt] 2/5 Collecte secrets...")
        secrets = _collect_secrets()
        # 3. Archive (le format guide le nom du fichier dump dans le tar.gz)
        logger.info("[BackupExt] 3/5 Creation archive tar.gz...")
        archive_bytes, manifest = _create_archive(dump_bytes, secrets, dump_format)
        # 4. Chiffrement
        logger.info("[BackupExt] 4/5 Chiffrement Fernet...")
        from app.crypto_backup import encrypt_bytes
        encrypted = encrypt_bytes(archive_bytes)
        # 5. Upload
        ts_filename = started_at.strftime("%Y-%m-%d_%H-%M")
        filename = f"{BACKUP_FILENAME_PREFIX}{ts_filename}.tar.gz.enc"
        logger.info(f"[BackupExt] 5/5 Upload Drive : {filename}...")
        upload_result = _upload_to_drive(encrypted, filename)
        # 6. Rotation (silencieuse en cas d echec)
        try:
            keep = int(os.getenv("BACKUP_KEEP_DAYS", str(DEFAULT_KEEP_DAYS)))
            rotation = _rotate_old_backups(keep_days=keep)
        except Exception as e:
            logger.warning(f"[BackupExt] Rotation echec (non bloquant): {e}")
            rotation = {"error": str(e)}

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        _consecutive_failures = 0
        result = {
            "ok": True,
            "filename": filename,
            "drive_file_id": upload_result.get("id"),
            "encrypted_size_bytes": len(encrypted),
            "dump_size_bytes": manifest["dump_size_bytes"],
            "dump_format": dump_format,
            "elapsed_seconds": round(elapsed, 1),
            "rotation": rotation,
            "manifest": manifest,
        }
        logger.info(f"[BackupExt] === SUCCES en {elapsed:.1f}s : {filename} ===")
        return result
    except Exception as e:
        _consecutive_failures += 1
        logger.error(f"[BackupExt] ECHEC #{_consecutive_failures} : {e}", exc_info=True)
        if _consecutive_failures >= 2:
            _send_alert_mail(
                subject=f"[Raya] ALERTE backup externe - {_consecutive_failures} echecs consecutifs",
                body=f"Le backup nocturne externe a echoue {_consecutive_failures} fois "
                     f"de suite.\n\nDernier echec : {e}\n\n"
                     f"Verifier Railway logs + Drive Saiyan Backups.",
            )
        return {"ok": False, "error": str(e)[:500],
                "consecutive_failures": _consecutive_failures}


def run_backup_external(force: bool = False, timeout_sec: int = 600) -> dict:
    """
    Orchestrateur principal du backup externe AVEC TIMEOUT.

    Wrapper autour de _run_backup_external_inner qui ajoute un timeout
    global pour eviter qu un backup bug ne reste bloque indefiniment
    (typiquement si Drive ou DB ne repond pas).

    timeout_sec : duree maxi du backup en secondes (def 600 = 10 min).
                  Si depasse, on cancel proprement, on incremente le compteur
                  d echecs, et on alerte par mail si 2 echecs consecutifs.

    Pourquoi ThreadPoolExecutor plutot que signal.alarm :
    - signal.alarm marche QUE dans le thread principal (KO car APScheduler
      tourne les jobs dans des threads workers)
    - ThreadPoolExecutor est le pattern Python standard pour timeout, marche
      partout, propre, ne s embete pas avec APScheduler.

    Note importante : un thread Python ne peut pas etre kill de force
    (limitation de l interpreteur). Donc en cas de timeout, le thread du
    backup continue a tourner en arriere-plan jusqu a ce qu il termine ou
    plante. Mais on a deja rendu la main au scheduler avec un resultat
    d echec, et le compteur d echecs est correctement incremente.

    Appele par le scheduler nocturne et par /admin/backup/external/run.

    Retourne {ok: bool, ...details} comme _run_backup_external_inner, plus :
    - Si timeout : {ok: false, error: "timeout XXXs", consecutive_failures: N}
    """
    import concurrent.futures

    global _consecutive_failures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_backup_external_inner, force=force)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            _consecutive_failures += 1
            logger.error(
                f"[BackupExt] TIMEOUT apres {timeout_sec}s "
                f"(echec #{_consecutive_failures})"
            )
            if _consecutive_failures >= 2:
                _send_alert_mail(
                    subject=f"[Raya] ALERTE backup externe TIMEOUT - "
                            f"{_consecutive_failures} echecs consecutifs",
                    body=f"Backup nocturne externe a TIMEOUT apres "
                         f"{timeout_sec} secondes.\n\n"
                         f"Causes possibles :\n"
                         f"- Drive ou DB ne repond pas\n"
                         f"- DB devenue trop grosse\n"
                         f"- Reseau Railway sature\n"
                         f"- Bug recent dans le code\n\n"
                         f"Verifier Railway logs + Drive Saiyan Backups."
                )
            return {
                "ok": False,
                "error": f"timeout {timeout_sec}s",
                "consecutive_failures": _consecutive_failures,
            }


# ─── ENDPOINTS ADMIN ───
# Pattern calque sur app/backup.py : router dans le meme fichier que la logique.
# Tous les endpoints sont proteges par require_super_admin (Guillaume seul).

from fastapi import APIRouter, Depends, HTTPException
from app.routes.deps import require_super_admin

router = APIRouter(tags=["backup_external"])


@router.get("/admin/backup/external/health")
def backup_external_health():
    """
    Verifie la configuration sans rien declencher.
    Utile pour valider qu apres deploiement les variables Railway sont OK.
    Pas de require_super_admin pour pouvoir le ping depuis curl en debug.
    Reponse safe : pas de valeur sensible exposee.
    """
    from app.crypto_backup import is_configured as backup_crypto_ok
    drive = _get_drive_service()
    folder_id = os.getenv("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "").strip()
    return {
        "backup_encryption_key_configured": backup_crypto_ok(),
        "drive_service_account_configured": drive is not None,
        "drive_folder_id_configured": bool(folder_id),
        "drive_folder_id_prefix": folder_id[:6] + "..." if folder_id else None,
        "alert_email": os.getenv("BACKUP_ALERT_EMAIL", "admin@raya-ia.fr"),
        "keep_days": int(os.getenv("BACKUP_KEEP_DAYS", str(DEFAULT_KEEP_DAYS))),
        "scheduler_enabled": os.getenv("SCHEDULER_BACKUP_EXTERNAL_ENABLED", "true"),
    }


@router.post("/admin/backup/external/run")
def backup_external_run_manual(user: dict = Depends(require_super_admin)):
    """
    Declenche un backup externe manuel. Reserve super_admin (Guillaume).

    Utile pour :
    - Test apres deploiement
    - Backup ponctuel avant operation risquee (migration, refacto)
    - Verification que tout marche sans attendre 3h du matin

    Reponse : dict avec ok, filename, drive_file_id, sizes, manifest, etc.
    """
    result = run_backup_external(force=False)
    if not result.get("ok"):
        raise HTTPException(
            status_code=500,
            detail=f"Backup echec : {result.get('error', 'unknown')}",
        )
    return result


@router.get("/admin/backup/external/list")
def backup_external_list(user: dict = Depends(require_super_admin)):
    """
    Liste les backups presents sur le Shared Drive Saiyan Backups.
    Reserve super_admin. Utile pour audit visuel + verifier rotation.
    """
    try:
        backups = list_backups_on_drive()
        return {"ok": True, "count": len(backups), "backups": backups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur liste : {e}")


@router.get("/admin/backup/external/diagnose")
def backup_external_diagnose(user: dict = Depends(require_super_admin)):
    """
    Endpoint de diagnostic pour debug pg_dump et autres binaires Nix.
    Reserve super_admin (Guillaume).

    Utile pour comprendre :
    - Si pg_dump est dans le PATH (shutil.which)
    - Quelle est la version de pg_dump si dispo
    - Quel est le PATH du process Python
    - Quelles entrees /nix/store contiennent "postgresql"

    A garder car utile pour debug futur de tout binaire externe.
    """
    import shutil
    import sys

    out = {
        "python_version": sys.version,
        "path_env": os.environ.get("PATH", ""),
        "which_pg_dump": shutil.which("pg_dump"),
        "which_psql": shutil.which("psql"),
        "pg_dump_version": None,
        "pg_dump_error": None,
        "nix_store_postgresql": None,
        "nix_store_error": None,
        "nix_store_total_entries": None,
    }

    # 1. Tenter pg_dump --version si binaire trouve
    if out["which_pg_dump"]:
        try:
            r = subprocess.run(
                [out["which_pg_dump"], "--version"],
                capture_output=True,
                timeout=5,
            )
            out["pg_dump_version"] = r.stdout.decode(errors="replace").strip()
        except Exception as e:
            out["pg_dump_error"] = str(e)

    # 2. Lister /nix/store pour voir si postgresql est installe
    try:
        if os.path.isdir("/nix/store"):
            all_entries = os.listdir("/nix/store")
            out["nix_store_total_entries"] = len(all_entries)
            pg_entries = [
                e for e in all_entries if "postgresql" in e.lower()
            ]
            out["nix_store_postgresql"] = sorted(pg_entries)[:30]
        else:
            out["nix_store_postgresql"] = "not_a_directory"
    except Exception as e:
        out["nix_store_error"] = str(e)

    return out
