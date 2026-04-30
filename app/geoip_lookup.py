"""
Lookup IP -> pays via GeoLite2 City (MaxMind).

Base de donnees GeoLite2 telechargee gratuitement chez MaxMind au build
Docker (cf Dockerfile). Stockee dans /opt/geoip/GeoLite2-City.mmdb.

Comportement defensif :
- Si la base est absente (Dockerfile build sans cle) : tous les lookups
  retournent None (= pays inconnu), l app continue de tourner. Le LOT 4
  fonctionne en mode degrade : on detecte les IP nouvelles mais pas les
  changements de pays.
- Si geoip2 n est pas installe : meme comportement.
- Erreurs de lookup individuelles (IP invalide, IP privee) : silencieuses,
  retourne None.

Usage typique :
    country = lookup_country("8.8.8.8")  # -> "US"
    country = lookup_country("82.66.42.13")  # -> "FR"
    country = lookup_country("127.0.0.1")  # -> None (IP privee)
    country = lookup_country("invalid")  # -> None (silencieux)
"""
import os
from typing import Optional

from app.logging_config import get_logger

logger = get_logger("raya.geoip")


# Chemin fixe defini dans le Dockerfile
GEOIP_DB_PATH = os.getenv(
    "GEOIP_DB_PATH",
    "/opt/geoip/GeoLite2-City.mmdb",
)

# Reader lazy (singleton thread-safe par default dans geoip2)
_reader = None
_init_attempted = False


def _get_reader():
    """Singleton thread-safe pour la base GeoLite2.

    Lazy load : pas d acces fichier tant que la 1ere requete n arrive pas.
    Si la base est absente ou la lib non installee, retourne None pour
    toujours sans planter l app.
    """
    global _reader, _init_attempted

    if _init_attempted:
        return _reader

    _init_attempted = True

    # Verifier l existence du fichier
    if not os.path.isfile(GEOIP_DB_PATH):
        logger.warning(
            "[GeoIP] Base GeoLite2 absente a %s — mode degrade actif",
            GEOIP_DB_PATH,
        )
        return None

    # Charger geoip2 dynamiquement (evite crash si lib non installee)
    try:
        import geoip2.database  # type: ignore[import-not-found]
        _reader = geoip2.database.Reader(GEOIP_DB_PATH)
        logger.info("[GeoIP] Base GeoLite2 chargee depuis %s", GEOIP_DB_PATH)
        return _reader
    except ImportError:
        logger.warning("[GeoIP] Module geoip2 non installe — mode degrade")
        return None
    except Exception as e:
        logger.error("[GeoIP] Echec chargement base : %s", str(e)[:200])
        return None


def lookup_country(ip: Optional[str]) -> Optional[str]:
    """Renvoie le code pays ISO 2-lettres pour une IP, ou None.

    Returns None pour :
    - IP None ou vide
    - IP invalide (format)
    - IP privee/locale (127.0.0.1, 192.168.x.x, 10.x.x.x)
    - Lookup echoue (IP non trouvee dans la base)
    - Base GeoLite2 absente (mode degrade)
    """
    if not ip or not ip.strip():
        return None

    reader = _get_reader()
    if not reader:
        return None

    try:
        response = reader.city(ip.strip())
        country_iso = response.country.iso_code
        return country_iso
    except Exception:
        # AddressNotFoundError, ValueError, etc.
        # On reste silencieux : c est une situation normale (IP privee,
        # IP nouvelle, ou IP non trouvee dans la base de signature).
        return None


def lookup_country_and_city(ip: Optional[str]) -> dict:
    """Renvoie {country: 'FR', city: 'Paris', region: 'Ile-de-France'} ou {}.

    Pour les futurs besoins UI ("vous vous etes connecte depuis Paris").
    """
    if not ip or not ip.strip():
        return {}

    reader = _get_reader()
    if not reader:
        return {}

    try:
        r = reader.city(ip.strip())
        return {
            "country": r.country.iso_code,
            "city": r.city.name or "",
            "region": (r.subdivisions.most_specific.name if r.subdivisions else "") or "",
        }
    except Exception:
        return {}


def is_geoip_available() -> bool:
    """Renvoie True si la base GeoLite2 est chargee et utilisable."""
    return _get_reader() is not None
