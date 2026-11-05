"""Tests des routes IDP : aucun réseau, aucune base, modèle et stockage simulés.

Deux familles :
- appels directs des fonctions de route (logique, codes d'erreur, paramètres) ;
- TestHttp : requêtes réelles via TestClient (câblage : chemins, champs de
  formulaire, validation, authentification).

Lancement (dans le conteneur) :
    python -m unittest tests.test_idp_routes -v
"""
import io
import logging
import unittest
from unittest import mock

from pydantic import ValidationError

from app.routers import idp
from app.security.auth_dependency import exiger_role_admin
from app.services import idp_stockage as stockage
from app.services import idp_structuration as structuration
from app.services.idp_extraction import DocumentIllisible, FichierTropVolumineux, FormatNonSupporte

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:          # pragma: no cover
    TestClient = None

def setUpModule():
    # Les routes journalisent les erreurs simulées par les tests : on coupe ce bruit.
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


USER = {"id": 12, "type": "interne", "nomBase": "compte_test_abc123", "entrepriseId": 3}

RESULTAT = {
    "empreinte_fichier": "ab" * 32, "empreinte_metier": "cd" * 32, "format": "pdf",
    "pages": 1, "ocr_utilise": False, "modele": "m",
    "donnees": {"numero": "F1"}, "anomalies": [], "resume": {"erreurs": 0},
    "avertissements": [],
}


class FauxFichier:
    def __init__(self, contenu=b"abc", nom="facture.pdf"):
        self.file = io.BytesIO(contenu)
        self.filename = nom


def code(exc_info):
    return exc_info.exception.status_code


class TestAcces(unittest.TestCase):
    def test_utilisateur_externe_refuse(self):
        for mauvais in ({"type": "externe", "nomBase": "x"}, {"type": "interne"}, {}):
            with self.assertRaises(idp.HTTPException) as ctx:
                idp.utilisateur_idp(utilisateur=mauvais)
            self.assertEqual(code(ctx), 403)

    def test_utilisateur_interne_accepte(self):
        self.assertEqual(idp.utilisateur_idp(utilisateur=USER), USER)


@mock.patch.object(idp, "get_pool_entreprise", return_value="POOL")
class TestDepot(unittest.TestCase):
    def test_depot_nominal(self, pool):
        with mock.patch.object(structuration, "traiter_document", return_value=RESULTAT) as trait, \
             mock.patch.object(stockage, "enregistrer_depot",
                               return_value={"id": 5, "statut": "brouillon", "doublons": []}) as depot:
            rep = idp.deposer_document(fichier=FauxFichier(), utilisateur=USER)
        trait.assert_called_once_with(b"abc", "facture.pdf")
        pool.assert_called_once_with("compte_test_abc123")
        args, kwargs = depot.call_args
        self.assertEqual(args[0], "POOL")
        self.assertEqual(kwargs["prefixe"], "compte_test_abc123")
        self.assertEqual(kwargs["depose_par"], "12")
        self.assertEqual(rep["id"], 5)
        self.assertEqual(rep["doublons"], [])
        self.assertEqual(rep["donnees"], {"numero": "F1"})
        self.assertNotIn("cle_stockage", rep)

    def test_fichier_trop_gros_refuse_sans_analyse(self, pool):
        with mock.patch.object(idp, "TAILLE_MAX_OCTETS", 10), \
             mock.patch.object(structuration, "traiter_document") as trait:
            with self.assertRaises(idp.HTTPException) as ctx:
                idp.deposer_document(fichier=FauxFichier(b"x" * 11), utilisateur=USER)
        self.assertEqual(code(ctx), 413)
        trait.assert_not_called()

    def test_fichier_vide(self, pool):
        with self.assertRaises(idp.HTTPException) as ctx:
            idp.deposer_document(fichier=FauxFichier(b""), utilisateur=USER)
        self.assertEqual(code(ctx), 422)

    def test_erreurs_d_analyse_traduites(self, pool):
        cas = [
            (FichierTropVolumineux("gros"), 413),
            (FormatNonSupporte("format"), 415),
            (DocumentIllisible("illisible"), 422),
            (structuration.StructurationIndisponible("pas de clé"), 503),
            (structuration.StructurationEchouee("modèle"), 502),
        ]
        for erreur, attendu in cas:
            with self.subTest(erreur=type(erreur).__name__):
                with mock.patch.object(structuration, "traiter_document", side_effect=erreur), \
                     mock.patch.object(stockage, "enregistrer_depot") as depot:
                    with self.assertRaises(idp.HTTPException) as ctx:
                        idp.deposer_document(fichier=FauxFichier(), utilisateur=USER)
                self.assertEqual(code(ctx), attendu)
                depot.assert_not_called()

    def test_stockage_indisponible(self, pool):
        with mock.patch.object(structuration, "traiter_document", return_value=RESULTAT), \
             mock.patch.object(stockage, "enregistrer_depot",
                               side_effect=stockage.StockageFichierIndisponible("MinIO secret-interne")):
            with self.assertRaises(idp.HTTPException) as ctx:
                idp.deposer_document(fichier=FauxFichier(), utilisateur=USER)
        self.assertEqual(code(ctx), 503)
        self.assertNotIn("secret-interne", ctx.exception.detail)


@mock.patch.object(idp, "get_pool_entreprise", return_value="POOL")
class TestLecture(unittest.TestCase):
    def test_liste(self, pool):
        with mock.patch.object(stockage, "lister", return_value=[{"id": 1}]) as lister:
            rep = idp.lister_documents(statut="brouillon", limite=20, decalage=40, utilisateur=USER)
        lister.assert_called_once_with("POOL", statut="brouillon", limite=20, decalage=40)
        self.assertEqual(rep, [{"id": 1}])

    def test_detail_masque_la_cle_de_stockage(self, pool):
        document = {"id": 4, "cle_stockage": "acme/ab/xxx", "statut": "brouillon"}
        with mock.patch.object(stockage, "obtenir", return_value=document):
            rep = idp.detail_document(4, utilisateur=USER)
        self.assertNotIn("cle_stockage", rep)
        self.assertEqual(rep["id"], 4)

    def test_detail_introuvable(self, pool):
        with mock.patch.object(stockage, "obtenir", side_effect=stockage.DocumentIntrouvable("non")):
            with self.assertRaises(idp.HTTPException) as ctx:
                idp.detail_document(4, utilisateur=USER)
        self.assertEqual(code(ctx), 404)

    def test_telechargement_en_piece_jointe(self, pool):
        with mock.patch.object(stockage, "obtenir",
                               return_value={"id": 4, "format": "pdf", "cle_stockage": "k/1"}), \
             mock.patch.object(stockage, "lire_fichier", return_value=b"%PDF") as lire:
            rep = idp.telecharger_fichier(4, utilisateur=USER)
        lire.assert_called_once_with("k/1")
        self.assertEqual(rep.body, b"%PDF")
        self.assertEqual(rep.media_type, "application/octet-stream")
        self.assertEqual(rep.headers["Content-Disposition"],
                         'attachment; filename="document-4.pdf"')
        self.assertEqual(rep.headers["X-Content-Type-Options"], "nosniff")

    def test_extension_inconnue_devient_bin(self, pool):
        for format_document in ("../../etc", "image", None):
            with mock.patch.object(stockage, "obtenir",
                                   return_value={"id": 4, "format": format_document, "cle_stockage": "k"}), \
                 mock.patch.object(stockage, "lire_fichier", return_value=b"x"):
                rep = idp.telecharger_fichier(4, utilisateur=USER)
            self.assertEqual(rep.headers["Content-Disposition"],
                             'attachment; filename="document-4.bin"')


@mock.patch.object(idp, "get_pool_entreprise", return_value="POOL")
class TestDecisions(unittest.TestCase):
    def test_correction_transmet_uniquement_les_champs_envoyes(self, pool):
        corrections = idp.Corrections(numero="F-9", fournisseur={"nom": "Atlas"})
        with mock.patch.object(stockage, "corriger", return_value={"id": 4}) as corriger:
            idp.corriger_document(4, corrections, utilisateur=USER)
        corriger.assert_called_once_with(
            "POOL", 4, {"numero": "F-9", "fournisseur": {"nom": "Atlas"}}, "12")

    def test_correction_champ_inconnu_refuse_par_le_schema(self, pool):
        for corps in ({"statut": "valide"}, {"id": 1}, {"fournisseur": {"role": "x"}},
                      {"lignes": [{"truc": 1}]}):
            with self.assertRaises(ValidationError):
                idp.Corrections(**corps)

    def test_correction_vide_refusee(self, pool):
        with mock.patch.object(stockage, "corriger", side_effect=ValueError("aucun champ")):
            with self.assertRaises(idp.HTTPException) as ctx:
                idp.corriger_document(4, idp.Corrections(), utilisateur=USER)
        self.assertEqual(code(ctx), 422)

    def test_validation_ok(self, pool):
        with mock.patch.object(stockage, "valider", return_value={"id": 4, "statut": "valide"}) as valider:
            rep = idp.valider_document(4, utilisateur=USER)
        valider.assert_called_once_with("POOL", 4, "12")
        self.assertEqual(rep["statut"], "valide")

    def test_codes_d_erreur_de_validation(self, pool):
        cas = [
            (stockage.DocumentIntrouvable("x"), 404),
            (stockage.TransitionInterdite("déjà traité"), 409),
            (stockage.ValidationBloquee("erreurs"), 409),
            (stockage.StockageFichierIndisponible("x"), 503),
        ]
        for erreur, attendu in cas:
            with self.subTest(erreur=type(erreur).__name__):
                with mock.patch.object(stockage, "valider", side_effect=erreur):
                    with self.assertRaises(idp.HTTPException) as ctx:
                        idp.valider_document(4, utilisateur=USER)
                self.assertEqual(code(ctx), attendu)

    def test_rejet(self, pool):
        with mock.patch.object(stockage, "rejeter", return_value={"id": 4, "statut": "rejete"}) as rejeter:
            idp.rejeter_document(4, idp.Rejet(motif="doublon"), utilisateur=USER)
        rejeter.assert_called_once_with("POOL", 4, "doublon", "12")

    def test_rejet_sans_motif_refuse_par_le_schema(self, pool):
        for motif in ("", "x" * 5000):
            with self.assertRaises(ValidationError):
                idp.Rejet(motif=motif)


@unittest.skipIf(TestClient is None, "fastapi.testclient indisponible")
class TestHttp(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(idp.router)
        self.client = TestClient(self.app)

    def _connecter(self, admin=False):
        self.app.dependency_overrides[idp.utilisateur_idp] = lambda: USER
        if admin:
            self.app.dependency_overrides[exiger_role_admin] = lambda: {**USER, "role": "admin"}

    def test_authentification_obligatoire(self):
        for methode, url in (("get", "/api/idp/documents"), ("get", "/api/idp/documents/1"),
                             ("post", "/api/idp/documents/1/valider"),
                             ("get", "/api/idp/documents/1/fichier")):
            with self.subTest(url=url):
                rep = getattr(self.client, methode)(url)
                self.assertIn(rep.status_code, (401, 403))

    def test_depot_multipart(self):
        self._connecter()
        with mock.patch.object(idp, "get_pool_entreprise", return_value="POOL"), \
             mock.patch.object(structuration, "traiter_document", return_value=RESULTAT), \
             mock.patch.object(stockage, "enregistrer_depot",
                               return_value={"id": 5, "statut": "brouillon", "doublons": []}):
            rep = self.client.post(
                "/api/idp/documents", files={"fichier": ("f.pdf", b"abc", "application/pdf")})
        self.assertEqual(rep.status_code, 201, rep.text)
        self.assertEqual(rep.json()["id"], 5)

    def test_depot_sans_fichier(self):
        self._connecter()
        self.assertEqual(self.client.post("/api/idp/documents").status_code, 422)

    def test_parametres_de_liste_valides(self):
        self._connecter()
        for requete in ("?statut=n_importe_quoi", "?limite=0", "?limite=999", "?decalage=-1"):
            with self.subTest(requete=requete):
                self.assertEqual(self.client.get("/api/idp/documents" + requete).status_code, 422)

    def test_identifiant_non_numerique(self):
        self._connecter()
        self.assertEqual(self.client.get("/api/idp/documents/abc").status_code, 422)

    def test_validation_et_conflit(self):
        self._connecter(admin=True)
        with mock.patch.object(idp, "get_pool_entreprise", return_value="POOL"):
            with mock.patch.object(stockage, "valider", return_value={"id": 5, "statut": "valide"}):
                rep = self.client.post("/api/idp/documents/5/valider")
            self.assertEqual((rep.status_code, rep.json()["statut"]), (200, "valide"))
            with mock.patch.object(stockage, "valider",
                                   side_effect=stockage.ValidationBloquee("déjà validé")):
                rep = self.client.post("/api/idp/documents/5/valider")
            self.assertEqual(rep.status_code, 409)
            self.assertIn("déjà validé", rep.json()["detail"])

    def test_rejet_exige_un_motif(self):
        self._connecter(admin=True)
        rep = self.client.post("/api/idp/documents/5/rejeter", json={})
        self.assertEqual(rep.status_code, 422)

    def test_correction_champ_interdit(self):
        self._connecter()
        rep = self.client.patch("/api/idp/documents/5", json={"statut": "valide"})
        self.assertEqual(rep.status_code, 422)


if __name__ == "__main__":
    unittest.main()
