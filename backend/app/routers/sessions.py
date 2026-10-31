from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import pool_central
from app.security.audit import journaliser
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
COL_EVT = (
    "id, cree_le, type_evenement, gravite, succes, email, host(adresse_ip), "
    "systeme, navigateur, acteur_email, details"
)


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


def _formater_evt(l) -> dict:
    return {
        "id": l[0], "creeLe": l[1].isoformat(), "type": l[2], "gravite": l[3],
        "succes": l[4], "email": l[5], "adresseIp": l[6], "systeme": l[7],
        "navigateur": l[8], "acteur": l[9], "details": l[10],
    }


def _journal(type_evt, u, request, gravite="info", details=None):
    journaliser(
        type_evt, gravite=gravite, type_compte=u.get("type"), utilisateur_id=u.get("id"),
        email=u.get("email"), entreprise_id=u.get("entrepriseId"), jti=u.get("jti"),
        request=request, details=details,
    )


def _evenements(base_sql, base_params, type_evt, gravite, email, limit, avant):
    where, params = [base_sql], list(base_params)
    if type_evt:
        where.append("type_evenement = %s")
        params.append(type_evt)
    if gravite:
        where.append("gravite = %s")
        params.append(gravite)
    if email:
        where.append("email = LOWER(%s)")
        params.append(email)
    if avant:
        where.append("id < %s")
        params.append(avant)
    limite = max(1, min(int(limit), 200))
    lignes = _lire(
        f"SELECT {COL_EVT} FROM evenement_securite WHERE {' AND '.join(where)} "
        "ORDER BY id DESC LIMIT %s",
        tuple(params + [limite]),
    )
    return {"evenements": [_formater_evt(l) for l in lignes]}


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


@router.get("/evenements")
def mes_evenements(
    limit: int = 20,
    avant: int | None = None,
    type: str | None = None,
    utilisateur: dict = Depends(utilisateur_connecte),
):
    """Journal de securite de la personne connectee (ses propres evenements)."""
    return _evenements(
        "(LOWER(email) = LOWER(%s) OR (type_compte = %s AND utilisateur_id = %s))",
        (utilisateur["email"], utilisateur["type"], str(utilisateur["id"])),
        type, None, None, limit, avant,
    )


@router.post("/deconnexion")
def deconnexion(request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
    """Deconnexion reelle : le jeton devient inutilisable cote serveur."""
    _ecrire(
        "UPDATE session_utilisateur SET revoquee_le = NOW(), motif_revocation = 'deconnexion' "
        "WHERE jti = %s AND revoquee_le IS NULL",
        (utilisateur["jti"],),
    )
    _journal("deconnexion", utilisateur, request)
    return {"message": "D\u00e9connexion effectu\u00e9e."}


@router.post("/autres/revoquer")
def revoquer_les_autres_sessions(request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_utilisateur'
        WHERE type_compte = %s AND utilisateur_id = %s AND jti <> %s AND revoquee_le IS NULL
        """,
        (utilisateur["type"], str(utilisateur["id"]), utilisateur["jti"]),
    )
    _journal("session_revoquee", utilisateur, request, "avertissement",
             {"motif": "revoquee_par_utilisateur", "nb": nombre})
    return {"message": f"{nombre} session(s) ferm\u00e9e(s).", "fermees": nombre}


@router.delete("/{jti}")
def revoquer_ma_session(jti: str, request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
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
        raise HTTPException(status_code=404, detail="Session introuvable ou d\u00e9j\u00e0 ferm\u00e9e.")
    _journal("session_revoquee", utilisateur, request, "info",
             {"motif": "revoquee_par_utilisateur", "cible_jti": jti})
    return {"message": "Session ferm\u00e9e."}


# ---------------------------------------------------------------------
# Administration (Admin de l'entreprise : uniquement SON entreprise)
# ---------------------------------------------------------------------

def _entreprise_admin(admin: dict) -> str:
    entreprise_id = admin.get("entrepriseId")
    if entreprise_id is None:
        raise HTTPException(status_code=403, detail="Action r\u00e9serv\u00e9e \u00e0 l'administrateur de l'entreprise.")
    return str(entreprise_id)


def _journal_admin(admin, request, details):
    journaliser(
        "action_admin", gravite="avertissement", type_compte=admin.get("type"),
        utilisateur_id=admin.get("id"), email=admin.get("email"),
        entreprise_id=admin.get("entrepriseId"), jti=admin.get("jti"),
        request=request, acteur_email=admin.get("email"), details=details,
    )


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


@router_admin.get("/evenements")
def evenements_entreprise(
    limit: int = 30,
    avant: int | None = None,
    type: str | None = None,
    gravite: str | None = None,
    email: str | None = None,
    admin: dict = Depends(exiger_role_admin),
):
    """Journal de securite de l'entreprise (filtre impose par le jeton)."""
    return _evenements("entreprise_id = %s", (_entreprise_admin(admin),),
                       type, gravite, email, limit, avant)


@router_admin.delete("/utilisateur/{utilisateur_id}")
def revoquer_toutes_sessions_utilisateur(
    utilisateur_id: str,
    request: Request,
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
    _journal_admin(admin, request, {"motif": "revoquer_toutes_sessions", "cible_id": utilisateur_id,
                                    "cible_type": type_compte, "nb": nombre})
    return {"message": f"{nombre} session(s) ferm\u00e9e(s).", "fermees": nombre}


@router_admin.delete("/{jti}")
def revoquer_session_entreprise(jti: str, request: Request, admin: dict = Depends(exiger_role_admin)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_admin'
        WHERE jti = %s AND entreprise_id = %s AND revoquee_le IS NULL
        """,
        (jti, _entreprise_admin(admin)),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Session introuvable ou d\u00e9j\u00e0 ferm\u00e9e.")
    _journal_admin(admin, request, {"motif": "revoquer_session", "cible_jti": jti})
    return {"message": "Session ferm\u00e9e."}