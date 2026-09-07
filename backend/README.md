# Backend ERP — FastAPI

## Démarrage local (hors Docker)

```bash
python3 -m venv venv
source venv/bin/activate          # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # puis adapter les valeurs si besoin
python3 -m app.scripts.seed       # crée un compte de test
uvicorn app.main:app --reload --port 8000
```

Documentation interactive générée automatiquement par FastAPI :
http://localhost:8000/docs

## Compte de test créé par le script seed

- email : admin@benjeddou-erp.ma
- mot de passe : Test1234!

## Endpoints disponibles

- `GET /api/health` — vérifie que le serveur répond
- `GET /api/auth/captcha` — génère un nouveau CAPTCHA local (image SVG)
- `POST /api/auth/login` — connexion, avec protection multicouche
  (captcha après 2 échecs, reCAPTCHA après 4 échecs)
