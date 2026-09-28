from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/achats", tags=["achats"])


class LigneAchat(BaseModel):
    produitId: int
    quantite: int = Field(gt=0)
    prixUnitaire: Decimal = Field(ge=0)


class LigneDemande(BaseModel):
    produitId: int
    quantite: int = Field(gt=0)
    prixEstime: Decimal = Field(default=Decimal("0"), ge=0)


class DemandePayload(BaseModel):
    lignes: list[LigneDemande]
    notes: str | None = None


class BonCommandePayload(BaseModel):
    fournisseurId: int
    lignes: list[LigneAchat]
    demandeId: int | None = None
    notes: str | None = None


class StatutPayload(BaseModel):
    statut: str


class ReceptionPayload(BaseModel):
    lignes: list[dict]
    notes: str | None = None


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _total(lignes):
    total = Decimal("0")
    for l in lignes:
        prix = getattr(l, "prixUnitaire", getattr(l, "prixEstime", Decimal("0")))
        total += prix * l.quantite
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _numero(cur, prefixe: str, sequence: str) -> str:
    cur.execute(f"SELECT nextval('{sequence}')")
    n = cur.fetchone()[0]
    return f"{prefixe}-{datetime.now().year}-{n:06d}"


def _verifier_produits(cur, lignes):
    if not lignes:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne.")
    ids = sorted({l.produitId for l in lignes})
    cur.execute("SELECT id FROM produit WHERE id = ANY(%s)", (ids,))
    trouves = {r[0] for r in cur.fetchall()}
    manquants = [i for i in ids if i not in trouves]
    if manquants:
        raise HTTPException(status_code=400, detail=f"Produit(s) introuvable(s) : {manquants}.")


def _lignes(cur, table, fk, doc_id):
    cur.execute(
        f"""
        SELECT l.id, l.produit_id, p.reference, p.nom AS produit_nom,
               l.quantite,
               {('l.prix_estime' if table == 'ligne_demande_achat' else 'l.prix_unitaire')} AS prix_unitaire
               {", COALESCE((SELECT SUM(lr.quantite) FROM ligne_reception_achat lr JOIN reception_achat rr ON rr.id=lr.reception_id WHERE rr.achat_id=l.achat_id AND rr.statut='receptionnee' AND lr.produit_id=l.produit_id),0) AS quantite_recue" if table == 'ligne_achat' else ''}
        FROM {table} l
        JOIN produit p ON p.id = l.produit_id
        WHERE l.{fk} = %s ORDER BY l.id
        """,
        (doc_id,),
    )
    return _dicts(cur)


@router.get("/references")
def references(utilisateur=Depends(exiger_permission("achats", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, email, telephone, adresse FROM fournisseur ORDER BY nom")
            fournisseurs = _dicts(cur)
            cur.execute("SELECT id, reference, nom, categorie, prix_unitaire, stock_actuel FROM produit ORDER BY nom")
            produits = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"fournisseurs": fournisseurs, "produits": produits}


@router.get("/demandes")
def lister_demandes(utilisateur=Depends(exiger_permission("achats", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, d.numero, d.date_demande, d.statut, d.montant_estime, d.notes,
                       d.demandeur_id, COALESCE(u.prenom || ' ' || u.nom, '—') AS demandeur_nom,
                       a.id AS achat_id, a.numero AS achat_numero
                FROM demande_achat d
                LEFT JOIN utilisateur u ON u.id=d.demandeur_id
                LEFT JOIN achat a ON a.demande_id=d.id
                ORDER BY d.date_demande DESC, d.id DESC
            """)
            docs = _dicts(cur)
            for d in docs:
                d["lignes"] = _lignes(cur, "ligne_demande_achat", "demande_id", d["id"])
    finally:
        pool.putconn(conn)
    return {"demandes": docs}


@router.post("/demandes")
def creer_demande(payload: DemandePayload, utilisateur=Depends(exiger_permission("achats", "creer"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            _verifier_produits(cur, payload.lignes)
            numero = _numero(cur, "DA", "seq_demande_achat_numero")
            montant = _total(payload.lignes)
            cur.execute(
                """INSERT INTO demande_achat (numero, demandeur_id, montant_estime, notes)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (numero, utilisateur.get("id"), montant, payload.notes),
            )
            did = cur.fetchone()[0]
            cur.executemany(
                "INSERT INTO ligne_demande_achat (demande_id, produit_id, quantite, prix_estime) VALUES (%s,%s,%s,%s)",
                [(did, l.produitId, l.quantite, l.prixEstime) for l in payload.lignes],
            )
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": did, "numero": numero, "message": "Demande d'achat créée."}


@router.patch("/demandes/{demande_id}/statut")
def statut_demande(demande_id: int, payload: StatutPayload, utilisateur=Depends(exiger_permission("achats", "valider"))):
    if payload.statut not in {"brouillon", "soumise", "annulee"}:
        raise HTTPException(status_code=400, detail="Statut de demande invalide.")
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM demande_achat WHERE id=%s FOR UPDATE", (demande_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
            if row[0] == "convertie": raise HTTPException(status_code=400, detail="Une demande déjà convertie ne peut plus être modifiée.")
            cur.execute("UPDATE demande_achat SET statut=%s, date_modification=NOW() WHERE id=%s", (payload.statut, demande_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"message": "Statut de la demande mis à jour."}


@router.get("/bons-commande")
def lister_bons_commande(utilisateur=Depends(exiger_permission("achats", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT a.id, a.numero, a.date_achat, a.statut, a.montant_total, a.notes,
                       f.id AS fournisseur_id, f.nom AS fournisseur_nom,
                       a.demande_id, d.numero AS demande_numero
                FROM achat a JOIN fournisseur f ON f.id=a.fournisseur_id
                LEFT JOIN demande_achat d ON d.id=a.demande_id
                ORDER BY a.date_achat DESC, a.id DESC
            """)
            docs = _dicts(cur)
            for d in docs:
                d["lignes"] = _lignes(cur, "ligne_achat", "achat_id", d["id"])
    finally:
        pool.putconn(conn)
    return {"bonsCommande": docs}


@router.post("/bons-commande")
def creer_bon_commande(payload: BonCommandePayload, utilisateur=Depends(exiger_permission("achats", "creer"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM fournisseur WHERE id=%s", (payload.fournisseurId,))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Fournisseur introuvable.")
            _verifier_produits(cur, payload.lignes)
            if payload.demandeId:
                cur.execute("SELECT statut FROM demande_achat WHERE id=%s FOR UPDATE", (payload.demandeId,))
                demande = cur.fetchone()
                if not demande: raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
                if demande[0] != "soumise": raise HTTPException(status_code=400, detail="La demande doit être soumise avant conversion.")
            numero = _numero(cur, "ACH", "seq_achat_numero")
            montant = _total(payload.lignes)
            cur.execute(
                """INSERT INTO achat (fournisseur_id, statut, montant_total, numero, demande_id, notes)
                   VALUES (%s,'commande',%s,%s,%s,%s) RETURNING id""",
                (payload.fournisseurId, montant, numero, payload.demandeId, payload.notes),
            )
            aid = cur.fetchone()[0]
            cur.executemany(
                "INSERT INTO ligne_achat (achat_id, produit_id, quantite, prix_unitaire) VALUES (%s,%s,%s,%s)",
                [(aid, l.produitId, l.quantite, l.prixUnitaire) for l in payload.lignes],
            )
            if payload.demandeId:
                cur.execute("UPDATE demande_achat SET statut='convertie', date_modification=NOW() WHERE id=%s", (payload.demandeId,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": aid, "numero": numero, "message": "Bon de commande fournisseur créé."}


@router.patch("/bons-commande/{achat_id}/statut")
def statut_bon_commande(achat_id: int, payload: StatutPayload, utilisateur=Depends(exiger_permission("achats", "valider"))):
    if payload.statut not in {"commande", "annulee"}:
        raise HTTPException(status_code=400, detail="Statut de bon de commande invalide.")
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM achat WHERE id=%s FOR UPDATE", (achat_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Bon de commande introuvable.")
            if row[0] in {"reception_partielle", "receptionne"} and payload.statut == "annulee":
                raise HTTPException(status_code=400, detail="Un bon déjà réceptionné ne peut pas être annulé.")
            cur.execute("UPDATE achat SET statut=%s, date_modification=NOW() WHERE id=%s", (payload.statut, achat_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"message": "Statut du bon de commande mis à jour."}


@router.post("/demandes/{demande_id}/convertir")
def convertir_demande(demande_id: int, fournisseur_id: int, utilisateur=Depends(exiger_permission("achats", "valider"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM demande_achat WHERE id=%s FOR UPDATE", (demande_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
            if row[0] != "soumise": raise HTTPException(status_code=400, detail="La demande doit être soumise avant conversion.")
            cur.execute("SELECT 1 FROM fournisseur WHERE id=%s", (fournisseur_id,))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Fournisseur introuvable.")
            cur.execute("SELECT produit_id, quantite, prix_estime FROM ligne_demande_achat WHERE demande_id=%s ORDER BY id", (demande_id,))
            lignes = cur.fetchall()
            if not lignes: raise HTTPException(status_code=400, detail="La demande ne contient aucune ligne.")
            numero = _numero(cur, "ACH", "seq_achat_numero")
            montant = sum((Decimal(str(x[2])) * x[1] for x in lignes), Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cur.execute("SELECT notes FROM demande_achat WHERE id=%s", (demande_id,))
            notes = cur.fetchone()[0]
            cur.execute("INSERT INTO achat (fournisseur_id, statut, montant_total, numero, demande_id, notes) VALUES (%s,'commande',%s,%s,%s,%s) RETURNING id", (fournisseur_id, montant, numero, demande_id, notes))
            aid = cur.fetchone()[0]
            cur.executemany("INSERT INTO ligne_achat (achat_id, produit_id, quantite, prix_unitaire) VALUES (%s,%s,%s,%s)", [(aid, p, q, pr) for p,q,pr in lignes])
            cur.execute("UPDATE demande_achat SET statut='convertie', date_modification=NOW() WHERE id=%s", (demande_id,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": aid, "numero": numero, "message": "Demande convertie en bon de commande."}


@router.post("/bons-commande/{achat_id}/receptionner")
def receptionner(achat_id: int, payload: ReceptionPayload, utilisateur=Depends(exiger_permission("achats", "valider"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT numero, statut FROM achat WHERE id=%s FOR UPDATE", (achat_id,))
            achat = cur.fetchone()
            if not achat: raise HTTPException(status_code=404, detail="Bon de commande introuvable.")
            if achat[1] == "annulee": raise HTTPException(status_code=400, detail="Un bon annulé ne peut pas être réceptionné.")
            if not payload.lignes: raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne à la réception.")

            cur.execute("SELECT produit_id, quantite FROM ligne_achat WHERE achat_id=%s", (achat_id,))
            commandes = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("""SELECT lr.produit_id, COALESCE(SUM(lr.quantite),0)
                           FROM ligne_reception_achat lr JOIN reception_achat r ON r.id=lr.reception_id
                           WHERE r.achat_id=%s AND r.statut='receptionnee' GROUP BY lr.produit_id""", (achat_id,))
            deja = {r[0]: r[1] for r in cur.fetchall()}

            lignes_valides = []
            for item in payload.lignes:
                try:
                    produit_id = int(item.get("produitId"))
                    quantite = int(item.get("quantite"))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail="Ligne de réception invalide.")
                if produit_id not in commandes:
                    raise HTTPException(status_code=400, detail=f"Le produit {produit_id} n'appartient pas au bon de commande.")
                restante = commandes[produit_id] - deja.get(produit_id, 0)
                if quantite <= 0 or quantite > restante:
                    raise HTTPException(status_code=400, detail=f"Quantité reçue invalide pour le produit {produit_id}. Restant : {restante}.")
                lignes_valides.append((produit_id, quantite))

            numero = _numero(cur, "REC", "seq_reception_achat_numero")
            cur.execute("INSERT INTO reception_achat (achat_id, numero, notes) VALUES (%s,%s,%s) RETURNING id", (achat_id, numero, payload.notes))
            rid = cur.fetchone()[0]
            cur.executemany("INSERT INTO ligne_reception_achat (reception_id, produit_id, quantite) VALUES (%s,%s,%s)", [(rid,p,q) for p,q in lignes_valides])

            for produit_id, quantite in lignes_valides:
                cur.execute("UPDATE produit SET stock_actuel = COALESCE(stock_actuel,0) + %s WHERE id=%s", (quantite, produit_id))
                cur.execute("INSERT INTO mouvement_stock (produit_id, type_mouvement, quantite, reference_doc) VALUES (%s,'entree',%s,%s)", (produit_id, quantite, numero))

            nouveau_total_recu = dict(deja)
            for p,q in lignes_valides: nouveau_total_recu[p] = nouveau_total_recu.get(p,0) + q
            complet = all(nouveau_total_recu.get(p,0) >= q for p,q in commandes.items())
            statut = "receptionne" if complet else "reception_partielle"
            cur.execute("UPDATE achat SET statut=%s, date_modification=NOW() WHERE id=%s", (statut, achat_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)
    return {"id": rid, "numero": numero, "message": "Réception enregistrée et stock mis à jour."}


@router.get("/receptions")
def lister_receptions(utilisateur=Depends(exiger_permission("achats", "consulter"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, r.numero, r.date_reception, r.statut, r.notes,
                       a.id AS achat_id, a.numero AS achat_numero, f.nom AS fournisseur_nom
                FROM reception_achat r JOIN achat a ON a.id=r.achat_id
                JOIN fournisseur f ON f.id=a.fournisseur_id
                ORDER BY r.date_reception DESC, r.id DESC
            """)
            docs = _dicts(cur)
            for d in docs:
                cur.execute("""SELECT lr.id, lr.produit_id, p.reference, p.nom AS produit_nom, lr.quantite
                               FROM ligne_reception_achat lr JOIN produit p ON p.id=lr.produit_id
                               WHERE lr.reception_id=%s ORDER BY lr.id""", (d["id"],))
                d["lignes"] = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"receptions": docs}
