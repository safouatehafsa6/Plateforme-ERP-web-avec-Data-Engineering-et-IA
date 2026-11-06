"""Accès base de données du suivi commercial : historique daté et recherche de doublons.

Toutes les fonctions reçoivent un curseur : la transaction reste gérée par l'appelant,
si bien qu'un événement d'historique est enregistré ou annulé avec l'opération qu'il décrit.
"""
import json

from psycopg2.extras import Json

from app.services import prospects as regles

_ACCENTS = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿœæ"
_SANS_ACCENTS = "aaaaaaceeeeiiiinooooouuuuyyoa"
assert len(_ACCENTS) == len(_SANS_ACCENTS)

_CHAMPS_DOUBLON = "id, nom, email, telephone, archive"


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def nom_auteur(cur, utilisateur: dict) -> str:
    cur.execute("SELECT TRIM(COALESCE(prenom, '') || ' ' || COALESCE(nom, '')) FROM utilisateur WHERE id = %s", (utilisateur.get("id"),))
    ligne = cur.fetchone()
    return (ligne[0] if ligne and ligne[0] else utilisateur.get("email") or "Utilisateur")[:200]


def ecrire_evenement(cur, entite_type: str, entite_id: int, type_evenement: str, utilisateur: dict,
                     contenu: str | None = None, details: dict | None = None, date_evenement=None) -> int:
    cur.execute(
        """
        INSERT INTO suivi_commercial (entite_type, entite_id, type_evenement, contenu, details,
                                      date_evenement, auteur_id, auteur_nom)
        VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()), %s, %s)
        RETURNING id
        """,
        (entite_type, entite_id, type_evenement, contenu, Json(details or {}, dumps=lambda o: json.dumps(o, default=str)),
         date_evenement, utilisateur.get("id"), nom_auteur(cur, utilisateur)),
    )
    return cur.fetchone()[0]


def lire_historique_prospect(cur, prospect_id: int, limite: int = 200, decalage: int = 0) -> list[dict]:
    cur.execute(
        """
        SELECT id, entite_type, entite_id, type_evenement, contenu, details,
               date_evenement, enregistre_le, auteur_id, auteur_nom
        FROM suivi_commercial
        WHERE entite_type = 'prospect' AND entite_id = %s
        ORDER BY date_evenement DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (prospect_id, limite, decalage),
    )
    return _dicts(cur)


def lire_historique_client(cur, client_id: int, limite: int = 200, decalage: int = 0) -> list[dict]:
    """Événements du client + historique du prospect dont il est issu (la conversion ne l'efface pas)."""
    cur.execute(
        """
        SELECT id, entite_type, entite_id, type_evenement, contenu, details,
               date_evenement, enregistre_le, auteur_id, auteur_nom
        FROM suivi_commercial
        WHERE (entite_type = 'client' AND entite_id = %(c)s)
           OR (entite_type = 'prospect' AND entite_id IN (SELECT id FROM prospect WHERE client_id = %(c)s))
        ORDER BY date_evenement DESC, id DESC
        LIMIT %(l)s OFFSET %(o)s
        """,
        {"c": client_id, "l": limite, "o": decalage},
    )
    return _dicts(cur)


def _candidats(cur, table: str, entite: str, nom, email, telephone, exclure_id):
    email_n = regles.normaliser_email(email)
    cle = regles.cle_telephone(telephone)
    mot = regles.mot_cle_nom(nom)
    if not (email_n or cle or mot):
        return []
    colonnes = _CHAMPS_DOUBLON + (", statut" if table == "prospect" else "")
    cur.execute(
        f"""
        SELECT {colonnes} FROM {table}
        WHERE (%(email)s::text IS NOT NULL AND LOWER(TRIM(COALESCE(email, ''))) = %(email)s)
           OR (%(cle)s::text IS NOT NULL
               AND right(regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g'), 8) = %(cle)s)
           OR (%(like)s::text IS NOT NULL
               AND translate(lower(nom), %(de)s, %(vers)s) LIKE %(like)s)
        LIMIT 200
        """,
        {"email": email_n, "cle": cle, "like": f"%{mot}%" if mot else None, "de": _ACCENTS, "vers": _SANS_ACCENTS},
    )
    resultats = []
    for ligne in _dicts(cur):
        if exclure_id is not None and ligne["id"] == exclure_id:
            continue
        ligne["entite"] = entite
        evalue = regles.evaluer_candidat(ligne, nom=nom, email=email, telephone=telephone)
        if evalue:
            resultats.append(evalue)
    return resultats


def rechercher_doublons(cur, *, nom=None, email=None, telephone=None,
                        exclure_prospect_id=None, exclure_client_id=None,
                        inclure_prospects=True, inclure_clients=True) -> list[dict]:
    doublons = []
    if inclure_prospects:
        doublons += _candidats(cur, "prospect", "prospect", nom, email, telephone, exclure_prospect_id)
    if inclure_clients:
        doublons += _candidats(cur, "client", "client", nom, email, telephone, exclure_client_id)
    return regles.trier_doublons(doublons)
