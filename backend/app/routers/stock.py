from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/stock", tags=["stock"])


class ProduitPayload(BaseModel):
    reference: str = Field(min_length=1, max_length=50)
    nom: str = Field(min_length=1, max_length=150)
    categorie: str | None = Field(default=None, max_length=100)
    prixUnitaire: float = Field(ge=0)


class MouvementPayload(BaseModel):
    produitId: int
    typeMouvement: str
    quantite: int = Field(gt=0)
    referenceDoc: str | None = Field(default=None, max_length=100)


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@router.get("")
def lister_stock(utilisateur=Depends(exiger_permission("stock", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.reference, p.nom, p.categorie, p.prix_unitaire,
                       COALESCE(p.stock_actuel, 0) AS stock_actuel,
                       COUNT(ms.id) AS nombre_mouvements
                FROM produit p
                LEFT JOIN mouvement_stock ms ON ms.produit_id = p.id
                GROUP BY p.id, p.reference, p.nom, p.categorie, p.prix_unitaire, p.stock_actuel
                ORDER BY p.nom, p.id
            """)
            return {"produits": _dicts(cur)}
    finally:
        pool.putconn(conn)


@router.get("/{produit_id}/mouvements")
def lister_mouvements(produit_id: int, utilisateur=Depends(exiger_permission("stock", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM produit WHERE id=%s", (produit_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Produit introuvable.")
            cur.execute("""
                SELECT id, produit_id, type_mouvement, quantite, date_mouvement, reference_doc
                FROM mouvement_stock WHERE produit_id=%s ORDER BY date_mouvement DESC, id DESC
            """, (produit_id,))
            return {"mouvements": _dicts(cur)}
    finally:
        pool.putconn(conn)


@router.post("/produits")
def creer_produit(payload: ProduitPayload, utilisateur=Depends(exiger_permission("stock", "creer"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM produit WHERE LOWER(reference)=LOWER(%s)", (payload.reference.strip(),))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Cette référence produit existe déjà.")
            cur.execute("""INSERT INTO produit(reference, nom, categorie, prix_unitaire, stock_actuel)
                           VALUES(%s,%s,%s,%s,0)
                           RETURNING id, reference, nom, categorie, prix_unitaire, stock_actuel""",
                        (payload.reference.strip(), payload.nom.strip(), payload.categorie.strip() if payload.categorie else None, payload.prixUnitaire))
            row = cur.fetchone(); result = dict(zip([d[0] for d in cur.description], row))
        conn.commit(); return {"produit": result, "message": "Produit créé avec succès."}
    except HTTPException:
        conn.rollback(); raise
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)


@router.patch("/produits/{produit_id}")
def modifier_produit(produit_id: int, payload: ProduitPayload, utilisateur=Depends(exiger_permission("stock", "modifier"))):
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM produit WHERE id=%s", (produit_id,))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Produit introuvable.")
            cur.execute("SELECT 1 FROM produit WHERE LOWER(reference)=LOWER(%s) AND id<>%s", (payload.reference.strip(), produit_id))
            if cur.fetchone(): raise HTTPException(status_code=409, detail="Cette référence produit existe déjà.")
            cur.execute("""UPDATE produit SET reference=%s, nom=%s, categorie=%s, prix_unitaire=%s
                           WHERE id=%s RETURNING id, reference, nom, categorie, prix_unitaire, stock_actuel""",
                        (payload.reference.strip(), payload.nom.strip(), payload.categorie.strip() if payload.categorie else None, payload.prixUnitaire, produit_id))
            row = cur.fetchone(); result = dict(zip([d[0] for d in cur.description], row))
        conn.commit(); return {"produit": result, "message": "Produit modifié avec succès."}
    except HTTPException:
        conn.rollback(); raise
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)


@router.post("/mouvements")
def creer_mouvement(payload: MouvementPayload, utilisateur=Depends(exiger_permission("stock", "creer"))):
    type_mouvement = payload.typeMouvement.lower().strip()
    if type_mouvement not in {"entree", "sortie", "ajustement"}:
        raise HTTPException(status_code=400, detail="Type de mouvement invalide : entree, sortie ou ajustement.")
    pool = _pool(utilisateur); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_actuel FROM produit WHERE id=%s FOR UPDATE", (payload.produitId,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Produit introuvable.")
            stock = row[0] or 0
            if type_mouvement == "entree": nouveau = stock + payload.quantite; delta = payload.quantite
            elif type_mouvement == "sortie":
                if payload.quantite > stock: raise HTTPException(status_code=400, detail=f"Stock insuffisant. Stock actuel : {stock}.")
                nouveau = stock - payload.quantite; delta = -payload.quantite
            else:
                nouveau = payload.quantite; delta = nouveau - stock
            cur.execute("UPDATE produit SET stock_actuel=%s WHERE id=%s", (nouveau, payload.produitId))
            cur.execute("""INSERT INTO mouvement_stock(produit_id,type_mouvement,quantite,reference_doc)
                           VALUES(%s,%s,%s,%s) RETURNING id, produit_id, type_mouvement, quantite, date_mouvement, reference_doc""",
                        (payload.produitId, type_mouvement, delta if type_mouvement == "ajustement" else payload.quantite, payload.referenceDoc))
            result = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        conn.commit(); return {"mouvement": result, "stockActuel": nouveau, "message": "Mouvement enregistré et stock mis à jour."}
    except HTTPException:
        conn.rollback(); raise
    except Exception:
        conn.rollback(); raise
    finally:
        pool.putconn(conn)
