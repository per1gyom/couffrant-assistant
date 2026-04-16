"""
Base de données PostgreSQL — pool de connexions + schéma + migrations.

Pool de connexions (ThreadedConnectionPool, 2-8 connexions) :
  - get_pg_conn() retourne un wrapper transparent _PooledConn
  - conn.close() remet la connexion dans le pool (pas de fermeture TCP)
  - Fallback automatique sur connexion directe si le pool est indisponible
  - Zéro changement requis dans les fichiers appelants

Migrations SQL : voir app/database_migrations.py
Ajouter les nouvelles migrations dans ce fichier uniquement.
"""
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from app.config import DATABASE_URL
from app.logging_config import get_logger

logger = get_logger("raya.db")


# ─── POOL DE CONNEXIONS ───

_pool: ThreadedConnectionPool = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """Initialise le pool une seule fois (lazy, thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = ThreadedConnectionPool(2, 8, DATABASE_URL)
                except Exception as e:
                    logger.warning("[DB] Pool non initialisé (%s) — fallback connexions directes", e)
    return _pool


class _PooledConn:
    """
    Wrapper transparent autour d'une connexion psycopg2.
    close() retourne la connexion au pool au lieu de la fermer (TCP maintenu).
    """

    def __init__(self, conn, pool):
        self.__dict__["_conn"] = conn
        self.__dict__["_pool"] = pool

    def __getattr__(self, name):
        return getattr(self.__dict__["_conn"], name)

    def cursor(self, *args, **kwargs):
        return self.__dict__["_conn"].cursor(*args, **kwargs)

    def commit(self):
        return self.__dict__["_conn"].commit()

    def rollback(self):
        return self.__dict__["_conn"].rollback()

    def close(self):
        pool = self.__dict__.get("_pool")
        conn = self.__dict__.get("_conn")
        if pool and conn:
            try:
                pool.putconn(conn)
                return
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_pg_conn():
    pool = _get_pool()
    if pool:
        try:
            conn = pool.getconn()
            if conn:
                return _PooledConn(conn, pool)
        except Exception as e:
            logger.warning("[DB] Pool getconn() échoué (%s) — connexion directe", e)
    return psycopg2.connect(DATABASE_URL)


def close_pool():
    global _pool
    if _pool:
        try:
            _pool.closeall()
        except Exception:
            pass
        _pool = None


# ─── SCHÉMA + MIGRATIONS ───

def init_postgres():
    """Crée les tables (idempotent) puis applique toutes les migrations."""
    from app.database_schema import get_schema_statements
    from app.database_migrations import MIGRATIONS
    conn = get_pg_conn()
    c = conn.cursor()
    # 1. Schéma (CREATE TABLE IF NOT EXISTS)
    for stmt in get_schema_statements():
        try:
            c.execute(stmt)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
    # 2. Migrations (ALTER TABLE, UPDATE, CREATE INDEX…)
    for mig in MIGRATIONS:
        try:
            c.execute(mig)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
    conn.close()
    from app.logging_config import get_logger as _gl
    _gl("raya.db").info("[DB] Schema + migrations initialises")
