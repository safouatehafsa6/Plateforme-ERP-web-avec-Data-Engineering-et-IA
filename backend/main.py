import os
import psycopg2
from fastapi import FastAPI

app = FastAPI(title="ERP Backend - Test de connexion")


@app.get("/")
def racine():
    return {"message": "Backend ERP opérationnel"}


@app.get("/health")
def health():
    """Vérifie que le backend répond correctement."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Vérifie que le backend arrive à se connecter à postgres-erp
    et que le script d'initialisation a bien créé les tables."""
    try:
        conn = psycopg2.connect(
            host="postgres-erp",
            dbname=os.getenv("ERP_DB_NAME", "erp_db"),
            user=os.getenv("ERP_DB_USER", "erp_user"),
            password=os.getenv("ERP_DB_PASSWORD", "erp_password"),
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return {"status": "connecté", "tables_trouvees": tables}
    except Exception as e:
        return {"status": "erreur", "detail": str(e)}
