"""Polling adaptatif jour/nuit.

Module ajoute le 06/05/2026 (Etape 5 refonte connexions). But : reduire
la charge sur les APIs et les workers Railway en dehors des heures
ouvrees, sans degrader la reactivite quand Guillaume bosse.

PRINCIPE :
- En heures ouvrees (lun-ven 7h30-18h30 heure de Paris) :
  on polle toutes les 5 min (= comportement actuel)
- En dehors (nuit + weekend + jours feries traites comme normaux) :
  on polle toutes les 30 min seulement (charge -83%)

IMPLEMENTATION :
On ne touche PAS au scheduler APScheduler (toujours en
IntervalTrigger 5 min). Les jobs eux-memes appellent
should_skip_poll_now() au debut de leur boucle sur chaque connexion :
- En heures ouvrees : retourne False -> on polle toujours
- Hors ouvrees : retourne True si dernier poll < 30 min -> on skip

AVANTAGES :
- 0 risque de casser le scheduler
- Reversible : si on retire les checks, retour comportement initial
- Granulaire : chaque connexion gere son propre rythme

ETAPE 6 a venir : ajouter la detection "user actif" qui force le mode
5 min meme la nuit si Guillaume bosse, plus le tool refresh_connections
expose a Raya pour qu elle force un poll quand elle voit qu une question
necessite des donnees fraiches.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    PARIS_TZ = ZoneInfo("Europe/Paris")
except Exception:
    # Fallback en cas de probleme zoneinfo (rare, mais on ne casse pas
    # le service pour ca) : on considere l heure UTC comme Paris (-2h
    # ce qui shifte les heures ouvrees mais reste fonctionnel)
    PARIS_TZ = timezone.utc

logger = logging.getLogger("raya.polling_schedule")

# Lundi 0 .. Dimanche 6
BUSINESS_DAYS = (0, 1, 2, 3, 4)
BUSINESS_HOUR_START = (7, 30)  # 7h30
BUSINESS_HOUR_END = (18, 30)   # 18h30

INTERVAL_BUSINESS_S = 300       # 5 min
INTERVAL_OFF_HOURS_S = 1800     # 30 min


def is_business_hours(now: Optional[datetime] = None) -> bool:
    """True si maintenant est en heures ouvrees Paris (lun-ven 7h30-18h30).

    Args:
        now: datetime de reference (UTC ou aware). Si None, utilise
             datetime.now(timezone.utc).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        # naive -> on considere UTC (cas Postgres qui retourne naive)
        now = now.replace(tzinfo=timezone.utc)

    paris = now.astimezone(PARIS_TZ)

    if paris.weekday() not in BUSINESS_DAYS:
        return False

    h, m = paris.hour, paris.minute
    if (h, m) < BUSINESS_HOUR_START:
        return False
    if (h, m) >= BUSINESS_HOUR_END:
        return False
    return True


def get_expected_poll_interval(now: Optional[datetime] = None) -> int:
    """Retourne l intervalle de poll attendu en secondes.

    Utilise par connection_health._compute_effective_status pour
    calculer les seuils green/amber/red de facon dynamique selon
    l heure (ex: la nuit, un silence de 45 min n est pas anormal).
    """
    return INTERVAL_BUSINESS_S if is_business_hours(now) else INTERVAL_OFF_HOURS_S


def should_skip_poll_now(connection_id: int,
                         now: Optional[datetime] = None) -> bool:
    """Vrai si le job de polling doit skipper ce cycle pour connection_id.

    Logique :
    - En heures ouvrees Paris : retourne toujours False (on polle)
    - Hors ouvrees : on skip si dernier poll attempt < 30 min
      (l intervalle attendu hors ouvrees), pour respecter le rythme
      d 1 poll / 30 min meme si APScheduler appelle le job toutes
      les 5 min.

    Args:
        connection_id: ID de la connexion (tenant_connections.id)
        now: heure de reference (debug/test). Sinon NOW.

    Returns:
        True si on doit return early dans le job, False sinon.
    """
    # En heures ouvrees, jamais de skip
    if is_business_hours(now):
        return False

    # Hors heures ouvrees : on regarde quand etait le dernier poll
    expected_s = INTERVAL_OFF_HOURS_S

    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # On utilise last_poll_attempt_at (et pas last_successful_poll_at)
        # pour ne pas retenter en boucle si une boite ne marche plus :
        # 1 tentative ratee toutes les 30 min suffit a detecter la panne.
        c.execute("""
            SELECT EXTRACT(EPOCH FROM (NOW() - last_poll_attempt_at))
            FROM connection_health
            WHERE connection_id = %s
        """, (connection_id,))
        row = c.fetchone()
        if not row or row[0] is None:
            return False  # jamais polle -> on polle pour initialiser
        seconds_since = float(row[0])
        # Si la derniere tentative est plus recente que l intervalle off-hours,
        # on skip (le scheduler reviendra dans 5 min, on retentera plus tard)
        return seconds_since < expected_s
    except Exception as e:
        logger.warning(
            "[PollingSchedule] should_skip check failed for conn=%s : %s",
            connection_id, str(e)[:200])
        # En cas de doute : on polle (mieux louper le throttle qu une
        # vraie alerte / qu un mail pas detecte)
        return False
    finally:
        if conn: conn.close()
