from fastapi import APIRouter, Depends
from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/comptabilite", tags=["comptabilite"])

def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])

@router.get("/synthese")
def synthese(utilisateur=Depends(exiger_permission("comptabilite", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT COALESCE(SUM(CASE WHEN statut='payee' THEN montant_total ELSE 0 END),0), COALESCE(SUM(CASE WHEN statut='impayee' THEN montant_total ELSE 0 END),0) FROM facture""")
            payees, impayees = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(montant_total),0) FROM achat WHERE statut <> 'annulee'")
            achats = cur.fetchone()[0]
            return {"factures_payees": payees, "factures_impayees": impayees, "total_achats": achats}
    finally:
        pool.putconn(conn)
