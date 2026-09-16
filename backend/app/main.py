from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, entreprises
from app.routers import utilisateurs
from app.routers import roles_permissions

app = FastAPI(title="ERP Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(utilisateurs.router)
app.include_router(roles_permissions.router)
app.include_router(entreprises.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
