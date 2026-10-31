"""IDP, étape 3 : stockage des documents et historique.

- Le fichier d'origine va dans MinIO (bucket "documents"), adressé par son
  empreinte : le même fichier déposé deux fois n'occupe qu'un objet. Chaque
  entreprise a son propre préfixe (son nom de base).
- Les champs extraits, les anomalies et le statut vont dans la base de
  l'entreprise : table idp_documents, plus idp_evenements pour l'historique
  (dépôt, correction, validation, rejet).
- Les tables sont créées à la demande (CREATE TABLE IF NOT EXISTS), comme les
  colonnes du RAG : aucune migration à lancer, les entreprises existantes sont
  couvertes.

Statuts : brouillon -> valide | rejete. Un document validé ou rejeté ne change
plus. Le dépôt n'est jamais bloqué par un doublon : il est signalé, et c'est la
validation qui refuse un second document identique (index unique en base).

Dépôt : l'upload MinIO précède l'insertion en base. Si la base échoue, il reste
un objet orphelin, sans conséquence (même empreinte = même contenu).
"""
from __future__ import annotations

import io
import json
import os
import re
from contextlib import contextmanager

from app.services.idp_controles import empreinte_document, verifier_document

BUCKET_DOCUMENTS = "documents"
STATUTS = ("brouillon", "valide", "rejete")
CHAMPS_CORRIGEABLES = (
    "type_document", "numero", "date", "date_echeance", "devise",
    "fournisseur", "lignes", "total_ht", "total_tva", "total_ttc", "taux_tva",
)
LONGUEUR_MAX_MOTIF = 1000
LONGUEUR_MAX_NOM = 255

COLONNES = (
    "id", "empreinte_fichier", "empreinte_metier", "nom_fichier", "format",
    "taille_octets", "cle_stockage", "statut", "donnees", "anomalies",
    "avertissements", "modele", "ocr_utilise", "depose_par", "depose_le",
    "traite_par", "traite_le", "motif_rejet",
)
_SELECT_LIGNE = "SELECT " + ", ".join(COLONNES) + " FROM idp_documents"

_DDL = """
CREATE TABLE IF NOT EXISTS idp_documents (
    id                SERIAL PRIMARY KEY,
    empreinte_fichier TEXT NOT NULL,
    empreinte_metier  TEXT,
    nom_fichier       TEXT,
    format            TEXT,
    taille_octets     BIGINT,
    cle_stockage      TEXT NOT NULL,
    statut            TEXT NOT NULL DEFAULT 'brouillon'
                      CHECK (statut IN ('brouillon', 'valide', 'rejete')),
    donnees           JSONB NOT NULL DEFAULT '{}'::jsonb,
    anomalies         JSONB NOT NULL DEFAULT '[]'::jsonb,
    avertissements    JSONB NOT NULL DEFAULT '[]'::jsonb,
    modele            TEXT,
    ocr_utilise       BOOLEAN NOT NULL DEFAULT FALSE,
    depose_par        TEXT,
    depose_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    traite_par        TEXT,
    traite_le         TIMESTAMPTZ,
    motif_rejet       TEXT
);
CREATE INDEX IF NOT EXISTS idx_idp_documents_fichier ON idp_documents (empreinte_fichier);
CREATE INDEX IF NOT EXISTS idx_idp_documents_metier ON idp_documents (empreinte_metier);
CREATE INDEX IF NOT EXISTS idx_idp_documents_statut ON idp_documents (statut, depose_le DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_idp_documents_valide_metier
    ON idp_documents (empreinte_metier)
    WHERE statut = 'valide' AND empreinte_metier IS NOT NULL;
CREATE TABLE IF NOT EXISTS idp_evenements (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES idp_documents (id) ON DELETE CASCADE,
    evenement   TEXT NOT NULL,
    acteur      TEXT,
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_idp_evenements_document ON idp_evenements (document_id, id);
"""

# Pools déjà initialisés (un pool = une base entreprise, réutilisé).
_schemas_prets: set[int] = set()


class StockageErreur(Exception):
    """Base des erreurs métier de ce module."""


class DocumentIntrouvable(StockageErreur):
    pass


class TransitionInterdite(StockageErreur):
    """Le document n'est plus au statut brouillon."""


class ValidationBloquee(StockageErreur):
    """Erreurs bloquantes ou doublon déjà validé."""


class StockageFichierIndisponible(StockageErreur):
    """MinIO injoignable ou mal configuré."""


# --------------------------------------------------------------------------
# Base de données
# --------------------------------------------------------------------------

@contextmanager
def _transaction(pool):
    """Un curseur dans une transaction : commit à la sortie, rollback sur erreur."""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def initialiser_schema(pool) -> None:
    if id(pool) in _schemas_prets:
        return
    with _transaction(pool) as cur:
        # Verrou : deux requêtes simultanées ne créent pas les tables en même temps.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('idp_schema'))")
        cur.execute(_DDL)
    _schemas_prets.add(id(pool))


def _json(valeur) -> str:
    return json.dumps(valeur, ensure_ascii=False, default=str)


def _vers_dict(ligne) -> dict:
    document = dict(zip(COLONNES, ligne))
    for cle in ("depose_le", "traite_le"):
        if document.get(cle) is not None and hasattr(document[cle], "isoformat"):
            document[cle] = document[cle].isoformat()
    return document


def _evenement(cur, document_id: int, evenement: str, acteur, detail: dict | None = None):
    cur.execute(
        "INSERT INTO idp_evenements (document_id, evenement, acteur, detail) "
        "VALUES (%s, %s, %s, %s::jsonb)",
        (document_id, evenement, acteur, _json(detail or {})),
    )


def _verrouiller(cur, document_id: int) -> dict:
    cur.execute(_SELECT_LIGNE + " WHERE id = %s FOR UPDATE", (document_id,))
    ligne = cur.fetchone()
    if ligne is None:
        raise DocumentIntrouvable(f"Document {document_id} introuvable.")
    return _vers_dict(ligne)


def _exiger_brouillon(document: dict) -> None:
    if document["statut"] != "brouillon":
        raise TransitionInterdite(
            f"Le document est déjà {document['statut']} : il ne peut plus être modifié."
        )


def _a_des_erreurs(anomalies) -> bool:
    return any(isinstance(a, dict) and a.get("gravite") == "erreur" for a in anomalies or [])


def _est_violation_unicite(exc: Exception) -> bool:
    return getattr(exc, "pgcode", None) == "23505"


# --------------------------------------------------------------------------
# MinIO
# --------------------------------------------------------------------------

def _client_minio():
    from minio import Minio   # import tardif : module utilisable sans MinIO installé

    try:
        return Minio(
            os.environ.get("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ["MINIO_ROOT_USER"],
            secret_key=os.environ["MINIO_ROOT_PASSWORD"],
            secure=False,
        )
    except KeyError as exc:
        raise StockageFichierIndisponible("Configuration MinIO incomplète.") from exc


def _prefixe_valide(prefixe: str) -> str:
    prefixe = (prefixe or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", prefixe):
        raise ValueError("Préfixe de stockage invalide.")
    return prefixe


def cle_stockage(prefixe: str, empreinte: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", empreinte or ""):
        raise ValueError("Empreinte de fichier invalide.")
    return f"{_prefixe_valide(prefixe)}/{empreinte[:2]}/{empreinte}"


def deposer_fichier(contenu: bytes, prefixe: str, empreinte: str, *, client=None) -> str:
    cle = cle_stockage(prefixe, empreinte)
    try:
        client = client or _client_minio()
        if not client.bucket_exists(BUCKET_DOCUMENTS):
            client.make_bucket(BUCKET_DOCUMENTS)
        client.put_object(
            BUCKET_DOCUMENTS, cle, io.BytesIO(contenu), len(contenu),
            content_type="application/octet-stream",
        )
    except StockageErreur:
        raise
    except Exception as exc:
        raise StockageFichierIndisponible(
            f"Stockage du fichier impossible ({type(exc).__name__})."
        ) from exc
    return cle


def lire_fichier(cle: str, *, client=None) -> bytes:
    try:
        client = client or _client_minio()
        reponse = client.get_object(BUCKET_DOCUMENTS, cle)
        try:
            return reponse.read()
        finally:
            reponse.close()
            reponse.release_conn()
    except StockageErreur:
        raise
    except Exception as exc:
        raise StockageFichierIndisponible(
            f"Lecture du fichier impossible ({type(exc).__name__})."
        ) from exc


def _nom_propre(nom: str | None) -> str | None:
    if not nom:
        return None
    nom = os.path.basename(str(nom).replace("\\", "/"))
    nom = re.sub(r"[\x00-\x1f\x7f]", "", nom).strip()
    return nom[:LONGUEUR_MAX_NOM] or None


# --------------------------------------------------------------------------
# Opérations
# --------------------------------------------------------------------------

def trouver_doublons(cur, empreinte_fichier: str, empreinte_metier: str | None) -> list[dict]:
    """Documents non rejetés qui ressemblent à celui-ci."""
    cur.execute(
        "SELECT id, statut, empreinte_fichier = %s FROM idp_documents "
        "WHERE statut <> 'rejete' AND (empreinte_fichier = %s "
        "OR (%s IS NOT NULL AND empreinte_metier = %s)) ORDER BY id",
        (empreinte_fichier, empreinte_fichier, empreinte_metier, empreinte_metier),
    )
    return [
        {"id": i, "statut": s,
         "raison": "fichier_identique" if meme_fichier else "meme_document"}
        for i, s, meme_fichier in cur.fetchall()
    ]


def enregistrer_depot(
    pool, resultat: dict, contenu: bytes, nom_fichier: str = "", *,
    prefixe: str, depose_par: str | None = None, client_minio=None,
) -> dict:
    """Range le fichier et le résultat de `traiter_document` ; crée un brouillon.
    Retourne {"id", "statut", "doublons": [...]}."""
    initialiser_schema(pool)
    cle = deposer_fichier(contenu, prefixe, resultat["empreinte_fichier"], client=client_minio)
    with _transaction(pool) as cur:
        doublons = trouver_doublons(
            cur, resultat["empreinte_fichier"], resultat.get("empreinte_metier"))
        cur.execute(
            "INSERT INTO idp_documents (empreinte_fichier, empreinte_metier, nom_fichier, "
            "format, taille_octets, cle_stockage, donnees, anomalies, avertissements, "
            "modele, ocr_utilise, depose_par) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s) "
            "RETURNING id",
            (
                resultat["empreinte_fichier"], resultat.get("empreinte_metier"),
                _nom_propre(nom_fichier), resultat.get("format"), len(contenu), cle,
                _json(resultat.get("donnees") or {}),
                _json(resultat.get("anomalies") or []),
                _json(resultat.get("avertissements") or []),
                resultat.get("modele"), bool(resultat.get("ocr_utilise")), depose_par,
            ),
        )
        document_id = cur.fetchone()[0]
        _evenement(cur, document_id, "depot", depose_par, {
            "nb_anomalies": len(resultat.get("anomalies") or []),
            "doublons": [d["id"] for d in doublons],
        })
    return {"id": document_id, "statut": "brouillon", "doublons": doublons}


def lister(pool, *, statut: str | None = None, limite: int = 50, decalage: int = 0) -> list[dict]:
    if statut is not None and statut not in STATUTS:
        raise ValueError("Statut inconnu.")
    limite = max(1, min(int(limite), 200))
    decalage = max(0, int(decalage))
    initialiser_schema(pool)
    with _transaction(pool) as cur:
        cur.execute(
            "SELECT id, nom_fichier, format, statut, depose_par, depose_le, "
            "donnees->>'numero', donnees->'fournisseur'->>'nom', donnees->>'total_ttc', "
            "(SELECT count(*) FROM jsonb_array_elements(anomalies) a "
            " WHERE a->>'gravite' = 'erreur') "
            "FROM idp_documents WHERE (%s::text IS NULL OR statut = %s) "
            "ORDER BY depose_le DESC, id DESC LIMIT %s OFFSET %s",
            (statut, statut, limite, decalage),
        )
        lignes = cur.fetchall()
    cles = ("id", "nom_fichier", "format", "statut", "depose_par", "depose_le",
            "numero", "fournisseur", "total_ttc", "nb_erreurs")
    resultats = []
    for ligne in lignes:
        element = dict(zip(cles, ligne))
        if hasattr(element["depose_le"], "isoformat"):
            element["depose_le"] = element["depose_le"].isoformat()
        resultats.append(element)
    return resultats


def obtenir(pool, document_id: int) -> dict:
    initialiser_schema(pool)
    with _transaction(pool) as cur:
        cur.execute(_SELECT_LIGNE + " WHERE id = %s", (document_id,))
        ligne = cur.fetchone()
        if ligne is None:
            raise DocumentIntrouvable(f"Document {document_id} introuvable.")
        document = _vers_dict(ligne)
        cur.execute(
            "SELECT evenement, acteur, detail, cree_le FROM idp_evenements "
            "WHERE document_id = %s ORDER BY id", (document_id,))
        document["evenements"] = [
            {"evenement": e, "acteur": a, "detail": d,
             "date": c.isoformat() if hasattr(c, "isoformat") else c}
            for e, a, d, c in cur.fetchall()
        ]
    return document


def corriger(pool, document_id: int, corrections: dict, acteur: str | None = None) -> dict:
    """Corrige des champs d'un brouillon, puis refait les contrôles."""
    inconnus = sorted(set(corrections) - set(CHAMPS_CORRIGEABLES))
    if inconnus or not corrections:
        raise ValueError("Champs non modifiables : " + ", ".join(inconnus or ["(aucun champ)"]))
    initialiser_schema(pool)
    with _transaction(pool) as cur:
        document = _verrouiller(cur, document_id)
        _exiger_brouillon(document)
        donnees = dict(document["donnees"] or {})
        for champ, valeur in corrections.items():
            if champ == "fournisseur" and isinstance(valeur, dict):
                donnees["fournisseur"] = {**(donnees.get("fournisseur") or {}), **valeur}
            else:
                donnees[champ] = valeur
        anomalies = [a.vers_dict() for a in verifier_document(donnees)]
        empreinte = empreinte_document(donnees)
        cur.execute(
            "UPDATE idp_documents SET donnees = %s::jsonb, anomalies = %s::jsonb, "
            "empreinte_metier = %s WHERE id = %s",
            (_json(donnees), _json(anomalies), empreinte, document_id),
        )
        _evenement(cur, document_id, "correction", acteur, {"champs": sorted(corrections)})
    return {"id": document_id, "statut": "brouillon", "donnees": donnees, "anomalies": anomalies}


def valider(pool, document_id: int, acteur: str | None = None) -> dict:
    initialiser_schema(pool)
    with _transaction(pool) as cur:
        document = _verrouiller(cur, document_id)
        _exiger_brouillon(document)
        if _a_des_erreurs(document["anomalies"]):
            raise ValidationBloquee(
                "Des erreurs bloquantes subsistent : corrigez le document avant de le valider.")
        if document["empreinte_metier"]:
            cur.execute(
                "SELECT id FROM idp_documents WHERE statut = 'valide' "
                "AND empreinte_metier = %s AND id <> %s LIMIT 1",
                (document["empreinte_metier"], document_id),
            )
            existant = cur.fetchone()
            if existant:
                raise ValidationBloquee(
                    f"Ce document existe déjà (document {existant[0]} validé).")
        try:
            cur.execute(
                "UPDATE idp_documents SET statut = 'valide', traite_par = %s, "
                "traite_le = now() WHERE id = %s", (acteur, document_id))
        except Exception as exc:
            if _est_violation_unicite(exc):   # deux validations simultanées
                raise ValidationBloquee("Ce document vient d'être validé par ailleurs.") from exc
            raise
        _evenement(cur, document_id, "validation", acteur)
    return {"id": document_id, "statut": "valide"}


def rejeter(pool, document_id: int, motif: str, acteur: str | None = None) -> dict:
    motif = (motif or "").strip()
    if not motif:
        raise ValueError("Un motif de rejet est obligatoire.")
    motif = motif[:LONGUEUR_MAX_MOTIF]
    initialiser_schema(pool)
    with _transaction(pool) as cur:
        document = _verrouiller(cur, document_id)
        _exiger_brouillon(document)
        cur.execute(
            "UPDATE idp_documents SET statut = 'rejete', traite_par = %s, "
            "traite_le = now(), motif_rejet = %s WHERE id = %s",
            (acteur, motif, document_id))
        _evenement(cur, document_id, "rejet", acteur, {"motif": motif})
    return {"id": document_id, "statut": "rejete"}
