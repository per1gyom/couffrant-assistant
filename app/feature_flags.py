"""
Système de feature flags par tenant.

Phase 1 (30/04/2026 nuit) : backend pur, sans UI.
- Tenant-level uniquement (pas user-level)
- Cache en mémoire avec TTL 60s pour éviter de hammer la DB
- Fallback sur le default_enabled du registry si pas d override tenant
- Décorateur require_feature() pour protéger un endpoint
- Helper is_feature_enabled() pour test inline dans le code
- Helper get_features_for_tenant() pour le front (/me/features)

Workflow d'utilisation :
  1. Code applicatif appelle is_feature_enabled(tenant_id, "audio_capture")
  2. Module check le cache (TTL 60s par paire tenant/feature)
  3. Si cache miss, query DB :
     a) tenant_features (override) → si ligne, retourne enabled
     b) feature_registry (default) → retourne default_enabled
     c) Si feature pas dans registry → retourne False (sécurité)
  4. Cache le résultat 60s

Pour Phase 2-3, le super_admin pourra :
  - Lister les features (GET /admin/features)
  - Toggler une feature pour un tenant (POST /admin/tenants/{id}/features/{key})
  - Voir l état actuel par tenant (UI dans panel super_admin)
"""
import time
from functools import wraps
from typing import Callable, Optional

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.feature_flags")


# ─── CACHE ─────────────────────────────────────────────────────────────

# Cache simple : {(tenant_id, feature_key): (enabled, timestamp)}
# TTL court (60s) pour permettre les toggles UI quasi-immédiats.
_CACHE: dict = {}
_CACHE_TTL_SECONDS = 60


def _cache_get(tenant_id: str, feature_key: str) -> Optional[bool]:
    """Lit le cache pour (tenant_id, feature_key). None si miss/expire."""
    key = (tenant_id, feature_key)
    entry = _CACHE.get(key)
    if not entry:
        return None
    enabled, ts = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        # Expiré
        _CACHE.pop(key, None)
        return None
    return enabled


def _cache_set(tenant_id: str, feature_key: str, enabled: bool) -> None:
    """Écrit le cache pour (tenant_id, feature_key)."""
    _CACHE[(tenant_id, feature_key)] = (enabled, time.time())


def invalidate_cache(tenant_id: Optional[str] = None) -> None:
    """Vide le cache pour un tenant (ou tout si tenant_id=None).

    Appelé après un toggle via l'UI super_admin (Phase 2) pour que
    la nouvelle valeur soit immédiatement effective.
    """
    if tenant_id is None:
        _CACHE.clear()
        logger.info("[FeatureFlags] Cache global invalide")
    else:
        keys_to_remove = [k for k in _CACHE.keys() if k[0] == tenant_id]
        for k in keys_to_remove:
            _CACHE.pop(k, None)
        logger.info("[FeatureFlags] Cache invalide pour tenant=%s (%d entrees)", tenant_id, len(keys_to_remove))


# ─── LECTURE EN DB ─────────────────────────────────────────────────────


def _fetch_feature_state_db(tenant_id: str, feature_key: str) -> bool:
    """Lit l'état réel d'une feature pour un tenant en DB.

    Logique :
    1. Cherche un override dans tenant_features → si présent, retourne enabled
    2. Sinon cherche le default_enabled dans feature_registry → retourne ça
    3. Si feature absente du registry → retourne False (fail-safe)
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Etape 1 : override tenant
        c.execute(
            """
            SELECT enabled FROM tenant_features
            WHERE tenant_id = %s AND feature_key = %s
            """,
            (tenant_id, feature_key),
        )
        row = c.fetchone()
        if row is not None:
            return bool(row[0])

        # Etape 2 : default registry
        c.execute(
            """
            SELECT default_enabled, deprecated FROM feature_registry
            WHERE feature_key = %s
            """,
            (feature_key,),
        )
        row = c.fetchone()
        if row is None:
            # Feature pas dans le registry : fail-safe -> False
            logger.warning("[FeatureFlags] Feature inconnue : '%s' (fail-safe -> False)", feature_key)
            return False
        default_enabled, deprecated = row
        if deprecated:
            # Feature dépréciée : automatiquement OFF
            return False
        return bool(default_enabled)

    except Exception as e:
        logger.error("[FeatureFlags] _fetch_feature_state_db error: %s", str(e)[:200])
        # En cas d'erreur DB, on retourne True pour éviter de casser le service
        # (les features sont activees par defaut sur tous les tenants existants)
        return True
    finally:
        if conn:
            conn.close()


# ─── API PUBLIQUE ──────────────────────────────────────────────────────


def is_feature_enabled(tenant_id: str, feature_key: str) -> bool:
    """Renvoie True si la feature est activée pour le tenant.

    Logique de fallback :
      tenant_features (override) > feature_registry.default_enabled > False

    Cache 60s pour éviter de hammer la DB.

    Args:
      tenant_id : id du tenant (ex: 'couffrant_solar')
      feature_key : clé de la feature (ex: 'audio_capture')

    Returns:
      bool : True si activée, False sinon

    Examples:
      if is_feature_enabled(user["tenant_id"], "audio_capture"):
          # autoriser l upload audio
      else:
          raise HTTPException(403, "Feature non disponible sur votre forfait")
    """
    if not tenant_id or not feature_key:
        return False

    # 1. Check cache
    cached = _cache_get(tenant_id, feature_key)
    if cached is not None:
        return cached

    # 2. Fetch DB
    enabled = _fetch_feature_state_db(tenant_id, feature_key)

    # 3. Cache et retour
    _cache_set(tenant_id, feature_key, enabled)
    return enabled


def get_features_for_tenant(tenant_id: str) -> dict:
    """Renvoie le dict {feature_key: enabled} pour un tenant.

    Inclut TOUTES les features du registry (avec leur état effectif).
    Utile pour le front : appel /me/features au load, le front cache et
    masque les boutons des features désactivées.

    Returns:
      dict : {
        'audio_capture': True,
        'vesta_connector': False,
        ...
      }
    """
    if not tenant_id:
        return {}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Une seule query : LEFT JOIN registry vs tenant_features
        # Si pas d override, utilise default_enabled du registry
        c.execute(
            """
            SELECT
                r.feature_key,
                COALESCE(tf.enabled, r.default_enabled) AS effective_enabled,
                r.deprecated
            FROM feature_registry r
            LEFT JOIN tenant_features tf
                ON tf.tenant_id = %s
                AND tf.feature_key = r.feature_key
            WHERE r.deprecated = FALSE
            ORDER BY r.feature_key
            """,
            (tenant_id,),
        )
        rows = c.fetchall()
        return {row[0]: bool(row[1]) for row in rows}
    except Exception as e:
        logger.error("[FeatureFlags] get_features_for_tenant error: %s", str(e)[:200])
        return {}
    finally:
        if conn:
            conn.close()


def list_all_features() -> list:
    """Renvoie le catalogue complet des features (avec metadata).

    Pour le panel super_admin Phase 2.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT feature_key, label, description, category, default_enabled, deprecated
            FROM feature_registry
            ORDER BY category, feature_key
            """
        )
        cols = ["feature_key", "label", "description", "category", "default_enabled", "deprecated"]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception as e:
        logger.error("[FeatureFlags] list_all_features error: %s", str(e)[:200])
        return []
    finally:
        if conn:
            conn.close()


def set_tenant_feature(tenant_id: str, feature_key: str, enabled: bool, updated_by: str, notes: Optional[str] = None) -> bool:
    """Active/désactive une feature pour un tenant.

    Pour le panel super_admin Phase 2. Utilise UPSERT (INSERT ON CONFLICT).
    Invalide le cache pour ce tenant après l'opération.

    Returns:
      bool : True si succès, False sinon
    """
    if not tenant_id or not feature_key:
        return False

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Verifier que la feature existe dans le registry
        c.execute("SELECT 1 FROM feature_registry WHERE feature_key = %s", (feature_key,))
        if not c.fetchone():
            logger.warning("[FeatureFlags] set_tenant_feature : feature '%s' inexistante", feature_key)
            return False

        # UPSERT
        c.execute(
            """
            INSERT INTO tenant_features (tenant_id, feature_key, enabled, updated_by, notes, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, feature_key)
            DO UPDATE SET
                enabled = EXCLUDED.enabled,
                updated_by = EXCLUDED.updated_by,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """,
            (tenant_id, feature_key, enabled, updated_by, notes),
        )
        conn.commit()

        # Invalider le cache pour ce tenant
        invalidate_cache(tenant_id)

        logger.info(
            "[FeatureFlags] %s : feature '%s' -> %s (par %s)",
            tenant_id, feature_key, enabled, updated_by,
        )
        return True

    except Exception as e:
        logger.error("[FeatureFlags] set_tenant_feature error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if conn:
            conn.close()


# ─── DÉCORATEUR FASTAPI ────────────────────────────────────────────────


def require_feature(feature_key: str):
    """Décorateur FastAPI : requiert qu'une feature soit activée pour le tenant courant.

    À utiliser sur les endpoints qui dépendent d'une feature optionnelle.
    Le tenant_id est extrait de la session (request.session['tenant_id']).

    Usage:
        @router.post("/audio/upload")
        @require_feature("audio_capture")
        def upload_audio(request: Request, ...):
            ...

    Si la feature est désactivée : lève HTTPException 403 avec message clair.

    Note : pour utiliser ce décorateur, l endpoint DOIT avoir 'request: Request'
    en premier paramètre (FastAPI standard).
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Trouver l'objet Request dans les args/kwargs
            request = kwargs.get("request")
            if request is None:
                # Cherche dans les args positionnels
                for a in args:
                    if hasattr(a, "session"):  # heuristique : c'est probablement Request
                        request = a
                        break

            if request is None:
                # Pas de request -> on log et on laisse passer (cas test ?)
                logger.warning("[FeatureFlags] require_feature(%s) : pas de request, bypass", feature_key)
                return func(*args, **kwargs)

            tenant_id = request.session.get("tenant_id")
            if not tenant_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Non authentifié")

            if not is_feature_enabled(tenant_id, feature_key):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_disabled",
                        "feature_key": feature_key,
                        "message": "Cette fonctionnalité n'est pas disponible sur votre forfait. "
                                   "Contactez votre administrateur pour en savoir plus.",
                    },
                )

            return func(*args, **kwargs)

        return wrapper
    return decorator
