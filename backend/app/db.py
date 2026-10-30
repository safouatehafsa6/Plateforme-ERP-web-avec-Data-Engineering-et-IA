import os
import threading
import time

from psycopg2 import extensions, pool

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")
DB_CENTRAL_NAME = os.getenv("DB_CENTRAL_NAME", "erp_db")

POOL_CENTRAL_MAX = int(os.getenv("POOL_CENTRAL_MAX", "20"))
POOL_ENTREPRISE_MAX = int(os.getenv("POOL_ENTREPRISE_MAX", "10"))
POOL_ATTENTE_MAX = float(os.getenv("POOL_ATTENTE_MAX", "5"))


class PoolParesseux:
    """Pool de connexions PostgreSQL, thread-safe, cree a la premiere utilisation.

    - threadpool FastAPI = plusieurs threads : on utilise ThreadedConnectionPool ;
    - si le pool est sature, on attend un peu au lieu d'echouer immediatement ;
    - une connexion rendue avec une transaction ouverte est annulee (rollback)
      pour ne jamais contaminer la requete suivante.
    L'interface reste celle d'un pool psycopg2 (getconn, putconn, closeall...).
    """

    def __init__(self, maxconn: int, attente_max: float = POOL_ATTENTE_MAX, **connexion):
        self._maxconn = maxconn
        self._attente_max = attente_max
        self._connexion = connexion
        self._pool = None
        self._verrou = threading.Lock()

    def _obtenir_pool(self):
        if self._pool is None:
            with self._verrou:
                if self._pool is None:
                    self._pool = pool.ThreadedConnectionPool(1, self._maxconn, **self._connexion)
        return self._pool

    def getconn(self):
        p = self._obtenir_pool()
        fin = time.monotonic() + self._attente_max
        while True:
            try:
                return p.getconn()
            except pool.PoolError:
                if time.monotonic() >= fin:
                    raise
                time.sleep(0.05)

    def putconn(self, conn, *args, **kwargs):
        try:
            if not conn.closed and conn.status != extensions.STATUS_READY:
                conn.rollback()
        except Exception:
            pass
        return self._obtenir_pool().putconn(conn, *args, **kwargs)

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return getattr(self._obtenir_pool(), nom)


# Pool permanent vers la base centrale.
pool_central = PoolParesseux(POOL_CENTRAL_MAX, host=DB_HOST, port=DB_PORT, user=DB_USER,
                             password=DB_PASSWORD, dbname=DB_CENTRAL_NAME)

# Cache des pools vers les bases entreprise (une base = un pool reutilise, cree
# a la demande selon le mecanisme de routage multi-tenant).
_pools_entreprise = {}
_verrou_pools = threading.Lock()


def get_pool_entreprise(nom_base: str):
    existant = _pools_entreprise.get(nom_base)
    if existant is not None:
        return existant
    with _verrou_pools:
        existant = _pools_entreprise.get(nom_base)
        if existant is None:
            existant = PoolParesseux(POOL_ENTREPRISE_MAX, host=DB_HOST, port=DB_PORT, user=DB_USER,
                                     password=DB_PASSWORD, dbname=nom_base)
            _pools_entreprise[nom_base] = existant
        return existant
