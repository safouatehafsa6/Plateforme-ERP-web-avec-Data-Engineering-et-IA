from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.db import pool_central
from app.security.audit import journaliser
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
def suspendre_abonnement(abonnement_id: int, request: Request, admin: dict = Depends(exiger_super_admin)):
    return _changer_statut_abonnement(abonnement_id, "suspendu", admin, request)


@router.post("/abonnements/{abonnement_id}/reactiver")
def reactiver_abonnement(abonnement_id: int, request: Request, admin: dict = Depends(exiger_super_admin)):
    return _changer_statut_abonnement(abonnement_id, "actif", admin, request)


def _changer_statut_abonnement(abonnement_id: int, nouveau_statut: str, admin: dict | None = None, request=None):
    """Change le statut d'un abonnement. Une SUSPENSION est effective
    immediatement : le login refuse l'entreprise (voir routers/auth.py) et
    toutes ses sessions ouvertes (internes et externes) sont revoquees."""
    sessions_fermees = 0
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE abonnement SET statut = %s WHERE id = %s RETURNING id, entreprise_id",
                (nouveau_statut, abonnement_id),
            )
            ligne = cur.fetchone()
            if not ligne:
                conn.rollback()
                return JSONResponse(status_code=404, content={"message": "Abonnement introuvable."})
            entreprise_id = ligne[1]

            if nouveau_statut == "suspendu":
                # Seul l'abonnement COURANT (le plus recent) gouverne l'acces.
                cur.execute("SELECT MAX(id) FROM abonnement WHERE entreprise_id = %s", (entreprise_id,))
                if cur.fetchone()[0] == abonnement_id:
                    cur.execute(
                        "UPDATE session_utilisateur SET revoquee_le = NOW(), "
                        "motif_revocation = 'entreprise_suspendue' "
                        "WHERE entreprise_id = %s AND revoquee_le IS NULL",
                        (str(entreprise_id),),
                    )
                    sessions_fermees = cur.rowcount
        conn.commit()
    finally:
        pool_central.putconn(conn)

    journaliser(
        "entreprise_suspendue" if nouveau_statut == "suspendu" else "entreprise_reactivee",
        gravite="avertissement", succes=True, type_compte="plateforme",
        utilisateur_id=(admin or {}).get("id"), email=(admin or {}).get("email"),
        entreprise_id=entreprise_id, request=request,
        acteur_email=(admin or {}).get("email"), details={"nb": sessions_fermees},
    )
    return {
        "message": f"Abonnement mis à jour : {nouveau_statut}.",
        "sessionsFermees": sessions_fermees,
    }
