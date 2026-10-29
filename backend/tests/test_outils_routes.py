"""Tests de la route /api/outils/montant-en-lettres.

    python -m unittest tests.test_outils_routes -v
"""
import unittest

from app.routers import outils
from app.security.auth_dependency import utilisateur_connecte

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:          # pragma: no cover
    TestClient = None

USER = {"id": 1, "type": "interne", "nomBase": "compte_test"}


class TestAppelDirect(unittest.TestCase):
    def appeler(self, montant, devise="MAD", langue="fr"):
        return outils.montant_en_lettres(montant=montant, devise=devise, langue=langue,
                                         utilisateur=USER)

    def test_nominal(self):
        rep = self.appeler("1 234,50")
        self.assertEqual(rep["montant"], "1234.50")
        self.assertEqual(rep["devise"], "MAD")
        self.assertEqual(rep["langue"], "fr")
        self.assertEqual(rep["libelle"], "Montant en lettres")
        self.assertEqual(rep["texte"], "mille deux cent trente-quatre dirhams et cinquante centimes")

    def test_alias_normalises_dans_la_reponse(self):
        rep = self.appeler("2", devise="dh", langue="AR-ma")
        self.assertEqual((rep["devise"], rep["langue"], rep["texte"]), ("MAD", "ar", "درهمان"))

    def test_entrees_invalides_donnent_422(self):
        for montant, devise, langue in [("abc", "MAD", "fr"), ("1", "XYZ", "fr"),
                                        ("1", "MAD", "de"), ("1" + "0" * 20, "MAD", "fr")]:
            with self.subTest(montant=montant, devise=devise, langue=langue):
                with self.assertRaises(outils.HTTPException) as ctx:
                    self.appeler(montant, devise, langue)
                self.assertEqual(ctx.exception.status_code, 422)

    def test_liste_des_devises(self):
        rep = outils.devises_prises_en_charge(utilisateur=USER)
        self.assertEqual(rep["devises"], ["EUR", "MAD", "USD"])
        self.assertEqual(rep["langues"], ["fr", "en", "ar"])


@unittest.skipIf(TestClient is None, "fastapi.testclient indisponible")
class TestHttp(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(outils.router)
        self.client = TestClient(self.app)

    def test_authentification_obligatoire(self):
        for url in ("/api/outils/montant-en-lettres?montant=10",
                    "/api/outils/montant-en-lettres/devises"):
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (401, 403))

    def test_requete_authentifiee(self):
        self.app.dependency_overrides[utilisateur_connecte] = lambda: USER
        rep = self.client.get("/api/outils/montant-en-lettres",
                              params={"montant": "1234.5", "devise": "EUR", "langue": "en"})
        self.assertEqual(rep.status_code, 200, rep.text)
        self.assertEqual(rep.json()["texte"],
                         "one thousand two hundred thirty-four euros and fifty cents")

    def test_arabe_en_utf8(self):
        self.app.dependency_overrides[utilisateur_connecte] = lambda: USER
        rep = self.client.get("/api/outils/montant-en-lettres",
                              params={"montant": "3", "langue": "ar"})
        self.assertEqual(rep.json()["texte"], "ثلاثة دراهم")

    def test_parametres_invalides(self):
        self.app.dependency_overrides[utilisateur_connecte] = lambda: USER
        self.assertEqual(self.client.get("/api/outils/montant-en-lettres").status_code, 422)
        self.assertEqual(self.client.get(
            "/api/outils/montant-en-lettres", params={"montant": "x" * 50}).status_code, 422)
        self.assertEqual(self.client.get(
            "/api/outils/montant-en-lettres", params={"montant": "abc"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
