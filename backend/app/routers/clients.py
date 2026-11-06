from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_pool_entreprise
from app.schemas.clients import ClientPayload
from app.schemas.prospects import ArchivagePayload, SuiviPayload
from app.security.permissions import actions_autorisees, exiger_permission
from app.services import prospects as regles_prospects
from app.services.suivi_commercial import ecrire_evenement, lire_historique_client
from app.services.transactions import transaction_entreprise

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _clean(payload: ClientPayload):
    return (
        payload.nom.strip(),
        payload.email.strip() if payload.email else None,
        payload.telephone.strip() if payload.telephone else None,
        payload.adresse.strip() if payload.adresse else None,
    )


@router.get("/permissions")
def mes_permissions(utilisateur=Depends(exiger_permission("clients", "consulter"))):
    return {"module": "clients", "actions": actions_autorisees(utilisateur, "clients")}


@router.get("")
def lister_clients(
    archives: str = Query(default="actifs", pattern="^(actifs|archives|tous)$"),
    utilisateur=Depends(exiger_permission("clients", "consulter")),
):
    filtre = {"actifs": "WHERE NOT f.archive", "archives": "WHERE f.archive", "tous": ""}[archives]
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse, f.archive, f.archive_le, f.archive_motif,
                       COUNT(DISTINCT c.id) AS nombre_commandes
                FROM client f
                LEFT JOIN commande c ON c.client_id = f.id
                {filtre}
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse, f.archive, f.archive_le, f.archive_motif
                ORDER BY f.nom, f.id
                """
            )
            return {"clients": _dicts(cur)}
    finally:
        pool.putconn(conn)


@router.get("/verification-doublon")
def verifier_doublons_client(
    email: str | None = None,
    telephone: str | None = None,
    exclure_id: int | None = None,
    utilisateur=Depends(exiger_permission("clients", "consulter")),
):
    """Recherche les clients partageant l'e-mail ou le téléphone saisi."""
    email_nettoye = email.strip().lower() if email and email.strip() else None
    telephone_chiffres = "".join(ch for ch in telephone or "" if ch.isdigit())
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nom, email, telephone,
                       CASE
                         WHEN %s::text IS NOT NULL AND LOWER(TRIM(COALESCE(email, ''))) = %s THEN 'email'
                         WHEN %s <> '' AND regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s THEN 'telephone'
                       END AS champ
                FROM client
                WHERE (%s::text IS NOT NULL AND LOWER(TRIM(COALESCE(email, ''))) = %s)
                   OR (%s <> '' AND regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s)
                ORDER BY nom, id
                """,
                (email_nettoye, email_nettoye, telephone_chiffres, telephone_chiffres,
                 email_nettoye, email_nettoye, telephone_chiffres, telephone_chiffres),
            )
            rows = _dicts(cur)
            if exclure_id is not None:
                rows = [row for row in rows if row["id"] != exclure_id]
            return {"doublons": rows}
    finally:
        pool.putconn(conn)


@router.get("/{client_id}")
def obtenir_client(client_id: int, utilisateur=Depends(exiger_permission("clients", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse, f.archive, f.archive_le, f.archive_motif,
                       COUNT(DISTINCT c.id) AS nombre_commandes,
                       (SELECT p.id FROM prospect p WHERE p.client_id = f.id ORDER BY p.date_conversion LIMIT 1) AS prospect_origine_id
                FROM client f
                LEFT JOIN commande c ON c.client_id = f.id
                WHERE f.id = %s
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse, f.archive, f.archive_le, f.archive_motif
                """,
                (client_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Client introuvable.")
            return dict(zip([d[0] for d in cur.description], row))
    finally:
        pool.putconn(conn)


@router.post("")
def creer_client(payload: ClientPayload, utilisateur=Depends(exiger_permission("clients", "creer"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(nom)) = LOWER(TRIM(%s))", (values[0],))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un client portant ce nom existe déjà.")
            if values[1]:
                cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s))", (values[1],))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Cette adresse e-mail est déjà utilisée par un autre client.")
            if values[2]:
                telephone_chiffres = "".join(ch for ch in values[2] if ch.isdigit())
                cur.execute("SELECT 1 FROM client WHERE regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s", (telephone_chiffres,))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Ce numéro de téléphone est déjà utilisé par un autre client.")
            cur.execute(
                """
                INSERT INTO client (nom, email, telephone, adresse)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nom, email, telephone, adresse
                """,
                values,
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
            ecrire_evenement(cur, "client", result["id"], "creation", utilisateur, contenu="Client créé manuellement.")
        conn.commit()
        return {"client": result, "message": "Client créé avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@router.patch("/{client_id}")
def modifier_client(client_id: int, payload: ClientPayload, utilisateur=Depends(exiger_permission("clients", "modifier"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom, email, telephone, adresse, archive FROM client WHERE id = %s FOR UPDATE", (client_id,))
            avant = cur.fetchone()
            if not avant:
                raise HTTPException(status_code=404, detail="Client introuvable.")
            if avant[4]:
                raise HTTPException(status_code=409, detail="Client archivé : réactivez-le avant toute modification.")
            cur.execute(
                "SELECT 1 FROM client WHERE LOWER(nom) = LOWER(%s) AND id <> %s",
                (values[0], client_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un autre client porte déjà ce nom.")
            if values[1]:
                cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s)) AND id <> %s", (values[1], client_id))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Cette adresse e-mail est déjà utilisée par un autre client.")
            if values[2]:
                telephone_chiffres = "".join(ch for ch in values[2] if ch.isdigit())
                cur.execute("SELECT 1 FROM client WHERE regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s AND id <> %s", (telephone_chiffres, client_id))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Ce numéro de téléphone est déjà utilisé par un autre client.")
            cur.execute(
                """
                UPDATE client
                SET nom=%s, email=%s, telephone=%s, adresse=%s
                WHERE id=%s
                RETURNING id, nom, email, telephone, adresse
                """,
                (*values, client_id),
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
            changements = regles_prospects.differences(
                dict(zip(("nom", "email", "telephone", "adresse"), avant[:4])),
                dict(zip(("nom", "email", "telephone", "adresse"), values)),
                champs=("nom", "email", "telephone", "adresse"),
            )
            if changements:
                ecrire_evenement(cur, "client", client_id, "modification", utilisateur,
                                 contenu="Champs modifiés : " + ", ".join(changements),
                                 details={"changements": changements})
        conn.commit()
        return {"client": result, "message": "Client modifié avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# Archivage / réactivation et suivi commercial (l'historique n'est jamais supprimé)
# ---------------------------------------------------------------------------
@router.post("/{client_id}/archiver")
def archiver_client(client_id: int, payload: ArchivagePayload,
                    utilisateur=Depends(exiger_permission("clients", "supprimer"))):
    with transaction_entreprise(utilisateur) as cur:
        cur.execute("SELECT archive FROM client WHERE id = %s FOR UPDATE", (client_id,))
        ligne = cur.fetchone()
        if not ligne:
            raise HTTPException(status_code=404, detail="Client introuvable.")
        if ligne[0]:
            raise HTTPException(status_code=409, detail="Ce client est déjà archivé.")
        cur.execute(
            """
            SELECT (SELECT COUNT(*) FROM commande WHERE client_id = %s AND statut IN ('en_cours', 'confirmee')),
                   (SELECT COUNT(*) FROM devis WHERE client_id = %s AND statut IN ('brouillon', 'envoye'))
            """,
            (client_id, client_id),
        )
        commandes, devis = cur.fetchone()
        if commandes or devis:
            raise HTTPException(
                status_code=409,
                detail=f"Archivage impossible : {commandes} commande(s) et {devis} devis en cours. Terminez-les ou annulez-les d'abord.",
            )
        cur.execute(
            "UPDATE client SET archive = TRUE, archive_le = NOW(), archive_motif = %s, archive_par = %s WHERE id = %s",
            (payload.motif, utilisateur.get("id"), client_id),
        )
        ecrire_evenement(cur, "client", client_id, "archivage", utilisateur, contenu=payload.motif)
    return {"message": "Client archivé. Commandes, factures et historique sont conservés."}


@router.post("/{client_id}/reactiver")
def reactiver_client(client_id: int, utilisateur=Depends(exiger_permission("clients", "supprimer"))):
    with transaction_entreprise(utilisateur) as cur:
        cur.execute("SELECT archive FROM client WHERE id = %s FOR UPDATE", (client_id,))
        ligne = cur.fetchone()
        if not ligne:
            raise HTTPException(status_code=404, detail="Client introuvable.")
        if not ligne[0]:
            raise HTTPException(status_code=409, detail="Ce client n'est pas archivé.")
        cur.execute(
            "UPDATE client SET archive = FALSE, archive_le = NULL, archive_motif = NULL, archive_par = NULL WHERE id = %s",
            (client_id,),
        )
        ecrire_evenement(cur, "client", client_id, "reactivation", utilisateur, contenu="Client réactivé.")
    return {"message": "Client réactivé."}


@router.get("/{client_id}/historique")
def historique_client(client_id: int, limite: int = Query(default=200, ge=1, le=500),
                      decalage: int = Query(default=0, ge=0),
                      utilisateur=Depends(exiger_permission("clients", "consulter"))):
    with transaction_entreprise(utilisateur) as cur:
        cur.execute("SELECT 1 FROM client WHERE id = %s", (client_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Client introuvable.")
        return {"historique": lire_historique_client(cur, client_id, limite, decalage)}


@router.post("/{client_id}/suivis")
def ajouter_suivi_client(client_id: int, payload: SuiviPayload,
                         utilisateur=Depends(exiger_permission("clients", "modifier"))):
    from datetime import datetime, timedelta, timezone

    maintenant = datetime.now(timezone.utc)
    date_evenement = payload.date_evenement or maintenant
    if date_evenement > maintenant + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="La date du suivi ne peut pas être dans le futur.")
    with transaction_entreprise(utilisateur) as cur:
        cur.execute("SELECT archive FROM client WHERE id = %s FOR UPDATE", (client_id,))
        ligne = cur.fetchone()
        if not ligne:
            raise HTTPException(status_code=404, detail="Client introuvable.")
        if ligne[0]:
            raise HTTPException(status_code=409, detail="Client archivé : réactivez-le avant d'ajouter un suivi.")
        suivi_id = ecrire_evenement(cur, "client", client_id, payload.type_evenement, utilisateur,
                                    contenu=payload.contenu, date_evenement=date_evenement)
    return {"suivi_id": suivi_id, "message": "Suivi enregistré."}
