"""Pipeline Data Engineering : lancement du DAG Airflow, suivi, et acces au Dashboard.

Flux : bouton Dashboard (React) -> POST /api/pipeline/run -> Airflow DAG
       -> GET /api/pipeline/status/{run_id} (sondage) -> POST /api/pipeline/dashboard-token
       -> Streamlit (affiche UNIQUEMENT les donnees validees de l'entreprise du jeton).

Reserve a l'Administrateur de l'entreprise (meme controle que Collaborateurs / Roles).
"""
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

from app.security.auth_dependency import exiger_role_admin

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

DAG_ID = "erp_data_engineering_pipeline"
CURATED_BUCKET = "curated"
POINTER_KEY = "_meta/latest_success.json"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_:+.\-]{8,100}$")
ETAPES = [
    ("extract_raw", "Extraction des données"),
    ("transform_staging", "Transformation en Parquet"),
    ("build_curated", "Préparation des données finales"),
    ("quality_gate", "Contrôle de qualité"),
]
DUREE_JETON_MINUTES = 5


class LancerPipeline(BaseModel):
    force: bool = False


# ---------------------------------------------------------------- configuration

def _env(nom: str) -> str:
    valeur = os.environ.get(nom)
    if not valeur:
        raise HTTPException(status_code=500, detail=f"Configuration serveur incomplète ({nom}).")
    return valeur


def _age_max_minutes() -> int:
    try:
        return int(os.environ.get("PIPELINE_MAX_AGE_MINUTES", "60"))
    except ValueError:
        return 60


# ---------------------------------------------------------------------- Airflow

def _airflow(methode: str, chemin: str, **kwargs):
    base = os.environ.get("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v1").rstrip("/")
    try:
        reponse = httpx.request(
            methode,
            f"{base}{chemin}",
            auth=(_env("AIRFLOW_API_USER"), _env("AIRFLOW_API_PASSWORD")),
            timeout=15,
            **kwargs,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Le service de traitement des données (Airflow) est injoignable.")
    if reponse.status_code == 404:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    if reponse.status_code >= 400:
        raise HTTPException(status_code=502, detail="Airflow a refusé la requête.")
    return reponse.json()


def _run_actif():
    donnees = _airflow(
        "GET",
        f"/dags/{DAG_ID}/dagRuns",
        params=[("state", "running"), ("state", "queued"), ("limit", "1")],
    )
    runs = donnees.get("dag_runs", [])
    return runs[0]["dag_run_id"] if runs else None


def _etat_run(run_id: str) -> dict:
    run_q = quote(run_id, safe="")
    run = _airflow("GET", f"/dags/{DAG_ID}/dagRuns/{run_q}")
    taches = _airflow("GET", f"/dags/{DAG_ID}/dagRuns/{run_q}/taskInstances").get("task_instances", [])
    etats = {t["task_id"]: (t.get("state") or "none") for t in taches}

    liste = [{"id": id_, "label": label, "state": etats.get(id_, "none")} for id_, label in ETAPES]
    en_echec = next((t for t in liste if t["state"] in ("failed", "upstream_failed")), None)

    if run["state"] == "success":
        statut = "success"
    elif run["state"] == "failed" or en_echec:
        statut = "failed"
    elif run["state"] == "queued":
        statut = "queued"
    else:
        statut = "running"

    resultat = {"runId": run_id, "status": statut, "tasks": liste}
    if statut == "failed":
        etape = next((t for t in liste if t["state"] == "failed"), en_echec)
        resultat["failedStage"] = etape["label"] if etape else None
        if etape and etape["id"] == "quality_gate":
            resultat["message"] = (
                "Le contrôle de qualité a refusé les nouvelles données. "
                "Le dernier jeu de données valide reste disponible."
            )
        else:
            resultat["message"] = "Le traitement des données a échoué. Réessayez ou contactez l'administrateur technique."
    return resultat


# ------------------------------------------------------------------------ MinIO

def _lire_pointeur():
    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        access_key=_env("MINIO_ROOT_USER"),
        secret_key=_env("MINIO_ROOT_PASSWORD"),
        secure=False,
    )
    try:
        reponse = client.get_object(CURATED_BUCKET, POINTER_KEY)
        try:
            return json.loads(reponse.read().decode("utf-8"))
        finally:
            reponse.close()
            reponse.release_conn()
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket"):
            return None
        raise HTTPException(status_code=502, detail="Stockage des données indisponible.")
    except Exception:
        raise HTTPException(status_code=502, detail="Stockage des données indisponible.")


def _est_recent(pointeur: dict) -> bool:
    try:
        publie = datetime.fromisoformat(pointeur["published_at"])
    except (KeyError, ValueError):
        return False
    return datetime.now(timezone.utc) - publie < timedelta(minutes=_age_max_minutes())


def _entreprise_id(utilisateur: dict) -> int:
    try:
        valeur = int(utilisateur.get("entrepriseId"))
    except (TypeError, ValueError):
        valeur = 0
    if valeur <= 0:
        raise HTTPException(status_code=403, detail="Compte non rattaché à une entreprise.")
    return valeur


# -------------------------------------------------------------------- endpoints

@router.get("/latest")
def derniere_version(utilisateur: dict = Depends(exiger_role_admin)):
    """Dernier jeu de donnees valide. Ne renvoie QUE les chiffres de l'entreprise de l'appelant."""
    entreprise_id = _entreprise_id(utilisateur)
    pointeur = _lire_pointeur()
    if not pointeur:
        return {"available": False}
    return {
        "available": True,
        "runId": pointeur.get("run_id"),
        "publishedAt": pointeur.get("published_at"),
        "recent": _est_recent(pointeur),
        "rows": (pointeur.get("companies") or {}).get(str(entreprise_id), 0),
    }


@router.post("/run")
def lancer(corps: LancerPipeline = LancerPipeline(), utilisateur: dict = Depends(exiger_role_admin)):
    _entreprise_id(utilisateur)

    # 1) Donnees recentes et pas de demande de rafraichissement : on reutilise.
    if not corps.force:
        pointeur = _lire_pointeur()
        if pointeur and _est_recent(pointeur):
            return {"cached": True, "status": "success", "runId": pointeur.get("run_id")}

    # 2) Un traitement est deja en cours : on se rattache a lui (jamais deux en parallele).
    actif = _run_actif()
    if actif:
        return {"cached": False, "status": "running", "runId": actif}

    # 3) Nouveau traitement.
    maintenant = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"erp-{maintenant}-{secrets.token_hex(3)}"
    _airflow("PATCH", f"/dags/{DAG_ID}", json={"is_paused": False})
    _airflow(
        "POST",
        f"/dags/{DAG_ID}/dagRuns",
        json={"dag_run_id": run_id, "conf": {"pipeline_run_id": run_id}},
    )
    return {"cached": False, "status": "queued", "runId": run_id}


@router.get("/status/{run_id}")
def statut(run_id: str, utilisateur: dict = Depends(exiger_role_admin)):
    _entreprise_id(utilisateur)
    if not RUN_ID_RE.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Identifiant d'exécution invalide.")
    return _etat_run(run_id)


@router.post("/dashboard-token")
def jeton_dashboard(utilisateur: dict = Depends(exiger_role_admin)):
    """Jeton court (5 min), signe avec un secret DEDIE au Dashboard (pas JWT_SECRET)."""
    entreprise_id = _entreprise_id(utilisateur)
    if not _lire_pointeur():
        raise HTTPException(status_code=409, detail="Aucune donnée validée disponible. Lancez d'abord le traitement.")

    jeton = jwt.encode(
        {
            "purpose": "dashboard",
            "entrepriseId": entreprise_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=DUREE_JETON_MINUTES),
        },
        _env("DASHBOARD_TOKEN_SECRET"),
        algorithm="HS256",
    )
    base = os.environ.get("STREAMLIT_PUBLIC_URL", "http://localhost:8501").rstrip("/")
    return {"url": f"{base}/?t={jeton}"}
