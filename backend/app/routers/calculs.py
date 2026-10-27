"""Moteur de calcul métier : calculs à taux unique / taux variables, référentiel de taux,
historique, modification, suppression et rapports PDF / Word.

Sécurité (même modèle que les autres modules de la plateforme) :
  - Calculs, historique, exports : permissions du module « calculs »
    (consulter, creer, modifier, supprimer, exporter) vérifiées en base à chaque requête.
  - Administration des périodes et des taux : réservée aux administrateurs de l'entreprise.
Toutes les données restent dans la base de l'entreprise de l'utilisateur.
"""
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise, pool_central
from app.routers.notifications import notifier_action
from app.security.auth_dependency import exiger_role_admin
from app.security.permissions import exiger_permission
from app.services import moteur_calcul as moteur
from app.services.moteur_calcul import ErreurCalcul, PeriodeTaux
from app.services.provisioning import DOSSIER_TEMPLATE
from app.utils import rapport_calcul

router = APIRouter(prefix="/api/calculs", tags=["calculs"])
logger = logging.getLogger(__name__)

DEVISES = {"MAD", "DT", "EUR", "USD"}
_bases_pretes: set[str] = set()


# ------------------------------------------------------------------ schéma
def _pool(utilisateur: dict):
    """Pool de l'entreprise ; crée le schéma du module s'il manque (bases existantes)."""
    nom_base = utilisateur["nomBase"]
    pool = get_pool_entreprise(nom_base)
    if nom_base not in _bases_pretes:
        with open(os.path.join(DOSSIER_TEMPLATE, "018_calculs_taux.sql"), encoding="utf-8") as f:
            script = f.read()
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(script)
            conn.commit()
            _bases_pretes.add(nom_base)
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    return pool


def _dicts(cur):
    colonnes = [d[0] for d in cur.description]
    return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


def _auteur(utilisateur: dict) -> str:
    return (utilisateur.get("email") or str(utilisateur.get("id") or "")).strip()


# ------------------------------------------------------------------ modèles
class CalculCommun(BaseModel):
    montant: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    dateDebut: date
    dateFin: date
    libelle: str | None = Field(default=None, max_length=200)
    moduleSource: str = "general"
    devise: str = "MAD"
    inclureDernierJour: bool | None = None


class CalculUniquePayload(CalculCommun):
    taux: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)


class CalculVariablePayload(CalculCommun):
    baremeId: int | None = None


class BaremePayload(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    libelle: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)


class BaremeMajPayload(BaseModel):
    libelle: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    actif: bool = True


class PeriodePayload(BaseModel):
    dateDebut: date
    dateFin: date
    taux: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)


def _valider_communs(p: CalculCommun):
    if p.moduleSource not in moteur.MODULES_SOURCE:
        raise HTTPException(status_code=400, detail="Module concerné inconnu.")
    if p.devise not in DEVISES:
        raise HTTPException(status_code=400, detail="Devise non prise en charge.")


# ------------------------------------------------------------------ formatage
def _formater(l: dict, avec_details: bool = True) -> dict:
    sortie = {
        "id": l["id"], "reference": l["reference"], "mode": l["mode"],
        "moduleSource": l["module_source"], "libelle": l["libelle"],
        "montant": str(l["montant"]), "dateDebut": l["date_debut"].isoformat(), "dateFin": l["date_fin"].isoformat(),
        "taux": str(l["taux"]) if l["taux"] is not None else None,
        "baremeId": l["bareme_id"], "baremeLibelle": l["bareme_libelle"],
        "baseJours": l["base_jours"], "inclureDernierJour": l["inclure_dernier_jour"], "devise": l["devise"],
        "nombreJours": l["nombre_jours"], "resultat": str(l["resultat"]),
        "creePar": l["cree_par_nom"] or l["cree_par"], "creeLe": l["cree_le"].isoformat(),
        "modifiePar": l["modifie_par"], "modifieLe": l["modifie_le"].isoformat() if l["modifie_le"] else None,
    }
    if avec_details:
        sortie["details"] = l["details"]
    return sortie


def _en_rapport(l: dict) -> dict:
    """Format attendu par le générateur de rapports (dates ISO, nombres en chaînes)."""
    return {**l, "montant": str(l["montant"]), "taux": str(l["taux"]) if l["taux"] is not None else None,
            "resultat": str(l["resultat"]), "date_debut": l["date_debut"].isoformat(), "date_fin": l["date_fin"].isoformat(),
            "cree_le": l["cree_le"].isoformat()}


_COLONNES = ("id, reference, mode, module_source, libelle, montant, date_debut, date_fin, taux, bareme_id, bareme_libelle, "
             "base_jours, inclure_dernier_jour, devise, nombre_jours, resultat, details, cree_par, cree_par_nom, cree_le, "
             "modifie_par, modifie_le")


def _lire_calcul(cur, calcul_id: int) -> dict:
    cur.execute(f"SELECT {_COLONNES} FROM calcul_taux WHERE id = %s", (calcul_id,))
    lignes = _dicts(cur)
    if not lignes:
        raise HTTPException(status_code=404, detail="Calcul introuvable.")
    return lignes[0]


# ------------------------------------------------------------------ référentiel (lecture interne)
def _periodes_du_bareme(cur, bareme_id: int) -> list[PeriodeTaux]:
    cur.execute(
        "SELECT id, date_debut, date_fin, taux FROM periode_taux WHERE bareme_id = %s AND actif = TRUE ORDER BY date_debut",
        (bareme_id,),
    )
    return [PeriodeTaux(id=r[0], date_debut=r[1], date_fin=r[2], taux=r[3]) for r in cur.fetchall()]


def _bareme(cur, bareme_id: int | None) -> tuple[int, str]:
    if bareme_id is None:
        cur.execute("SELECT id, libelle FROM bareme_taux WHERE actif = TRUE ORDER BY (code = 'TAUX_REFERENCE') DESC, id LIMIT 1")
    else:
        cur.execute("SELECT id, libelle FROM bareme_taux WHERE id = %s AND actif = TRUE", (bareme_id,))
    ligne = cur.fetchone()
    if not ligne:
        raise HTTPException(status_code=400, detail="Barème de taux introuvable ou inactif.")
    return ligne[0], ligne[1]


def _executer(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ErreurCalcul as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------ calculs
def _reference(cur) -> str:
    cur.execute("SELECT nextval('calcul_taux_seq')")
    return f"CAL-{datetime.now().year}-{cur.fetchone()[0]:06d}"


@router.get("/modules")
def modules_disponibles(_: dict = Depends(exiger_permission("calculs", "consulter"))):
    return {"modules": [{"code": k, "libelle": v} for k, v in moteur.MODULES_SOURCE.items()], "devises": sorted(DEVISES)}


@router.post("/taux-unique", status_code=201)
def calculer_taux_unique(payload: CalculUniquePayload, utilisateur: dict = Depends(exiger_permission("calculs", "creer"))):
    _valider_communs(payload)
    inclure = bool(payload.inclureDernierJour)
    res = _executer(moteur.calculer_taux_unique, payload.montant, payload.dateDebut, payload.dateFin, payload.taux,
                    inclure_dernier_jour=inclure)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            reference = _reference(cur)
            cur.execute(
                """INSERT INTO calcul_taux (reference, mode, module_source, libelle, montant, date_debut, date_fin, taux,
                       base_jours, inclure_dernier_jour, devise, nombre_jours, resultat, details, cree_par, cree_par_nom)
                   VALUES (%s,'taux_unique',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING id""",
                (reference, payload.moduleSource, payload.libelle, payload.montant, payload.dateDebut, payload.dateFin,
                 payload.taux, moteur.BASE_JOURS_DEFAUT, inclure, payload.devise, res["nombre_jours"], res["resultat"],
                 json.dumps(res["details"]), str(utilisateur["id"]), _auteur(utilisateur)),
            )
            nouveau_id = cur.fetchone()[0]
            calcul = _lire_calcul(cur, nouveau_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    notifier_action(utilisateur, "Calcul enregistré", f"{calcul['reference']} : résultat {res['resultat']} {payload.devise}.", "/calculs", "info")
    return _formater(calcul)


@router.post("/taux-variable", status_code=201)
def calculer_taux_variable(payload: CalculVariablePayload, utilisateur: dict = Depends(exiger_permission("calculs", "creer"))):
    _valider_communs(payload)
    inclure = True if payload.inclureDernierJour is None else payload.inclureDernierJour
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            bareme_id, bareme_libelle = _bareme(cur, payload.baremeId)
            periodes = _periodes_du_bareme(cur, bareme_id)
            res = _executer(moteur.calculer_taux_variable, payload.montant, payload.dateDebut, payload.dateFin, periodes,
                            inclure_dernier_jour=inclure)
            reference = _reference(cur)
            cur.execute(
                """INSERT INTO calcul_taux (reference, mode, module_source, libelle, montant, date_debut, date_fin, bareme_id,
                       bareme_libelle, base_jours, inclure_dernier_jour, devise, nombre_jours, resultat, details, cree_par, cree_par_nom)
                   VALUES (%s,'taux_variable',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING id""",
                (reference, payload.moduleSource, payload.libelle, payload.montant, payload.dateDebut, payload.dateFin,
                 bareme_id, bareme_libelle, moteur.BASE_JOURS_DEFAUT, inclure, payload.devise, res["nombre_jours"],
                 res["resultat"], json.dumps(res["details"]), str(utilisateur["id"]), _auteur(utilisateur)),
            )
            nouveau_id = cur.fetchone()[0]
            calcul = _lire_calcul(cur, nouveau_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    notifier_action(utilisateur, "Calcul enregistré", f"{calcul['reference']} : résultat {res['resultat']} {payload.devise}.", "/calculs", "info")
    return _formater(calcul)


@router.get("")
def historique(
    q: str | None = Query(default=None, max_length=100),
    mode: str | None = None,
    moduleSource: str | None = None,
    du: date | None = None,
    au: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    utilisateur: dict = Depends(exiger_permission("calculs", "consulter")),
):
    conditions, params = [], []
    if q:
        conditions.append("(reference ILIKE %s OR libelle ILIKE %s OR cree_par_nom ILIKE %s)")
        params += [f"%{q}%"] * 3
    if mode:
        if mode not in ("taux_unique", "taux_variable"):
            raise HTTPException(status_code=400, detail="Type de calcul inconnu.")
        conditions.append("mode = %s"); params.append(mode)
    if moduleSource:
        conditions.append("module_source = %s"); params.append(moduleSource)
    if du:
        conditions.append("cree_le::date >= %s"); params.append(du)
    if au:
        conditions.append("cree_le::date <= %s"); params.append(au)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM calcul_taux {where}", params)
            total = cur.fetchone()[0]
            cur.execute(f"SELECT {_COLONNES} FROM calcul_taux {where} ORDER BY cree_le DESC, id DESC LIMIT %s OFFSET %s",
                        params + [limit, offset])
            lignes = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"total": total, "calculs": [_formater(l, avec_details=False) for l in lignes]}


# --- référentiel : routes fixes déclarées AVANT « /{calcul_id} » -------------------------
@router.get("/referentiel/baremes")
def lister_baremes(utilisateur: dict = Depends(exiger_permission("calculs", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT b.id, b.code, b.libelle, b.description, b.actif,
                                  COUNT(p.id) FILTER (WHERE p.actif) AS nb_periodes
                           FROM bareme_taux b LEFT JOIN periode_taux p ON p.bareme_id = b.id
                           GROUP BY b.id ORDER BY (b.code = 'TAUX_REFERENCE') DESC, b.libelle""")
            lignes = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"baremes": [{"id": l["id"], "code": l["code"], "libelle": l["libelle"], "description": l["description"],
                         "actif": l["actif"], "nbPeriodes": l["nb_periodes"]} for l in lignes]}


@router.post("/referentiel/baremes", status_code=201)
def creer_bareme(payload: BaremePayload, utilisateur: dict = Depends(exiger_role_admin)):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM bareme_taux WHERE UPPER(code) = UPPER(%s)", (payload.code,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Ce code de barème existe déjà.")
            cur.execute("INSERT INTO bareme_taux (code, libelle, description) VALUES (%s,%s,%s) RETURNING id",
                        (payload.code.upper(), payload.libelle.strip(), payload.description))
            nouveau_id = cur.fetchone()[0]
        conn.commit()
    except HTTPException:
        conn.rollback(); raise
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return {"id": nouveau_id, "message": "Barème créé."}


@router.put("/referentiel/baremes/{bareme_id}")
def modifier_bareme(bareme_id: int, payload: BaremeMajPayload, utilisateur: dict = Depends(exiger_role_admin)):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE bareme_taux SET libelle=%s, description=%s, actif=%s WHERE id=%s RETURNING code",
                        (payload.libelle.strip(), payload.description, payload.actif, bareme_id))
            ligne = cur.fetchone()
            if not ligne:
                raise HTTPException(status_code=404, detail="Barème introuvable.")
            if ligne[0] == "TAUX_REFERENCE" and not payload.actif:
                raise HTTPException(status_code=400, detail="Le barème par défaut ne peut pas être désactivé.")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return {"message": "Barème mis à jour."}


def _formater_periode(r: dict) -> dict:
    return {"id": r["id"], "baremeId": r["bareme_id"], "dateDebut": r["date_debut"].isoformat(), "dateFin": r["date_fin"].isoformat(),
            "taux": str(r["taux"]), "actif": r["actif"], "creePar": r["cree_par"], "modifiePar": r["modifie_par"],
            "modifieLe": r["modifie_le"].isoformat() if r["modifie_le"] else None}


@router.get("/referentiel/baremes/{bareme_id}/periodes")
def lister_periodes(bareme_id: int, archivees: bool = False, utilisateur: dict = Depends(exiger_permission("calculs", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM bareme_taux WHERE id = %s", (bareme_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Barème introuvable.")
            cur.execute("""SELECT id, bareme_id, date_debut, date_fin, taux, actif, cree_par, modifie_par, modifie_le
                           FROM periode_taux WHERE bareme_id = %s AND (actif OR %s) ORDER BY date_debut""", (bareme_id, archivees))
            lignes = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"periodes": [_formater_periode(l) for l in lignes]}


def _verifier_chevauchement(cur, bareme_id: int, debut: date, fin: date, ignorer_id: int | None):
    cur.execute("""SELECT date_debut, date_fin, taux FROM periode_taux
                   WHERE bareme_id = %s AND actif = TRUE AND id <> COALESCE(%s, -1)
                     AND date_debut <= %s AND date_fin >= %s ORDER BY date_debut LIMIT 1""",
                (bareme_id, ignorer_id, fin, debut))
    autre = cur.fetchone()
    if autre:
        raise HTTPException(status_code=409, detail=(
            f"Cette période chevauche une période existante (du {autre[0]:%d/%m/%Y} au {autre[1]:%d/%m/%Y}, taux {autre[2]} %). "
            "Modifiez les dates ou ajustez l'autre période."))


@router.post("/referentiel/baremes/{bareme_id}/periodes", status_code=201)
def ajouter_periode(bareme_id: int, payload: PeriodePayload, utilisateur: dict = Depends(exiger_role_admin)):
    if payload.dateFin < payload.dateDebut:
        raise HTTPException(status_code=400, detail="La date de fin doit être postérieure ou égale à la date de début.")
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bareme_taux WHERE id = %s AND actif = TRUE FOR UPDATE", (bareme_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Barème introuvable ou inactif.")
            _verifier_chevauchement(cur, bareme_id, payload.dateDebut, payload.dateFin, None)
            cur.execute("INSERT INTO periode_taux (bareme_id, date_debut, date_fin, taux, cree_par) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        (bareme_id, payload.dateDebut, payload.dateFin, payload.taux, _auteur(utilisateur)))
            nouveau_id = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return {"id": nouveau_id, "message": "Période ajoutée."}


@router.put("/referentiel/periodes/{periode_id}")
def modifier_periode(periode_id: int, payload: PeriodePayload, utilisateur: dict = Depends(exiger_role_admin)):
    if payload.dateFin < payload.dateDebut:
        raise HTTPException(status_code=400, detail="La date de fin doit être postérieure ou égale à la date de début.")
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT bareme_id, actif FROM periode_taux WHERE id = %s FOR UPDATE", (periode_id,))
            ligne = cur.fetchone()
            if not ligne:
                raise HTTPException(status_code=404, detail="Période introuvable.")
            if not ligne[1]:
                raise HTTPException(status_code=400, detail="Une période archivée ne peut plus être modifiée.")
            cur.execute("SELECT id FROM bareme_taux WHERE id = %s FOR UPDATE", (ligne[0],))
            _verifier_chevauchement(cur, ligne[0], payload.dateDebut, payload.dateFin, periode_id)
            cur.execute("""UPDATE periode_taux SET date_debut=%s, date_fin=%s, taux=%s, modifie_par=%s, modifie_le=NOW() WHERE id=%s""",
                        (payload.dateDebut, payload.dateFin, payload.taux, _auteur(utilisateur), periode_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return {"message": "Période mise à jour. Elle sera appliquée aux nouveaux calculs."}


@router.delete("/referentiel/periodes/{periode_id}")
def supprimer_periode(periode_id: int, utilisateur: dict = Depends(exiger_role_admin)):
    """Règle de gestion : une période jamais utilisée est supprimée ; une période déjà utilisée par
    un calcul enregistré est archivée (retirée des nouveaux calculs, conservée pour l'historique)."""
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM periode_taux WHERE id = %s FOR UPDATE", (periode_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Période introuvable.")
            cur.execute("""SELECT EXISTS (SELECT 1 FROM calcul_taux c, jsonb_array_elements(c.details) d
                                          WHERE d->>'periodeId' = %s::text)""", (periode_id,))
            utilisee = cur.fetchone()[0]
            if utilisee:
                cur.execute("UPDATE periode_taux SET actif = FALSE, modifie_par=%s, modifie_le=NOW() WHERE id=%s",
                            (_auteur(utilisateur), periode_id))
            else:
                cur.execute("DELETE FROM periode_taux WHERE id = %s", (periode_id,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    if utilisee:
        return {"archivee": True, "message": "Cette période est utilisée par des calculs enregistrés : elle a été archivée (les anciens calculs restent intacts)."}
    return {"archivee": False, "message": "Période supprimée."}


# --- calcul : lecture, modification, suppression, export ---------------------------------
@router.get("/{calcul_id}")
def lire(calcul_id: int, utilisateur: dict = Depends(exiger_permission("calculs", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            return _formater(_lire_calcul(cur, calcul_id))
    finally:
        pool.putconn(conn)


@router.put("/taux-unique/{calcul_id}")
def modifier_taux_unique(calcul_id: int, payload: CalculUniquePayload, utilisateur: dict = Depends(exiger_permission("calculs", "modifier"))):
    _valider_communs(payload)
    inclure = bool(payload.inclureDernierJour)
    res = _executer(moteur.calculer_taux_unique, payload.montant, payload.dateDebut, payload.dateFin, payload.taux, inclure_dernier_jour=inclure)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            existant = _lire_calcul(cur, calcul_id)
            if existant["mode"] != "taux_unique":
                raise HTTPException(status_code=400, detail="Ce calcul n'est pas un calcul à taux unique.")
            cur.execute(
                """UPDATE calcul_taux SET module_source=%s, libelle=%s, montant=%s, date_debut=%s, date_fin=%s, taux=%s,
                       inclure_dernier_jour=%s, devise=%s, nombre_jours=%s, resultat=%s, details=%s::jsonb,
                       modifie_par=%s, modifie_le=NOW() WHERE id=%s""",
                (payload.moduleSource, payload.libelle, payload.montant, payload.dateDebut, payload.dateFin, payload.taux, inclure,
                 payload.devise, res["nombre_jours"], res["resultat"], json.dumps(res["details"]), _auteur(utilisateur), calcul_id))
            calcul = _lire_calcul(cur, calcul_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return _formater(calcul)


@router.put("/taux-variable/{calcul_id}")
def modifier_taux_variable(calcul_id: int, payload: CalculVariablePayload, utilisateur: dict = Depends(exiger_permission("calculs", "modifier"))):
    _valider_communs(payload)
    inclure = True if payload.inclureDernierJour is None else payload.inclureDernierJour
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            existant = _lire_calcul(cur, calcul_id)
            if existant["mode"] != "taux_variable":
                raise HTTPException(status_code=400, detail="Ce calcul n'est pas un calcul à taux variables.")
            bareme_id, bareme_libelle = _bareme(cur, payload.baremeId or existant["bareme_id"])
            res = _executer(moteur.calculer_taux_variable, payload.montant, payload.dateDebut, payload.dateFin,
                            _periodes_du_bareme(cur, bareme_id), inclure_dernier_jour=inclure)
            cur.execute(
                """UPDATE calcul_taux SET module_source=%s, libelle=%s, montant=%s, date_debut=%s, date_fin=%s, bareme_id=%s,
                       bareme_libelle=%s, inclure_dernier_jour=%s, devise=%s, nombre_jours=%s, resultat=%s, details=%s::jsonb,
                       modifie_par=%s, modifie_le=NOW() WHERE id=%s""",
                (payload.moduleSource, payload.libelle, payload.montant, payload.dateDebut, payload.dateFin, bareme_id, bareme_libelle,
                 inclure, payload.devise, res["nombre_jours"], res["resultat"], json.dumps(res["details"]), _auteur(utilisateur), calcul_id))
            calcul = _lire_calcul(cur, calcul_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    return _formater(calcul)


@router.delete("/{calcul_id}")
def supprimer(calcul_id: int, utilisateur: dict = Depends(exiger_permission("calculs", "supprimer"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM calcul_taux WHERE id = %s RETURNING reference", (calcul_id,))
            ligne = cur.fetchone()
            if not ligne:
                raise HTTPException(status_code=404, detail="Calcul introuvable.")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
    logger.info("Calcul %s supprimé par %s", ligne[0], _auteur(utilisateur))
    return {"message": "Calcul supprimé."}


def _nom_entreprise(utilisateur: dict) -> str:
    entreprise_id = utilisateur.get("entrepriseId")
    if entreprise_id is None:
        return "Plateforme ERP"
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom FROM entreprise WHERE id = %s", (entreprise_id,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    return ligne[0] if ligne else "Plateforme ERP"


@router.get("/{calcul_id}/export")
def exporter(calcul_id: int, format: str = Query(default="pdf", pattern="^(pdf|docx)$"),
             type: str = Query(default="detaille", pattern="^(detaille|simplifie)$"),
             utilisateur: dict = Depends(exiger_permission("calculs", "exporter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            calcul = _lire_calcul(cur, calcul_id)
    finally:
        pool.putconn(conn)
    rapport = _en_rapport(calcul)
    entreprise = _nom_entreprise(utilisateur)
    if format == "pdf":
        contenu = rapport_calcul.generer_pdf(rapport, entreprise, type)
        media = "application/pdf"
    else:
        contenu = rapport_calcul.generer_docx(rapport, entreprise, type)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    suffixe = f"_{type}" if calcul["mode"] == "taux_variable" else ""
    nom = f"{calcul['reference']}{suffixe}.{format}"
    return Response(content=contenu, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{nom}"', "Cache-Control": "no-store"})
