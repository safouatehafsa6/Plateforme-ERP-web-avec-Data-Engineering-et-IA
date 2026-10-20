from fastapi import APIRouter, Depends, HTTPException

from app.db import pool_central
from app.security.auth_dependency import utilisateur_connecte, exiger_role_admin

# Sessions de la personne connectee (tous profils : plateforme, interne, externe)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Gestion par l'Administrateur de l'entreprise
router_admin = APIRouter(prefix="/api/admin/sessions", tags=["sessions-admin"])

COLONNES = (
    "jti, systeme, navigateur, appareil, adresse_ip, cree_le, "
    "derniere_activite, expire_le, email, type_compte, utilisateur_id"
)
ACTIVE = "revoquee_le IS NULL AND expire_le > NOW()"


def _lire(requete: str, params: tuple) -> list:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(requete, params)
            return cur.fetchall()
    finally:
        pool_central.putconn(conn)


def _ecrire(requete: str, params: tuple) -> int:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(requete, params)
            nombre = cur.rowcount
        conn.commit()
        return nombre
    finally:
        pool_central.putconn(conn)


def _formater(ligne, jti_courant: str) -> dict:
    return {
        "id": ligne[0],
        "systeme": ligne[1],
        "navigateur": ligne[2],
        "appareil": ligne[3],
        "adresseIp": ligne[4],
        "creeLe": ligne[5].isoformat(),
        "derniereActivite": ligne[6].isoformat(),
        "expireLe": ligne[7].isoformat(),
        "email": ligne[8],
        "typeCompte": ligne[9],
        "utilisateurId": ligne[10],
        "courante": ligne[0] == jti_courant,
    }


# ---------------------------------------------------------------------
# Mes appareils
# ---------------------------------------------------------------------

@router.get("")
def lister_mes_sessions(utilisateur: dict = Depends(utilisateur_connecte)):
    lignes = _lire(
        f"""
        SELECT {COLONNES} FROM session_utilisateur
        WHERE type_compte = %s AND utilisateur_id = %s AND {ACTIVE}
        ORDER BY derniere_activite DESC
        """,
        (utilisateur["type"], str(utilisateur["id"])),
    )
    return {"sessions": [_formater(l, utilisateur["jti"]) for l in lignes]}


@router.post("/deconnexion")
def deconnexion(utilisateur: dict = Depends(utilisateur_connecte)):
    """Deconnexion reelle : le jeton devient inutilisable cote serveur."""
    _ecrire(
        "UPDATE session_utilisateur SET revoquee_le = NOW(), motif_revocation = 'deconnexion' "
        "WHERE jti = %s AND revoquee_le IS NULL",
        (utilisateur["jti"],),
    )
    return {"message": "Déconnexion effectuée."}


@router.post("/autres/revoquer")
def revoquer_les_autres_sessions(utilisateur: dict = Depends(utilisateur_connecte)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_utilisateur'
        WHERE type_compte = %s AND utilisateur_id = %s AND jti <> %s AND revoquee_le IS NULL
        """,
        (utilisateur["type"], str(utilisateur["id"]), utilisateur["jti"]),
    )
    return {"message": f"{nombre} session(s) fermée(s).", "fermees": nombre}


@router.delete("/{jti}")
def revoquer_ma_session(jti: str, utilisateur: dict = Depends(utilisateur_connecte)):
    # Le filtre sur type + id empeche de fermer la session de quelqu'un d'autre.
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_utilisateur'
        WHERE jti = %s AND type_compte = %s AND utilisateur_id = %s AND revoquee_le IS NULL
        """,
        (jti, utilisateur["type"], str(utilisateur["id"])),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Session introuvable ou déjà fermée.")
    return {"message": "Session fermée."}


# ---------------------------------------------------------------------
# Administration (Admin de l'entreprise : uniquement SON entreprise)
# ---------------------------------------------------------------------

def _entreprise_admin(admin: dict) -> str:
    entreprise_id = admin.get("entrepriseId")
    if entreprise_id is None:
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")
    return str(entreprise_id)


@router_admin.get("")
def lister_sessions_entreprise(admin: dict = Depends(exiger_role_admin)):
    lignes = _lire(
        f"""
        SELECT {COLONNES} FROM session_utilisateur
        WHERE entreprise_id = %s AND {ACTIVE}
        ORDER BY derniere_activite DESC
        """,
        (_entreprise_admin(admin),),
    )
    return {"sessions": [_formater(l, admin["jti"]) for l in lignes]}


@router_admin.delete("/utilisateur/{utilisateur_id}")
def revoquer_toutes_sessions_utilisateur(
    utilisateur_id: str,
    type_compte: str = "interne",
    admin: dict = Depends(exiger_role_admin),
):
    if type_compte not in ("interne", "externe"):
        raise HTTPException(status_code=400, detail="Type de compte invalide.")

    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_admin'
        WHERE entreprise_id = %s AND type_compte = %s AND utilisateur_id = %s
          AND revoquee_le IS NULL
        """,
        (_entreprise_admin(admin), type_compte, utilisateur_id),
    )
    return {"message": f"{nombre} session(s) fermée(s).", "fermees": nombre}


@router_admin.delete("/{jti}")
def revoquer_session_entreprise(jti: str, admin: dict = Depends(exiger_role_admin)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_admin'
        WHERE jti = %s AND entreprise_id = %s AND revoquee_le IS NULL
        """,
        (jti, _entreprise_admin(admin)),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Session introuvable ou déjà fermée.")
    return {"message": "Session fermée."}
