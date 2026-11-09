<<<<<<< HEAD
from dotenv import load_dotenv
load_dotenv()

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, entreprises, admin, utilisateurs, roles, utilisateurs_externes, portail, verification, ventes, achats, fournisseurs, clients, stock, comptabilite, assistant, assistant_documents, pipeline, appareils, sessions, suggestions, notifications, support, public, calculs, room_live, prospects, idp, outils
from app.db import pool_central
from app.security.appareils import AppareilRefuse, assurer_schema as assurer_schema_appareils
from app.security.tentatives import assurer_schema as assurer_schema_tentatives
from fastapi.responses import JSONResponse
app = FastAPI(title="ERP Backend", version="0.1.0")

def _origines_cors() -> list[str]:
    """Origines autorisees a appeler l'API (variable CORS_ORIGINS, separees par
    des virgules). Par defaut : uniquement l'interface locale."""
    brut = os.getenv("CORS_ORIGINS", "")
    if brut.strip():
        return [o.strip() for o in brut.split(",") if o.strip()]
    return [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origines_cors(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def entetes_securite(request, call_next):
    reponse = await call_next(request)
    reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
    reponse.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and reponse.headers.get("content-type", "").startswith("application/json"):
        reponse.headers.setdefault("Cache-Control", "no-store")
    return reponse

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(sessions.router_admin)
app.include_router(appareils.router)
app.include_router(appareils.router_admin)
app.include_router(entreprises.router)
app.include_router(admin.router)
app.include_router(utilisateurs.router)
app.include_router(roles.router)
app.include_router(utilisateurs_externes.router)
app.include_router(portail.router)
app.include_router(verification.router)
app.include_router(ventes.router)
app.include_router(achats.router)
app.include_router(fournisseurs.router)
app.include_router(prospects.router)
app.include_router(clients.router)
app.include_router(stock.router)
app.include_router(comptabilite.router)
app.include_router(assistant.router)
app.include_router(assistant_documents.router)
app.include_router(pipeline.router)
app.include_router(suggestions.router)
app.include_router(notifications.router)
app.include_router(support.router)
app.include_router(public.router)
app.include_router(calculs.router)
app.include_router(idp.router)
app.include_router(outils.router)
app.include_router(room_live.router)


@app.on_event("startup")
def preparer_notifications():
    """Crée la table des notifications sur une base existante (voir notifications.py)."""
    try:
        notifications.assurer_table()
    except Exception:
        import logging
        logging.getLogger("erp.notifications").exception(
            "Table des notifications non créée au démarrage (nouvel essai à la première utilisation)"
        )


@app.exception_handler(AppareilRefuse)
async def appareil_refuse(request, exc):
    return JSONResponse(status_code=403, content={"message": exc.message})


def verifier_configuration() -> None:
    """Refuse de demarrer avec un secret JWT absent ou trop court."""
    if len(os.environ.get("JWT_SECRET", "")) < 32:
        raise RuntimeError("JWT_SECRET absent ou trop court (32 caracteres minimum).")


def assurer_index_sessions() -> None:
    """Index sur session_utilisateur.expire_le (nettoyage des sessions a chaque
    connexion). Idempotent ; ne bloque jamais le demarrage."""
    try:
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_session_utilisateur_expire "
                    "ON session_utilisateur (expire_le)"
                )
            conn.commit()
        finally:
            pool_central.putconn(conn)
    except Exception:
        logging.getLogger("erp.securite").exception("Index des sessions non cree au demarrage")


@app.on_event("startup")
def preparer_securite():
    verifier_configuration()
    assurer_index_sessions()
    assurer_schema_appareils()
    assurer_schema_tentatives()


@app.get("/api/health")
def health():
    return {"status": "ok"}
=======
from dotenv import load_dotenv
load_dotenv()

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, entreprises, admin, utilisateurs, roles, utilisateurs_externes, portail, verification, ventes, achats, fournisseurs, clients, stock, comptabilite, assistant, assistant_documents, pipeline, appareils, sessions, suggestions, notifications, support, public, calculs, room_live, prospects, idp, outils, boutons_flottants
from app.db import pool_central
from app.security.appareils import AppareilRefuse, assurer_schema as assurer_schema_appareils
from app.security.tentatives import assurer_schema as assurer_schema_tentatives
from app.security.schema_central import assurer_schema_central
from fastapi.responses import JSONResponse
app = FastAPI(title="ERP Backend", version="0.1.0")

def _origines_cors() -> list[str]:
    """Origines autorisees a appeler l'API (variable CORS_ORIGINS, separees par
    des virgules). Par defaut : uniquement l'interface locale."""
    brut = os.getenv("CORS_ORIGINS", "")
    if brut.strip():
        return [o.strip() for o in brut.split(",") if o.strip()]
    return [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


# Acces depuis une autre machine du reseau local (ex. navigateur Windows -> VM
# en http://192.168.x.x:3000) : par defaut on accepte les adresses privees
# (192.168.*, 10.*, 172.16-31.*) sur les ports du frontend. En production,
# definir CORS_ORIGINS (liste exacte) et CORS_ORIGIN_REGEX="" pour le desactiver.
_REGEX_RESEAU_LOCAL = (
    r"^https?://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):(3000|5173)$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origines_cors(),
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", _REGEX_RESEAU_LOCAL) or None,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def entetes_securite(request, call_next):
    reponse = await call_next(request)
    reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
    reponse.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and reponse.headers.get("content-type", "").startswith("application/json"):
        reponse.headers.setdefault("Cache-Control", "no-store")
    return reponse

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(sessions.router_admin)
app.include_router(appareils.router)
app.include_router(appareils.router_admin)
app.include_router(entreprises.router)
app.include_router(admin.router)
app.include_router(utilisateurs.router)
app.include_router(roles.router)
app.include_router(utilisateurs_externes.router)
app.include_router(portail.router)
app.include_router(verification.router)
app.include_router(ventes.router)
app.include_router(achats.router)
app.include_router(fournisseurs.router)
app.include_router(prospects.router)
app.include_router(clients.router)
app.include_router(stock.router)
app.include_router(comptabilite.router)
app.include_router(assistant.router)
app.include_router(assistant_documents.router)
app.include_router(pipeline.router)
app.include_router(suggestions.router)
app.include_router(notifications.router)
app.include_router(support.router)
app.include_router(public.router)
app.include_router(calculs.router)
app.include_router(idp.router)
app.include_router(outils.router)
app.include_router(room_live.router)
app.include_router(boutons_flottants.router)


@app.on_event("startup")
def preparer_notifications():
    """Crée la table des notifications sur une base existante (voir notifications.py)."""
    try:
        notifications.assurer_table()
    except Exception:
        import logging
        logging.getLogger("erp.notifications").exception(
            "Table des notifications non créée au démarrage (nouvel essai à la première utilisation)"
        )


@app.exception_handler(AppareilRefuse)
async def appareil_refuse(request, exc):
    return JSONResponse(status_code=403, content={"message": exc.message})


def verifier_configuration() -> None:
    """Refuse de demarrer avec un secret JWT absent ou trop court."""
    if len(os.environ.get("JWT_SECRET", "")) < 32:
        raise RuntimeError("JWT_SECRET absent ou trop court (32 caracteres minimum).")


def assurer_index_sessions() -> None:
    """Index sur session_utilisateur.expire_le (nettoyage des sessions a chaque
    connexion). Idempotent ; ne bloque jamais le demarrage."""
    try:
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_session_utilisateur_expire "
                    "ON session_utilisateur (expire_le)"
                )
            conn.commit()
        finally:
            pool_central.putconn(conn)
    except Exception:
        logging.getLogger("erp.securite").exception("Index des sessions non cree au demarrage")


@app.on_event("startup")
def preparer_securite():
    verifier_configuration()
    assurer_index_sessions()
    assurer_schema_appareils()
    assurer_schema_tentatives()
    assurer_schema_central()


@app.get("/api/health")
def health():
    return {"status": "ok"}
>>>>>>> 50a24f0 (Boutons flottants :administration dynamique)
