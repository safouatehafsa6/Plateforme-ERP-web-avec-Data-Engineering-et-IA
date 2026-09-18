from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db import pool_central
from app.security.jwt_utils import exiger_super_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/entreprises")
def lister_entreprises(_: dict = Depends(exiger_super_admin)):
    """Vue d'ensemble pour le Super Admin : chaque entreprise avec son
    abonnement le plus récent — correspond directement au cas d'utilisation
    'Gérer abonnements et licences' du diagramme de cas d'utilisation."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.id, e.type_compte, e.nom, e.email_contact, e.statut AS statut_compte,
                    a.id AS abonnement_id, a.type_plan, a.statut AS statut_abonnement,
                    a.date_debut, a.date_fin, a.montant
                FROM entreprise e
                LEFT JOIN LATERAL (
                    SELECT * FROM abonnement
                    WHERE abonnement.entreprise_id = e.id
                    ORDER BY id DESC LIMIT 1
                ) a ON true
                ORDER BY e.date_creation DESC
            """)
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]
    finally:
        pool_central.putconn(conn)

    # Conversion des dates en texte pour la sérialisation JSON.
    for ligne in lignes:
        for cle in ("date_debut", "date_fin"):
            if ligne.get(cle):
                ligne[cle] = ligne[cle].isoformat()

    return {"entreprises": lignes}


@router.post("/abonnements/{abonnement_id}/suspendre")
def suspendre_abonnement(abonnement_id: int, _: dict = Depends(exiger_super_admin)):
    return _changer_statut_abonnement(abonnement_id, "suspendu")


@router.post("/abonnements/{abonnement_id}/reactiver")
def reactiver_abonnement(abonnement_id: int, _: dict = Depends(exiger_super_admin)):
    return _changer_statut_abonnement(abonnement_id, "actif")


def _changer_statut_abonnement(abonnement_id: int, nouveau_statut: str):
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE abonnement SET statut = %s WHERE id = %s RETURNING id", (nouveau_statut, abonnement_id))
            if not cur.fetchone():
                return JSONResponse(status_code=404, content={"message": "Abonnement introuvable."})
        conn.commit()
    finally:
        pool_central.putconn(conn)

    return {"message": f"Abonnement mis à jour : {nouveau_statut}."}
