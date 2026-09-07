import os
from psycopg2 import pool

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")
DB_CENTRAL_NAME = os.getenv("DB_CENTRAL_NAME", "erp_db")

# Pool de connexions permanent vers la base centrale.
pool_central = pool.SimpleConnectionPool(
    1, 10,
    host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
    dbname=DB_CENTRAL_NAME,
)

# Cache des pools de connexions vers les bases entreprise (une base = un
# pool réutilisé, créé à la demande selon le mécanisme de routage
# multi-tenant).
_pools_entreprise = {}


def get_pool_entreprise(nom_base: str):
    if nom_base in _pools_entreprise:
        return _pools_entreprise[nom_base]

    nouveau_pool = pool.SimpleConnectionPool(
        1, 5,
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        dbname=nom_base,
    )
    _pools_entreprise[nom_base] = nouveau_pool
    return nouveau_pool
