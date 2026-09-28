from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/ventes", tags=["ventes"])


class LigneDocument(BaseModel):
    produitId: int
    quantite: int = Field(gt=0)
    prixUnitaire: Decimal = Field(ge=0)
    remisePct: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class DocumentPayload(BaseModel):
    clientId: int
    lignes: list[LigneDocument]
    notes: str | None = None


class DevisPayload(DocumentPayload):
    dateValidite: date | None = None


class StatutPayload(BaseModel):
    statut: str


class LivraisonPayload(BaseModel):
    adresseLivraison: str | None = None
    notes: str | None = None


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _total(lignes: list[LigneDocument]) -> Decimal:
    total = Decimal("0")
    for l in lignes:
        total += l.prixUnitaire * l.quantite * (Decimal("1") - l.remisePct / Decimal("100"))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _verifier_client_et_produits(cur, client_id: int, lignes: list[LigneDocument]):
    if not lignes:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne au document.")
    cur.execute("SELECT 1 FROM client WHERE id = %s", (client_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Client introuvable.")
    ids = sorted({l.produitId for l in lignes})
    cur.execute("SELECT id FROM produit WHERE id = ANY(%s)", (ids,))
    trouves = {r[0] for r in cur.fetchall()}
    manquants = [i for i in ids if i not in trouves]
    if manquants:
        raise HTTPException(status_code=400, detail=f"Produit(s) introuvable(s) : {manquants}.")


def _numero(cur, prefixe: str, sequence: str) -> str:
    cur.execute(f"SELECT nextval('{sequence}')")
    n = cur.fetchone()[0]
    return f"{prefixe}-{datetime.now().year}-{n:06d}"


def _charger_lignes(cur, table: str, fk: str, document_id: int):
    cur.execute(
        f"""
        SELECT l.id, l.produit_id, p.reference, p.nom AS produit_nom,
               l.quantite, l.prix_unitaire, l.remise_pct,
               ROUND((l.quantite * l.prix_unitaire * (1 - l.remise_pct / 100.0))::numeric, 2) AS total_ligne
        FROM {table} l
        JOIN produit p ON p.id = l.produit_id
        WHERE l.{fk} = %s
        ORDER BY l.id
        """,
        (document_id,),
    )
    return _dicts(cur)


@router.get("/references")
def references(utilisateur=Depends(exiger_permission("ventes", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, email, telephone, adresse FROM client ORDER BY nom")
            clients = _dicts(cur)
            cur.execute("SELECT id, reference, nom, categorie, prix_unitaire, stock_actuel FROM produit ORDER BY nom")
            produits = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"clients": clients, "produits": produits}


@router.get("/devis")
def lister_devis(utilisateur=Depends(exiger_permission("ventes", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, d.numero, d.date_devis, d.date_validite, d.statut,
                       d.montant_total, d.notes, c.id AS client_id, c.nom AS client_nom,
                       cmd.id AS commande_id, cmd.numero AS commande_numero
                FROM devis d
                JOIN client c ON c.id = d.client_id
                LEFT JOIN commande cmd ON cmd.devis_id = d.id
                ORDER BY d.date_devis DESC, d.id DESC
            """)
            docs = _dicts(cur)
            for d in docs:
                d["lignes"] = _charger_lignes(cur, "ligne_devis", "devis_id", d["id"])
    finally:
        pool.putconn(conn)
    return {"devis": docs}


@router.post("/devis")
def creer_devis(payload: DevisPayload, utilisateur=Depends(exiger_permission("ventes", "creer"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            _verifier_client_et_produits(cur, payload.clientId, payload.lignes)
            numero = _numero(cur, "DEV", "seq_devis_numero")
            montant = _total(payload.lignes)
            cur.execute(
                """INSERT INTO devis (client_id, numero, date_validite, montant_total, notes)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (payload.clientId, numero, payload.dateValidite, montant, payload.notes),
            )
            doc_id = cur.fetchone()[0]
            cur.executemany(
                """INSERT INTO ligne_devis (devis_id, produit_id, quantite, prix_unitaire, remise_pct)
                   VALUES (%s,%s,%s,%s,%s)""",
                [(doc_id, l.produitId, l.quantite, l.prixUnitaire, l.remisePct) for l in payload.lignes],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    return {"id": doc_id, "numero": numero, "message": "Devis créé."}


@router.put("/devis/{devis_id}")
def modifier_devis(devis_id: int, payload: DevisPayload, utilisateur=Depends(exiger_permission("ventes", "modifier"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM devis WHERE id=%s", (devis_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Devis introuvable.")
            if row[0] not in ("brouillon", "envoye"):
                raise HTTPException(status_code=400, detail="Seul un devis brouillon ou envoyé peut être modifié.")
            _verifier_client_et_produits(cur, payload.clientId, payload.lignes)
            cur.execute(
                """UPDATE devis SET client_id=%s, date_validite=%s, montant_total=%s, notes=%s,
                   date_modification=NOW() WHERE id=%s""",
                (payload.clientId, payload.dateValidite, _total(payload.lignes), payload.notes, devis_id),
            )
            cur.execute("DELETE FROM ligne_devis WHERE devis_id=%s", (devis_id,))
            cur.executemany(
                "INSERT INTO ligne_devis (devis_id, produit_id, quantite, prix_unitaire, remise_pct) VALUES (%s,%s,%s,%s,%s)",
                [(devis_id, l.produitId, l.quantite, l.prixUnitaire, l.remisePct) for l in payload.lignes],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    return {"message": "Devis modifié."}


@router.patch("/devis/{devis_id}/statut")
def statut_devis(devis_id: int, payload: StatutPayload, utilisateur=Depends(exiger_permission("ventes", "valider"))):
    autorises = {"brouillon", "envoye", "accepte", "refuse", "expire", "annule"}
    if payload.statut not in autorises:
        raise HTTPException(status_code=400, detail="Statut de devis invalide.")
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE devis SET statut=%s, date_modification=NOW() WHERE id=%s RETURNING id", (payload.statut, devis_id))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Devis introuvable.")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"message": "Statut du devis mis à jour."}


@router.post("/devis/{devis_id}/convertir")
def convertir_devis(devis_id: int, utilisateur=Depends(exiger_permission("ventes", "valider"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT client_id, statut, montant_total, notes FROM devis WHERE id=%s FOR UPDATE", (devis_id,))
            d = cur.fetchone()
            if not d: raise HTTPException(status_code=404, detail="Devis introuvable.")
            if d[1] not in ("envoye", "accepte"):
                raise HTTPException(status_code=400, detail="Le devis doit être envoyé ou accepté avant conversion.")
            cur.execute("SELECT id, numero FROM commande WHERE devis_id=%s", (devis_id,))
            existe = cur.fetchone()
            if existe: return {"id": existe[0], "numero": existe[1], "message": "Ce devis est déjà converti."}
            numero = _numero(cur, "CMD", "seq_commande_numero")
            cur.execute("""INSERT INTO commande (client_id, statut, montant_total, numero, devis_id, notes)
                           VALUES (%s,'confirmee',%s,%s,%s,%s) RETURNING id""", (d[0], d[2], numero, devis_id, d[3]))
            commande_id = cur.fetchone()[0]
            cur.execute("""INSERT INTO ligne_commande (commande_id, produit_id, quantite, prix_unitaire, remise_pct)
                           SELECT %s, produit_id, quantite, prix_unitaire, remise_pct FROM ligne_devis WHERE devis_id=%s""", (commande_id, devis_id))
            cur.execute("UPDATE devis SET statut='accepte', date_modification=NOW() WHERE id=%s", (devis_id,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": commande_id, "numero": numero, "message": "Devis converti en commande."}


@router.get("/commandes")
def lister_commandes(utilisateur=Depends(exiger_permission("ventes", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.numero, c.date_commande, c.statut, c.montant_total, c.notes,
                       cl.id AS client_id, cl.nom AS client_nom, c.devis_id,
                       d.numero AS devis_numero
                FROM commande c JOIN client cl ON cl.id=c.client_id
                LEFT JOIN devis d ON d.id=c.devis_id
                ORDER BY c.date_commande DESC, c.id DESC
            """)
            docs = _dicts(cur)
            for d in docs: d["lignes"] = _charger_lignes(cur, "ligne_commande", "commande_id", d["id"])
    finally: pool.putconn(conn)
    return {"commandes": docs}


@router.post("/commandes")
def creer_commande(payload: DocumentPayload, utilisateur=Depends(exiger_permission("ventes", "creer"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            _verifier_client_et_produits(cur, payload.clientId, payload.lignes)
            numero = _numero(cur, "CMD", "seq_commande_numero")
            cur.execute("INSERT INTO commande (client_id, statut, montant_total, numero, notes) VALUES (%s,'confirmee',%s,%s,%s) RETURNING id", (payload.clientId, _total(payload.lignes), numero, payload.notes))
            cid = cur.fetchone()[0]
            cur.executemany("INSERT INTO ligne_commande (commande_id, produit_id, quantite, prix_unitaire, remise_pct) VALUES (%s,%s,%s,%s,%s)", [(cid,l.produitId,l.quantite,l.prixUnitaire,l.remisePct) for l in payload.lignes])
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": cid, "numero": numero, "message": "Commande créée."}


@router.post("/commandes/{commande_id}/livrer")
def creer_bl(commande_id: int, payload: LivraisonPayload, utilisateur=Depends(exiger_permission("ventes", "valider"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM commande WHERE id=%s FOR UPDATE", (commande_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Commande introuvable.")
            if row[0] in ("annulee",): raise HTTPException(status_code=400, detail="Une commande annulée ne peut pas être livrée.")
            numero = _numero(cur, "BL", "seq_bl_numero")
            cur.execute("INSERT INTO bon_livraison (commande_id, numero, adresse_livraison, notes) VALUES (%s,%s,%s,%s) RETURNING id", (commande_id, numero, payload.adresseLivraison, payload.notes))
            bl_id = cur.fetchone()[0]
            cur.execute("INSERT INTO ligne_bon_livraison (bon_livraison_id, produit_id, quantite) SELECT %s, produit_id, quantite FROM ligne_commande WHERE commande_id=%s", (bl_id, commande_id))
            cur.execute("UPDATE commande SET statut='livree', date_modification=NOW() WHERE id=%s", (commande_id,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": bl_id, "numero": numero, "message": "Bon de livraison créé."}


@router.get("/bons-livraison")
def lister_bl(utilisateur=Depends(exiger_permission("ventes", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT bl.id, bl.numero, bl.date_livraison, bl.statut, bl.adresse_livraison, bl.notes,
                                  c.id AS commande_id, c.numero AS commande_numero, cl.nom AS client_nom
                           FROM bon_livraison bl JOIN commande c ON c.id=bl.commande_id
                           JOIN client cl ON cl.id=c.client_id ORDER BY bl.date_livraison DESC, bl.id DESC""")
            docs = _dicts(cur)
            for d in docs:
                cur.execute("""SELECT l.id, l.produit_id, p.reference, p.nom AS produit_nom, l.quantite
                               FROM ligne_bon_livraison l JOIN produit p ON p.id=l.produit_id
                               WHERE l.bon_livraison_id=%s ORDER BY l.id""", (d["id"],))
                d["lignes"] = _dicts(cur)
    finally: pool.putconn(conn)
    return {"bonsLivraison": docs}


@router.post("/commandes/{commande_id}/facturer")
def facturer_commande(commande_id: int, utilisateur=Depends(exiger_permission("facturation", "creer"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, numero FROM facture WHERE commande_id=%s ORDER BY id LIMIT 1", (commande_id,))
            existe = cur.fetchone()
            if existe: return {"id": existe[0], "numero": existe[1], "message": "Cette commande est déjà facturée."}
            cur.execute("SELECT montant_total, statut FROM commande WHERE id=%s", (commande_id,))
            c = cur.fetchone()
            if not c: raise HTTPException(status_code=404, detail="Commande introuvable.")
            if c[1] == "annulee": raise HTTPException(status_code=400, detail="Une commande annulée ne peut pas être facturée.")
            numero = _numero(cur, "FAC", "seq_facture_numero")
            cur.execute("""INSERT INTO facture (commande_id, numero, montant_total, statut, code_verification)
                           VALUES (%s,%s,%s,'impayee',encode(gen_random_bytes(24),'hex')) RETURNING id""", (commande_id, numero, c[0]))
            fid = cur.fetchone()[0]
            cur.execute("""INSERT INTO ligne_facture (facture_id, produit_id, designation, quantite, prix_unitaire, remise_pct)
                           SELECT %s, lc.produit_id, p.nom, lc.quantite, lc.prix_unitaire, lc.remise_pct
                           FROM ligne_commande lc JOIN produit p ON p.id=lc.produit_id WHERE lc.commande_id=%s""", (fid, commande_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": fid, "numero": numero, "message": "Facture créée."}


@router.get("/factures")
def lister_factures(utilisateur=Depends(exiger_permission("facturation", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT f.id, f.numero, f.date_facture, f.montant_total, f.statut,
                                  c.id AS commande_id, c.numero AS commande_numero, cl.nom AS client_nom
                           FROM facture f LEFT JOIN commande c ON c.id=f.commande_id
                           LEFT JOIN client cl ON cl.id=c.client_id
                           ORDER BY f.date_facture DESC, f.id DESC""")
            docs = _dicts(cur)
            for d in docs:
                cur.execute("SELECT id, produit_id, designation, quantite, prix_unitaire, remise_pct FROM ligne_facture WHERE facture_id=%s ORDER BY id", (d["id"],))
                d["lignes"] = _dicts(cur)
    finally: pool.putconn(conn)
    return {"factures": docs}


@router.patch("/factures/{facture_id}/statut")
def statut_facture(facture_id: int, payload: StatutPayload, utilisateur=Depends(exiger_permission("facturation", "valider"))):
    if payload.statut not in {"impayee", "payee", "annulee"}:
        raise HTTPException(status_code=400, detail="Statut de facture invalide.")
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE facture SET statut=%s WHERE id=%s RETURNING id", (payload.statut, facture_id))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Facture introuvable.")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"message": "Statut de facture mis à jour."}
