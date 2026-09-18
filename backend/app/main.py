from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, entreprises, admin, utilisateurs, roles

app = FastAPI(title="ERP Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(entreprises.router)
app.include_router(admin.router)
app.include_router(utilisateurs.router)
app.include_router(roles.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
