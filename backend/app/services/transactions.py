from contextlib import contextmanager

from app.db import get_pool_entreprise


@contextmanager
def transaction_entreprise(utilisateur: dict):
    """Curseur transactionnel sur la base de l'entreprise : commit si tout réussit, rollback sinon."""
    pool = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
