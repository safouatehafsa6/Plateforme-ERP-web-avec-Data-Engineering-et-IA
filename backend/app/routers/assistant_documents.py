"""Import / liste / suppression des documents du RAG de l'assistant.

Sécurité :
- authentification Bearer + permission RBAC revérifiée en base (exiger_permission) ;
- la base entreprise vient du JWT signé (jamais d'un paramètre client) ;
- le nom de fichier envoyé n'est jamais utilisé comme chemin MinIO (clé = UUID) ;
- aucune URL publique : l'original n'est pas exposé par l'API.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from psycopg2.extras import execute_values

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission
from app.services import rag_documents as rag
from app.services.rag_embeddings import embed_texts, MODEL_NAME

logger = logging.getLogger("erp.rag")

router = APIRouter(prefix="/api/assistant/documents", tags=["assistant-documents"])

TYPES_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("/upload", status_code=201)
def importer_document(
    fichier: UploadFile = File(...),
    titre: str | None = Form(default=None, max_length=200),
    langue: str = Form(default="fr", pattern="^(fr|en|ar)$"),
    utilisateur: dict = Depends(exiger_permission("documents", "creer")),
):
    nom = rag.nettoyer_nom_fichier(fichier.filename)

    # Lecture bornée : on lit au plus limite+1 octets pour détecter le dépassement
    # sans jamais charger un fichier énorme en mémoire.
    contenu = fichier.file.read(rag.TAILLE_MAX_OCTETS + 1)
    if len(contenu) > rag.TAILLE_MAX_OCTETS:
        raise HTTPException(413, "Fichier trop volumineux (maximum 10 Mo).")

    try:
        type_fichier = rag.valider_fichier(nom, contenu)
        pages = rag.extraire_pages(contenu, type_fichier)
        if not pages:
            raise rag.DocumentInvalide(
                "Aucun texte extractible. S'il s'agit d'un PDF scanné, l'OCR n'est pas encore pris en charge."
            )
        chunks = rag.construire_chunks(pages, nom)
        vecteurs = embed_texts([texte for _, texte in chunks])
    except rag.DocumentInvalide as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        logger.exception("Moteur d'embeddings local indisponible")
        raise HTTPException(503, str(e))

    document_id = str(uuid.uuid4())
    cle = f"{utilisateur.get('entrepriseId', 'x')}/{document_id}.{type_fichier}"
    titre_final = (titre or "").strip() or nom.rsplit(".", 1)[0]

    # 1) original dans MinIO ; 2) métadonnées + chunks dans UNE transaction ;
    # si la base échoue, on retire l'objet MinIO (pas de fichier orphelin).
    try:
        rag.stocker_original(cle, contenu, TYPES_MIME[type_fichier])
    except Exception:
        logger.exception("Stockage MinIO impossible")
        raise HTTPException(503, "Le stockage des documents est momentanément indisponible.")

    pool = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Compatibilité avec les bases entreprise créées avant la migration 016.
            cur.execute("ALTER TABLE assistant_document_chunk ADD COLUMN IF NOT EXISTS embedding JSONB")
            cur.execute("ALTER TABLE assistant_document_chunk ADD COLUMN IF NOT EXISTS embedding_model TEXT")
            cur.execute(
                """INSERT INTO assistant_document
                   (id, titre, nom_fichier, type_fichier, taille_octets, objet_minio, nb_chunks, cree_par)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (document_id, titre_final, nom, type_fichier, len(contenu), cle, len(chunks), utilisateur["id"]),
            )
            execute_values(
                cur,
                """INSERT INTO assistant_document_chunk
                   (document_id, titre, source, module, contenu, langue, embedding, embedding_model) VALUES %s""",
                [
                    (document_id, titre_final, src, "documents", texte, langue, __import__("json").dumps(vecteur), MODEL_NAME)
                    for (src, texte), vecteur in zip(chunks, vecteurs)
                ],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        rag.supprimer_original(cle)
        logger.exception("Enregistrement du document impossible")
        raise HTTPException(500, "L'importation a échoué. Veuillez réessayer.")
    finally:
        pool.putconn(conn)

    return {"id": document_id, "titre": titre_final, "nomFichier": nom, "type": type_fichier, "nbChunks": len(chunks)}


@router.get("")
def lister_documents(utilisateur: dict = Depends(exiger_permission("documents", "consulter"))):
    pool = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, titre, nom_fichier, type_fichier, taille_octets, nb_chunks, cree_le
                   FROM assistant_document ORDER BY cree_le DESC LIMIT 200"""
            )
            lignes = cur.fetchall()
    finally:
        pool.putconn(conn)
    return [
        {"id": l[0], "titre": l[1], "nomFichier": l[2], "type": l[3],
         "tailleOctets": l[4], "nbChunks": l[5], "creeLe": l[6].isoformat()}
        for l in lignes
    ]


@router.delete("/{document_id}", status_code=204)
def supprimer_document(
    document_id: uuid.UUID,
    utilisateur: dict = Depends(exiger_permission("documents", "supprimer")),
):
    pool = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assistant_document WHERE id = %s RETURNING objet_minio", (str(document_id),))
            ligne = cur.fetchone()
            if not ligne:
                conn.rollback()
                raise HTTPException(404, "Document introuvable.")
            cur.execute("DELETE FROM assistant_document_chunk WHERE document_id = %s", (str(document_id),))
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        logger.exception("Suppression du document impossible")
        raise HTTPException(500, "La suppression a échoué.")
    finally:
        pool.putconn(conn)
    rag.supprimer_original(ligne[0])
