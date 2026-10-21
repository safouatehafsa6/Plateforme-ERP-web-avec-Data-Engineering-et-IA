import io, os, sys, json
os.environ.update(DB_HOST="localhost", DB_USER="erp_user", DB_PASSWORD="erp_password", DB_CENTRAL_NAME="erp_db",
                  JWT_SECRET="t", MINIO_ENDPOINT="x", MINIO_ROOT_USER="x", MINIO_ROOT_PASSWORD="x")
sys.path.insert(0, "/home/claude/Plateforme-ERP-web-avec-Data-Engineering-et-IA/backend")
from fastapi.testclient import TestClient
from app.main import app
from app.security.auth_dependency import utilisateur_connecte
from app.services import rag_documents as rag
from app.db import get_pool_entreprise

STORE = {}
rag.stocker_original = lambda cle, c, m: STORE.__setitem__(cle, c)
rag.supprimer_original = lambda cle: STORE.pop(cle, None)

def uid(base, email):
    p = get_pool_entreprise(base); c = p.getconn()
    try:
        with c.cursor() as cur:
            cur.execute("select u.id, r.nom from utilisateur u join role r on r.id=u.role_id where email=%s", (email,))
            return cur.fetchone()
    finally: p.putconn(c)

USERS = {}
for base in ("tenant_a", "tenant_b"):
    for kind, mail in (("admin", f"admin@{base}.test"), ("lect", f"lect@{base}.test")):
        i, role = uid(base, mail)
        USERS[f"{kind}_{base[-1]}"] = {"id": i, "email": mail, "role": role, "type": "interne", "nomBase": base, "entrepriseId": 1 if base == "tenant_a" else 2}
USERS["externe_a"] = {"id": 1, "email": "e@x", "role": "Utilisateur", "type": "externe", "nomBase": "tenant_a", "clientId": 1}
CUR = {"u": "admin_a"}
app.dependency_overrides[utilisateur_connecte] = lambda: dict(USERS[CUR["u"]])
cl = TestClient(app)

from reportlab.pdfgen import canvas
def pdf_bytes(lines):
    b = io.BytesIO(); c = canvas.Canvas(b); y = 800
    for l in lines: c.drawString(50, y, l); y -= 20
    c.showPage(); c.save(); return b.getvalue()
import docx
def docx_bytes(paras):
    d = docx.Document(); [d.add_paragraph(p) for p in paras]; b = io.BytesIO(); d.save(b); return b.getvalue()

res = []
def check(name, cond, info=""):
    cond = bool(cond); res.append(cond); print(("PASS " if cond else "FAIL ") + name, info)

def up(name, data, **kw):
    return cl.post("/api/assistant/documents/upload", files={"fichier": (name, data)}, data=kw)

PDF = pdf_bytes(["La virtualisation permet de partager un serveur physique entre plusieurs machines virtuelles.",
                 "Docker est un outil de conteneurisation qui isole les applications.",
                 "Un hyperviseur gere les machines virtuelles."])
r = up("Cours Virtualisation.pdf", PDF, titre="Cours virtualisation"); check("1 upload PDF admin", r.status_code == 201, r.text)
pid = r.json().get("id")
r = up("note.docx", docx_bytes(["Le delai de paiement standard des factures clients est de trente jours.", "Les remises sont validees par le directeur commercial."]))
check("2 upload DOCX", r.status_code == 201, r.text)
check("3 originaux dans (faux) MinIO, cle = uuid", len(STORE) == 2 and all(".." not in k and " " not in k for k in STORE), list(STORE))
r = cl.get("/api/assistant/documents"); check("4 liste", r.status_code == 200 and len(r.json()) == 2, str([d['titre'] for d in r.json()]))

r = cl.post("/api/assistant/chat", json={"message": "Qu'est-ce que la virtualisation et à quoi sert un hyperviseur ?", "langue": "fr"})
j = r.json(); check("5 question -> sources", r.status_code == 200 and j.get("sources") and "virtualisation" in j["reply"].lower(), j.get("reply", "")[:120])
check("6 source = fichier+page", j["sources"][0]["source"].startswith("Cours Virtualisation.pdf (p.1)"), j["sources"][0]["source"])
r = cl.post("/api/assistant/chat", json={"message": "Quel est le délai de paiement des factures ?", "langue": "fr"})
check("6b question DOCX", any("trente jours" in s["excerpt"] for s in r.json().get("sources", [])))
r = cl.post("/api/assistant/chat", json={"message": "Quelle est la capitale de la Norvege fjords ?", "langue": "fr"})
check("7 hors-sujet -> aucune source inventee", r.json().get("sources") == [], str(r.json().get("sources")))
r = cl.post("/api/assistant/chat", json={"message": "bonjour comment ça va", "langue": "fr"})
check("7b message banal non détourné", r.json().get("sources") == [])

CUR["u"] = "lect_a"
r = up("x.pdf", PDF); check("8 lecteur sans documents.creer -> 403", r.status_code == 403, r.text)
r = cl.delete(f"/api/assistant/documents/{pid}"); check("8b lecteur sans supprimer -> 403", r.status_code == 403)
r = cl.post("/api/assistant/chat", json={"message": "virtualisation hyperviseur", "langue": "fr"})
check("8c lecteur avec consulter voit les sources", len(r.json().get("sources", [])) > 0)
CUR["u"] = "externe_a"
r = cl.post("/api/assistant/chat", json={"message": "virtualisation hyperviseur"}); check("9 externe refusé (chat)", r.status_code == 403)
r = cl.get("/api/assistant/documents"); check("9b externe refusé (liste)", r.status_code == 403)
CUR["u"] = "admin_b"
r = cl.get("/api/assistant/documents"); check("10 autre entreprise : liste vide", r.json() == [])
r = cl.post("/api/assistant/chat", json={"message": "virtualisation hyperviseur", "langue": "fr"})
check("10b autre entreprise : aucune source", r.json().get("sources") == [])
r = cl.delete(f"/api/assistant/documents/{pid}"); check("10c autre entreprise ne peut pas supprimer", r.status_code == 404)

CUR["u"] = "admin_a"
r = up("gros.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024)); check("11 >10 Mo -> 413", r.status_code == 413, r.text)
r = up("virus.exe", b"MZ123"); check("11b format interdit -> 422", r.status_code == 422, r.text)
r = up("faux.pdf", b"juste du texte"); check("11c faux PDF (signature) -> 422", r.status_code == 422, r.text)
blank = io.BytesIO(); c = canvas.Canvas(blank); c.showPage(); c.save()
r = up("scan.pdf", blank.getvalue()); check("11d PDF sans texte -> 422 + mention OCR", r.status_code == 422 and "OCR" in r.text, r.text)
r = up("../../etc/passwd.pdf", PDF); check("11e nom piégé neutralisé", r.status_code == 201 and r.json()["nomFichier"] == "passwd.pdf", r.text)
n_before = len(STORE)

# échec DB après MinIO : rien ne doit rester
import psycopg2.extras
orig = psycopg2.extras.execute_values
import app.routers.assistant_documents as ad
def boom(*a, **k): raise RuntimeError("db down")
ad.execute_values = boom
r = up("rollback.pdf", PDF); ad.execute_values = orig
check("12 échec DB -> 500 propre, pas d'objet MinIO orphelin", r.status_code == 500 and len(STORE) == n_before and "db down" not in r.text, r.text)
p = get_pool_entreprise("tenant_a"); c = p.getconn()
with c.cursor() as cur: cur.execute("select count(*) from assistant_document where nom_fichier='rollback.pdf'"); orph = cur.fetchone()[0]
p.putconn(c); check("12b pas de métadonnée partielle", orph == 0)

r = cl.delete(f"/api/assistant/documents/{pid}"); check("13 suppression admin", r.status_code == 204)
r = cl.post("/api/assistant/chat", json={"message": "virtualisation hyperviseur", "langue": "fr"})
check("13b chunks supprimés (plus de source)", not any(s["source"].startswith("Cours Virtualisation") for s in r.json().get("sources", [])))
check("13c objet MinIO supprimé", not any(k.endswith(f"{pid}.pdf") for k in STORE))
r = cl.post("/api/assistant/chat", json={"message": "Synthèse des ventes", "langue": "fr"})
check("14 non-régression : analytics ventes répond toujours", r.status_code == 200 and r.json().get("reply"), r.json().get("reply", "")[:80])
print(f"\n{sum(res)}/{len(res)} OK"); sys.exit(0 if all(res) else 1)
