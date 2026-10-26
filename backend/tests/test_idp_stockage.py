"""Tests de idp_stockage.

La plupart utilisent un faux pool et un faux MinIO (aucune base, aucun réseau) :
ils vérifient la logique Python (transitions, refus, paramètres, transactions).
Le SQL lui-même n'est exercé que par le test d'intégration, désactivé par défaut :

    docker compose exec -e IDP_TEST_BASE=<nom_base_de_dev> backend \
        python -m unittest tests.test_idp_stockage -v

Il écrit dans la base indiquée puis supprime ses lignes. À réserver à une base
de développement.
"""
import json
import os
import unittest
import uuid

from app.services import idp_stockage as sk

EMPREINTE = "ab" * 32


def ligne(**kw):
    defauts = dict(
        id=7, empreinte_fichier=EMPREINTE, empreinte_metier="cd" * 32,
        nom_fichier="f.pdf", format="pdf", taille_octets=3, cle_stockage="acme/ab/x",
        statut="brouillon", donnees={"numero": "F1", "fournisseur": {"nom": "Atlas"}},
        anomalies=[], avertissements=[], modele="m", ocr_utilise=False,
        depose_par="u1", depose_le=None, traite_par=None, traite_le=None,
        motif_rejet=None,
    )
    defauts.update(kw)
    return tuple(defauts[c] for c in sk.COLONNES)


class FauxCurseur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.conn.journal.append((sql, params))
        erreur = self.conn.erreur_sur
        if erreur and sql.startswith(erreur[0]):
            raise erreur[1]

    def fetchone(self):
        return self.conn.reponses.pop(0)

    def fetchall(self):
        return self.conn.reponses.pop(0)


class FausseConnexion:
    def __init__(self, reponses=()):
        self.reponses = list(reponses)
        self.journal = []
        self.commits = 0
        self.rollbacks = 0
        self.erreur_sur = None

    def cursor(self):
        return FauxCurseur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FauxPool:
    def __init__(self, reponses=()):
        self.conn = FausseConnexion(reponses)
        self.rendues = 0

    def getconn(self):
        return self.conn

    def putconn(self, conn):
        self.rendues += 1

    def requetes(self, debut):
        return [(s, p) for s, p in self.conn.journal if s.startswith(debut)]


class FauxMinio:
    def __init__(self, bucket_existe=True):
        self.bucket_existe = bucket_existe
        self.buckets_crees = []
        self.objets = {}

    def bucket_exists(self, bucket):
        return self.bucket_existe

    def make_bucket(self, bucket):
        self.buckets_crees.append(bucket)

    def put_object(self, bucket, cle, flux, longueur, content_type=None):
        data = flux.read()
        assert len(data) == longueur
        self.objets[(bucket, cle)] = (data, content_type)

    def get_object(self, bucket, cle):
        data = self.objets[(bucket, cle)][0]

        class Reponse:
            def read(self):
                return data

            def close(self):
                pass

            def release_conn(self):
                pass

        return Reponse()


RESULTAT = {
    "empreinte_fichier": EMPREINTE,
    "empreinte_metier": "cd" * 32,
    "format": "pdf",
    "ocr_utilise": False,
    "modele": "gpt-test",
    "donnees": {"numero": "F1", "fournisseur": {"nom": "Atlas"}},
    "anomalies": [],
    "avertissements": [],
}


class Base(unittest.TestCase):
    def setUp(self):
        sk._schemas_prets.clear()


class TestSchema(Base):
    def test_cree_une_seule_fois_avec_verrou(self):
        pool = FauxPool()
        sk.initialiser_schema(pool)
        sk.initialiser_schema(pool)
        self.assertEqual(len(pool.requetes("SELECT pg_advisory_xact_lock")), 1)
        ddl = pool.requetes("CREATE TABLE IF NOT EXISTS idp_documents")
        self.assertEqual(len(ddl), 1)
        self.assertIn("idp_evenements", ddl[0][0])
        self.assertIn("ux_idp_documents_valide_metier", ddl[0][0])
        self.assertEqual(pool.conn.commits, 1)


class TestFichier(Base):
    def test_cle_et_prefixe(self):
        self.assertEqual(sk.cle_stockage("Acme_12", EMPREINTE), f"acme_12/ab/{EMPREINTE}")
        for mauvais in ("", "../x", "a/b", "a b", "é"):
            with self.assertRaises(ValueError):
                sk.cle_stockage(mauvais, EMPREINTE)
        with self.assertRaises(ValueError):
            sk.cle_stockage("acme", "pas-une-empreinte")

    def test_depot_cree_le_bucket_et_stocke(self):
        minio = FauxMinio(bucket_existe=False)
        cle = sk.deposer_fichier(b"abc", "acme", EMPREINTE, client=minio)
        self.assertEqual(minio.buckets_crees, [sk.BUCKET_DOCUMENTS])
        self.assertEqual(minio.objets[(sk.BUCKET_DOCUMENTS, cle)],
                         (b"abc", "application/octet-stream"))
        self.assertEqual(sk.lire_fichier(cle, client=minio), b"abc")

    def test_minio_en_panne(self):
        class Casse(FauxMinio):
            def put_object(self, *a, **k):
                raise OSError("secret-interne")

        with self.assertRaises(sk.StockageFichierIndisponible) as ctx:
            sk.deposer_fichier(b"abc", "acme", EMPREINTE, client=Casse())
        self.assertNotIn("secret-interne", str(ctx.exception))

    def test_nom_de_fichier_nettoye(self):
        self.assertEqual(sk._nom_propre("C:\\Users\\hp\\facture.pdf"), "facture.pdf")
        self.assertEqual(sk._nom_propre("../../etc/passwd\x00"), "passwd")
        self.assertEqual(len(sk._nom_propre("x" * 500)), sk.LONGUEUR_MAX_NOM)
        self.assertIsNone(sk._nom_propre(""))


class TestDepot(Base):
    def test_depot_nominal(self):
        pool = FauxPool([[], (42,)])
        minio = FauxMinio()
        res = sk.enregistrer_depot(pool, RESULTAT, b"abc", "dir/facture.pdf",
                                   prefixe="acme", depose_par="u1", client_minio=minio)
        self.assertEqual(res, {"id": 42, "statut": "brouillon", "doublons": []})
        self.assertIn((sk.BUCKET_DOCUMENTS, f"acme/ab/{EMPREINTE}"), minio.objets)
        sql, params = pool.requetes("INSERT INTO idp_documents")[0]
        self.assertEqual(params[0], EMPREINTE)
        self.assertEqual(params[2], "facture.pdf")
        self.assertEqual(params[4], 3)
        self.assertEqual(json.loads(params[6])["numero"], "F1")
        self.assertEqual(params[-1], "u1")
        evt = pool.requetes("INSERT INTO idp_evenements")[0][1]
        self.assertEqual(evt[:3], (42, "depot", "u1"))
        self.assertEqual(pool.conn.rollbacks, 0)

    def test_doublons_signales_sans_bloquer(self):
        pool = FauxPool([[(3, "brouillon", True), (5, "valide", False)], (9,)])
        res = sk.enregistrer_depot(pool, RESULTAT, b"abc", "f.pdf",
                                   prefixe="acme", client_minio=FauxMinio())
        self.assertEqual(res["id"], 9)
        self.assertEqual(res["doublons"], [
            {"id": 3, "statut": "brouillon", "raison": "fichier_identique"},
            {"id": 5, "statut": "valide", "raison": "meme_document"},
        ])

    def test_echec_base_annule_la_transaction(self):
        pool = FauxPool([[]])
        pool.conn.erreur_sur = ("INSERT INTO idp_documents", RuntimeError("base HS"))
        with self.assertRaises(RuntimeError):
            sk.enregistrer_depot(pool, RESULTAT, b"abc", "f.pdf",
                                 prefixe="acme", client_minio=FauxMinio())
        self.assertEqual(pool.conn.rollbacks, 1)
        self.assertEqual(pool.rendues, 2)    # schéma + dépôt : connexions toujours rendues

    def test_prefixe_invalide_refuse_avant_tout_acces(self):
        pool = FauxPool()
        with self.assertRaises(ValueError):
            sk.enregistrer_depot(pool, RESULTAT, b"abc", "f.pdf",
                                 prefixe="../autre", client_minio=FauxMinio())
        self.assertEqual(pool.requetes("INSERT"), [])


class TestValidation(Base):
    def test_validation_ok(self):
        pool = FauxPool([ligne(), None])
        self.assertEqual(sk.valider(pool, 7, "admin"), {"id": 7, "statut": "valide"})
        sql, params = pool.requetes("UPDATE idp_documents SET statut = 'valide'")[0]
        self.assertEqual(params, ("admin", 7))
        self.assertEqual(pool.requetes("INSERT INTO idp_evenements")[0][1][:3],
                         (7, "validation", "admin"))

    def test_introuvable(self):
        with self.assertRaises(sk.DocumentIntrouvable):
            sk.valider(FauxPool([None]), 7, "admin")

    def test_deja_traite(self):
        for statut in ("valide", "rejete"):
            with self.assertRaises(sk.TransitionInterdite):
                sk.valider(FauxPool([ligne(statut=statut)]), 7, "admin")

    def test_erreurs_bloquantes(self):
        anomalies = [{"code": "x", "gravite": "avertissement"},
                     {"code": "ttc", "gravite": "erreur"}]
        pool = FauxPool([ligne(anomalies=anomalies)])
        with self.assertRaises(sk.ValidationBloquee):
            sk.valider(pool, 7, "admin")
        self.assertEqual(pool.requetes("UPDATE"), [])
        self.assertEqual(pool.conn.rollbacks, 1)

    def test_avertissements_seuls_n_empechent_pas(self):
        pool = FauxPool([ligne(anomalies=[{"code": "ice", "gravite": "avertissement"}]), None])
        self.assertEqual(sk.valider(pool, 7, "admin")["statut"], "valide")

    def test_doublon_deja_valide(self):
        pool = FauxPool([ligne(), (3,)])
        with self.assertRaises(sk.ValidationBloquee) as ctx:
            sk.valider(pool, 7, "admin")
        self.assertIn("3", str(ctx.exception))
        self.assertEqual(pool.requetes("UPDATE"), [])

    def test_validations_simultanees(self):
        class Unicite(Exception):
            pgcode = "23505"

        pool = FauxPool([ligne(), None])
        pool.conn.erreur_sur = ("UPDATE idp_documents", Unicite())
        with self.assertRaises(sk.ValidationBloquee):
            sk.valider(pool, 7, "admin")
        self.assertEqual(pool.conn.rollbacks, 1)

    def test_autre_erreur_sql_remontee_telle_quelle(self):
        pool = FauxPool([ligne(), None])
        pool.conn.erreur_sur = ("UPDATE idp_documents", RuntimeError("autre"))
        with self.assertRaises(RuntimeError):
            sk.valider(pool, 7, "admin")


class TestRejet(Base):
    def test_motif_obligatoire(self):
        for motif in ("", "   ", None):
            with self.assertRaises(ValueError):
                sk.rejeter(FauxPool(), 7, motif, "admin")

    def test_rejet_ok_et_motif_borne(self):
        pool = FauxPool([ligne()])
        sk.rejeter(pool, 7, "x" * 5000, "admin")
        params = pool.requetes("UPDATE idp_documents SET statut = 'rejete'")[0][1]
        self.assertEqual(len(params[1]), sk.LONGUEUR_MAX_MOTIF)

    def test_rejet_d_un_document_valide_interdit(self):
        with self.assertRaises(sk.TransitionInterdite):
            sk.rejeter(FauxPool([ligne(statut="valide")]), 7, "erreur", "admin")


class TestCorrection(Base):
    def test_champ_non_modifiable(self):
        for corr in ({"statut": "valide"}, {"id": 1}, {}):
            with self.assertRaises(ValueError):
                sk.corriger(FauxPool(), 7, corr, "admin")

    def test_correction_refait_les_controles(self):
        pool = FauxPool([ligne(anomalies=[{"gravite": "erreur", "code": "numero_manquant"}],
                               donnees={"numero": None, "fournisseur": {"nom": "Atlas", "ice": "1"}})])
        res = sk.corriger(pool, 7, {"numero": "F-9", "fournisseur": {"nom": "Atlas SARL"}}, "admin")
        self.assertEqual(res["donnees"]["numero"], "F-9")
        # le fournisseur est fusionné, pas écrasé
        self.assertEqual(res["donnees"]["fournisseur"], {"nom": "Atlas SARL", "ice": "1"})
        params = pool.requetes("UPDATE idp_documents SET donnees")[0][1]
        self.assertEqual(json.loads(params[0])["numero"], "F-9")
        self.assertEqual(params[3], 7)
        self.assertEqual(pool.requetes("INSERT INTO idp_evenements")[0][1][1], "correction")

    def test_correction_refusee_si_deja_valide(self):
        with self.assertRaises(sk.TransitionInterdite):
            sk.corriger(FauxPool([ligne(statut="valide")]), 7, {"numero": "X"}, "admin")


class TestLecture(Base):
    def test_lister_valide_ses_parametres(self):
        with self.assertRaises(ValueError):
            sk.lister(FauxPool(), statut="n'importe quoi")
        pool = FauxPool([[]])
        sk.lister(pool, statut="brouillon", limite=10_000, decalage=-5)
        params = pool.requetes("SELECT id, nom_fichier")[0][1]
        self.assertEqual(params, ("brouillon", "brouillon", 200, 0))

    def test_obtenir_avec_historique(self):
        pool = FauxPool([ligne(), [("depot", "u1", {"nb_anomalies": 0}, None)]])
        doc = sk.obtenir(pool, 7)
        self.assertEqual(doc["id"], 7)
        self.assertEqual(doc["evenements"][0]["evenement"], "depot")

    def test_obtenir_introuvable(self):
        with self.assertRaises(sk.DocumentIntrouvable):
            sk.obtenir(FauxPool([None]), 7)


# --------------------------------------------------------------------------
# Intégration réelle (désactivée sans IDP_TEST_BASE)
# --------------------------------------------------------------------------

@unittest.skipUnless(os.environ.get("IDP_TEST_BASE"),
                     "définir IDP_TEST_BASE (base de développement) pour activer")
class TestIntegrationBase(unittest.TestCase):
    def setUp(self):
        from app.db import get_pool_entreprise
        self.pool = get_pool_entreprise(os.environ["IDP_TEST_BASE"])
        self.ids = []
        self.numero = "IT-" + uuid.uuid4().hex[:8]

    def tearDown(self):
        if self.ids:
            with sk._transaction(self.pool) as cur:
                cur.execute("DELETE FROM idp_documents WHERE id = ANY(%s)", (self.ids,))

    def _deposer(self):
        from app.services.idp_controles import empreinte_document
        donnees = {
            "type_document": "facture", "numero": self.numero, "date": "2026-03-15",
            "date_echeance": "2026-04-14", "devise": "MAD",
            "fournisseur": {"nom": "Fournisseur de test IDP", "ice": "001234567000089"},
            "lignes": [{"designation": "Ramette", "quantite": "10", "prix_unitaire": "100.00",
                        "remise": None, "total": "1000.00"}],
            "total_ht": "1000.00", "total_tva": "200.00", "total_ttc": "1200.00",
            "taux_tva": "20",
        }
        empreinte = uuid.uuid4().hex * 2
        resultat = {
            "empreinte_fichier": empreinte, "empreinte_metier": empreinte_document(donnees),
            "format": "txt", "ocr_utilise": False, "modele": "test", "donnees": donnees,
            "anomalies": [{"code": "bidon", "gravite": "erreur", "champ": "x", "message": "m"}],
            "avertissements": [],
        }
        res = sk.enregistrer_depot(self.pool, resultat, b"test", "t.txt",
                                   prefixe="test-idp", depose_par="test",
                                   client_minio=FauxMinio())
        self.ids.append(res["id"])
        return res

    def test_cycle_complet(self):
        premier = self._deposer()
        with self.assertRaises(sk.ValidationBloquee):         # erreur bloquante simulée
            sk.valider(self.pool, premier["id"], "test")
        sk.corriger(self.pool, premier["id"], {"devise": "MAD"}, "test")   # refait les contrôles
        sk.valider(self.pool, premier["id"], "test")

        second = self._deposer()
        self.assertIn(premier["id"], [d["id"] for d in second["doublons"]])
        sk.corriger(self.pool, second["id"], {"devise": "MAD"}, "test")
        with self.assertRaises(sk.ValidationBloquee):         # même document déjà validé
            sk.valider(self.pool, second["id"], "test")
        sk.rejeter(self.pool, second["id"], "doublon", "test")

        doc = sk.obtenir(self.pool, second["id"])
        self.assertEqual(doc["statut"], "rejete")
        self.assertEqual([e["evenement"] for e in doc["evenements"]],
                         ["depot", "correction", "rejet"])


if __name__ == "__main__":
    unittest.main()
