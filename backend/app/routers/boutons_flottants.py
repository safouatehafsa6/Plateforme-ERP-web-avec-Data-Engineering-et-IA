"""Boutons flottants administrables.

  GET  /api/boutons-flottants                 public (affichage) : boutons actifs et dans leur période
  *    /api/admin/boutons-flottants/...       Super Administrateur : création, modification, ordre, config,
                                              restauration, historique

La configuration est volontairement au niveau plateforme : les boutons s'affichent aussi sur les pages
publiques (aucune entreprise connue). Chaque modification est historisée dans la même transaction.
"""
import json
import threading
import time
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg2.extras import Json

from app.db import pool_central
from app.schemas.boutons_flottants import ActifPayload, BoutonPayload, ConfigPayload, OrdrePayload
from app.security.jwt_utils import exiger_super_admin
from app.services import boutons_flottants as regles

router = APIRouter(tags=["boutons-flottants"])

_COLONNES = """id, cle, titres, icone, couleur, taille, placement, position, ordre, actif, action, cible,
       nouvel_onglet, audience, profils, appareils, routes_incluses, routes_exclues,
       affiche_du, affiche_jusqu_au, systeme, mis_a_jour_le"""
_COLONNES_CONFIG = "actif, position, taille, couleur, icone, version, mis_a_jour_le"
_TTL_CACHE_S = 20
_cache = {"expire": 0.0, "valeur": None}
_verrou = threading.Lock()
_pret = False


def _vider_cache():
    _cache["expire"] = 0.0
    _cache["valeur"] = None


@contextmanager
def _transaction():
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _inserer_defauts(cur, ecraser: bool):
    """Insère les boutons système ; avec ecraser=True, remet ceux qui existent à leur valeur d'origine."""
    for b in regles.DEFAUTS_SYSTEME:
        valeurs = {"placement": "menu", "taille": "moyen", "nouvel_onglet": False, "cible": None, **b}
        cur.execute(
            f"""
            INSERT INTO bouton_flottant (cle, titres, icone, taille, placement, ordre, actif, action, cible,
                                         nouvel_onglet, audience, systeme)
            VALUES (%(cle)s, %(titres)s, %(icone)s, %(taille)s, %(placement)s, %(ordre)s, TRUE, %(action)s, %(cible)s,
                    %(nouvel_onglet)s, %(audience)s, TRUE)
            ON CONFLICT (cle) DO {"UPDATE SET titres = EXCLUDED.titres, icone = EXCLUDED.icone, taille = EXCLUDED.taille, placement = 'menu', position = NULL, ordre = EXCLUDED.ordre, actif = TRUE, action = EXCLUDED.action, cible = EXCLUDED.cible, nouvel_onglet = EXCLUDED.nouvel_onglet, audience = EXCLUDED.audience, profils = '{}', appareils = 'tous', routes_incluses = '{}', routes_exclues = '{}', affiche_du = NULL, affiche_jusqu_au = NULL, couleur = NULL, systeme = TRUE, mis_a_jour_le = NOW()" if ecraser else "NOTHING"}
            """,
            {**valeurs, "titres": Json(valeurs["titres"])},
        )


def _assurer_pret():
    """Crée la ligne de configuration et les boutons d'origine au premier usage (une fois par processus)."""
    global _pret
    if _pret:
        return
    with _verrou:
        if _pret:
            return
        with _transaction() as cur:
            cur.execute("SELECT to_regclass('bouton_flottant') IS NOT NULL")
            if not cur.fetchone()[0]:
                raise HTTPException(status_code=503, detail="Module non initialisé : lancez la migration centrale 015.")
            c = regles.CONFIG_PAR_DEFAUT
            cur.execute(
                "INSERT INTO bouton_flottant_config (id, actif, position, taille, couleur, icone) VALUES (1, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (c["actif"], c["position"], c["taille"], c["couleur"], c["icone"]),
            )
            cur.execute("SELECT COUNT(*) FROM bouton_flottant WHERE systeme")
            if cur.fetchone()[0] == 0:
                _inserer_defauts(cur, ecraser=False)
        _pret = True


def _lire_config(cur) -> dict:
    cur.execute(f"SELECT {_COLONNES_CONFIG} FROM bouton_flottant_config WHERE id = 1")
    return _dicts(cur)[0]


def _journal(cur, utilisateur, operation, cle=None, details=None):
    cur.execute(
        "INSERT INTO bouton_flottant_historique (cle, operation, details, par_email) VALUES (%s, %s, %s, %s)",
        (cle, operation, Json(details or {}, dumps=lambda o: json.dumps(o, default=str)), utilisateur.get("email")),
    )
    cur.execute("UPDATE bouton_flottant_config SET version = version + 1, mis_a_jour_le = NOW(), mis_a_jour_par = %s WHERE id = 1",
                (utilisateur.get("email"),))
    _vider_cache()


def _valeurs(p: BoutonPayload) -> dict:
    d = p.model_dump()
    d["titres"] = Json(d["titres"])
    return d


# ---------------------------------------------------------------------------
# Public : affichage
# ---------------------------------------------------------------------------
@router.get("/api/boutons-flottants")
def boutons_publics(reponse: Response):
    """Configuration appliquée à tous les écrans (aucune authentification : visible aussi sur les pages publiques)."""
    reponse.headers["Cache-Control"] = "public, max-age=15"
    if _cache["valeur"] is not None and time.monotonic() < _cache["expire"]:
        return _cache["valeur"]
    _assurer_pret()
    with _transaction() as cur:
        config = _lire_config(cur)
        cur.execute(
            f"""
            SELECT {_COLONNES} FROM bouton_flottant
            WHERE actif AND (affiche_du IS NULL OR affiche_du <= NOW())
                        AND (affiche_jusqu_au IS NULL OR affiche_jusqu_au > NOW())
            ORDER BY ordre, id
            """
        )
        valeur = {"config": config, "boutons": _dicts(cur), "version": config["version"]}
    _cache["valeur"], _cache["expire"] = valeur, time.monotonic() + _TTL_CACHE_S
    return valeur


# ---------------------------------------------------------------------------
# Administration (Super Administrateur)
# ---------------------------------------------------------------------------
def _options():
    return {
        "icones": list(regles.ICONES), "actions": list(regles.ACTIONS), "actions_integrees": list(regles.ACTIONS_INTEGREES),
        "tailles": list(regles.TAILLES), "positions": list(regles.POSITIONS), "positions_principal": list(regles.POSITIONS_PRINCIPAL),
        "audiences": list(regles.AUDIENCES), "profils": list(regles.PROFILS), "appareils": list(regles.APPAREILS),
        "langues": list(regles.LANGUES),
    }


@router.get("/api/admin/boutons-flottants")
def admin_lister(utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        config = _lire_config(cur)
        cur.execute(f"SELECT {_COLONNES} FROM bouton_flottant ORDER BY ordre, id")
        return {"config": config, "boutons": _dicts(cur), "options": _options()}


@router.put("/api/admin/boutons-flottants/config")
def admin_config(payload: ConfigPayload, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        avant = _lire_config(cur)
        cur.execute(
            "UPDATE bouton_flottant_config SET actif=%s, position=%s, taille=%s, couleur=%s, icone=%s WHERE id = 1",
            (payload.actif, payload.position, payload.taille, payload.couleur, payload.icone),
        )
        _journal(cur, utilisateur, "config", details={"avant": {k: avant[k] for k in ("actif", "position", "taille", "couleur", "icone")},
                                                      "apres": payload.model_dump()})
        return {"config": _lire_config(cur), "message": "Réglages enregistrés."}


@router.put("/api/admin/boutons-flottants/ordre")
def admin_ordre(payload: OrdrePayload, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        cur.execute("SELECT id FROM bouton_flottant WHERE id = ANY(%s)", (payload.ids,))
        if len(cur.fetchall()) != len(payload.ids):
            raise HTTPException(status_code=404, detail="Un des boutons n'existe plus.")
        for position, bouton_id in enumerate(payload.ids):
            cur.execute("UPDATE bouton_flottant SET ordre = %s, mis_a_jour_le = NOW(), mis_a_jour_par = %s WHERE id = %s",
                        ((position + 1) * 10, utilisateur.get("email"), bouton_id))
        _journal(cur, utilisateur, "ordre", details={"ids": payload.ids})
    return {"message": "Ordre enregistré."}


@router.post("/api/admin/boutons-flottants/restaurer")
def admin_restaurer(utilisateur=Depends(exiger_super_admin)):
    """Remet les boutons d'origine et les réglages généraux par défaut (les boutons ajoutés restent, désactivés pas touchés)."""
    _assurer_pret()
    with _transaction() as cur:
        _inserer_defauts(cur, ecraser=True)
        c = regles.CONFIG_PAR_DEFAUT
        cur.execute("UPDATE bouton_flottant_config SET actif=%s, position=%s, taille=%s, couleur=%s, icone=%s WHERE id = 1",
                    (c["actif"], c["position"], c["taille"], c["couleur"], c["icone"]))
        _journal(cur, utilisateur, "restauration", details={"boutons": [b["cle"] for b in regles.DEFAUTS_SYSTEME]})
    return {"message": "Boutons d'origine et réglages par défaut restaurés."}


@router.get("/api/admin/boutons-flottants/historique")
def admin_historique(limite: int = Query(default=50, ge=1, le=200), utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        cur.execute("SELECT id, cle, operation, details, par_email, le FROM bouton_flottant_historique ORDER BY le DESC, id DESC LIMIT %s", (limite,))
        return {"historique": _dicts(cur)}


@router.post("/api/admin/boutons-flottants", status_code=201)
def admin_creer(payload: BoutonPayload, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    cle = payload.cle or regles.generer_cle(payload.titres["fr"])
    with _transaction() as cur:
        cur.execute("SELECT cle FROM bouton_flottant WHERE cle = %s OR cle LIKE %s", (cle, cle + "-%"))
        existantes = {row[0] for row in cur.fetchall()}
        if payload.cle and cle in existantes:
            raise HTTPException(status_code=409, detail="Cet identifiant est déjà utilisé.")
        n = 2
        while cle in existantes:                    # titre identique : suffixe automatique
            cle_candidate = f"{cle[:35]}-{n}"
            if cle_candidate not in existantes:
                cle = cle_candidate
            n += 1
        v = _valeurs(payload)
        cur.execute(
            """
            INSERT INTO bouton_flottant (cle, titres, icone, couleur, taille, placement, position, ordre, actif, action, cible,
                   nouvel_onglet, audience, profils, appareils, routes_incluses, routes_exclues, affiche_du, affiche_jusqu_au,
                   systeme, mis_a_jour_par)
            VALUES (%(cle)s, %(titres)s, %(icone)s, %(couleur)s, %(taille)s, %(placement)s, %(position)s, %(ordre)s, %(actif)s,
                   %(action)s, %(cible)s, %(nouvel_onglet)s, %(audience)s, %(profils)s, %(appareils)s, %(routes_incluses)s,
                   %(routes_exclues)s, %(affiche_du)s, %(affiche_jusqu_au)s, FALSE, %(par)s)
            RETURNING id
            """,
            {**v, "cle": cle, "par": utilisateur.get("email")},
        )
        bouton_id = cur.fetchone()[0]
        _journal(cur, utilisateur, "creation", cle, {"titre": payload.titres["fr"], "action": payload.action})
        cur.execute(f"SELECT {_COLONNES} FROM bouton_flottant WHERE id = %s", (bouton_id,))
        return {"bouton": _dicts(cur)[0], "message": "Bouton créé."}


def _charger_pour_ecriture(cur, bouton_id: int) -> dict:
    cur.execute(f"SELECT {_COLONNES} FROM bouton_flottant WHERE id = %s FOR UPDATE", (bouton_id,))
    lignes = _dicts(cur)
    if not lignes:
        raise HTTPException(status_code=404, detail="Bouton introuvable.")
    return lignes[0]


@router.put("/api/admin/boutons-flottants/{bouton_id}")
def admin_modifier(bouton_id: int, payload: BoutonPayload, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        actuel = _charger_pour_ecriture(cur, bouton_id)
        v = _valeurs(payload)
        cur.execute(
            """
            UPDATE bouton_flottant SET titres=%(titres)s, icone=%(icone)s, couleur=%(couleur)s, taille=%(taille)s,
                   placement=%(placement)s, position=%(position)s, ordre=%(ordre)s, actif=%(actif)s, action=%(action)s,
                   cible=%(cible)s, nouvel_onglet=%(nouvel_onglet)s, audience=%(audience)s, profils=%(profils)s,
                   appareils=%(appareils)s, routes_incluses=%(routes_incluses)s, routes_exclues=%(routes_exclues)s,
                   affiche_du=%(affiche_du)s, affiche_jusqu_au=%(affiche_jusqu_au)s,
                   mis_a_jour_le=NOW(), mis_a_jour_par=%(par)s
            WHERE id=%(id)s
            """,
            {**v, "id": bouton_id, "par": utilisateur.get("email")},
        )
        champs = [k for k in ("titres", "icone", "couleur", "taille", "placement", "position", "ordre", "actif", "action", "cible",
                              "nouvel_onglet", "audience", "profils", "appareils", "routes_incluses", "routes_exclues",
                              "affiche_du", "affiche_jusqu_au") if actuel[k] != payload.model_dump()[k]]
        _journal(cur, utilisateur, "modification", actuel["cle"], {"champs": champs})
        cur.execute(f"SELECT {_COLONNES} FROM bouton_flottant WHERE id = %s", (bouton_id,))
        return {"bouton": _dicts(cur)[0], "message": "Bouton modifié."}


@router.patch("/api/admin/boutons-flottants/{bouton_id}/actif")
def admin_activer(bouton_id: int, payload: ActifPayload, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        actuel = _charger_pour_ecriture(cur, bouton_id)
        cur.execute("UPDATE bouton_flottant SET actif=%s, mis_a_jour_le=NOW(), mis_a_jour_par=%s WHERE id=%s",
                    (payload.actif, utilisateur.get("email"), bouton_id))
        _journal(cur, utilisateur, "activation" if payload.actif else "desactivation", actuel["cle"])
    return {"message": "Bouton activé." if payload.actif else "Bouton désactivé."}


@router.delete("/api/admin/boutons-flottants/{bouton_id}")
def admin_supprimer(bouton_id: int, utilisateur=Depends(exiger_super_admin)):
    _assurer_pret()
    with _transaction() as cur:
        actuel = _charger_pour_ecriture(cur, bouton_id)
        if actuel["systeme"]:
            raise HTTPException(status_code=409, detail="Un bouton d'origine ne se supprime pas : désactivez-le (ou restaurez-le).")
        cur.execute("DELETE FROM bouton_flottant WHERE id = %s", (bouton_id,))
        _journal(cur, utilisateur, "suppression", actuel["cle"], {"titre": actuel["titres"].get("fr")})
    return {"message": "Bouton supprimé."}
