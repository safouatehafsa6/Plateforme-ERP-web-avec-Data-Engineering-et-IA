"""Securisation du parcours d'inscription /api/entreprises (Lot 1).

    python -m unittest tests.test_onboarding_securite -v
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import entreprises
from app.security.jwt_utils import exiger_super_admin

SUPER_ADMIN = {"id": 1, "email": "root@test.local", "type": "plateforme", "role": "super_admin"}


def faux_pool(ligne):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ligne
    return pool


class Base(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(entreprises.router)
        self.client = TestClient(self.app)
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ONBOARDING_AUTO_VALIDATION", None)

    def tearDown(self):
        self._env.stop()


class TestValidationReserveeAuSuperAdmin(Base):
    def test_valider_et_refuser_exigent_une_authentification(self):
        with patch.object(entreprises, "_changer_statut_si") as changer:
            for url in ("/api/entreprises/valider", "/api/entreprises/refuser"):
                with self.subTest(url=url):
                    rep = self.client.post(url, json={"entrepriseId": 1})
                    self.assertIn(rep.status_code, (401, 403))
            changer.assert_not_called()

    def test_valider_transition_autorisee_uniquement_depuis_en_attente(self):
        self.app.dependency_overrides[exiger_super_admin] = lambda: SUPER_ADMIN
        with patch.object(entreprises, "_changer_statut_si", return_value=True) as changer:
            rep = self.client.post("/api/entreprises/valider", json={"entrepriseId": 5})
        self.assertEqual(rep.status_code, 200, rep.text)
        entreprise_id, nouveau, autorises = changer.call_args[0]
        self.assertEqual((entreprise_id, nouveau), (5, "valide"))
        self.assertEqual(tuple(autorises), ("en_attente",))

    def test_refuser_ne_touche_jamais_une_entreprise_active(self):
        self.app.dependency_overrides[exiger_super_admin] = lambda: SUPER_ADMIN
        with patch.object(entreprises, "_changer_statut_si", return_value=True) as changer:
            rep = self.client.post("/api/entreprises/refuser", json={"entrepriseId": 5})
        self.assertEqual(rep.status_code, 200, rep.text)
        autorises = changer.call_args[0][2]
        self.assertNotIn("actif", autorises)
        self.assertNotIn("refuse", autorises)

    def test_transition_refusee_donne_409(self):
        self.app.dependency_overrides[exiger_super_admin] = lambda: SUPER_ADMIN
        with patch.object(entreprises, "_changer_statut_si", return_value=False):
            for url in ("/api/entreprises/valider", "/api/entreprises/refuser"):
                with self.subTest(url=url):
                    rep = self.client.post(url, json={"entrepriseId": 5})
                    self.assertEqual(rep.status_code, 409)

    def test_changer_statut_si_filtre_sur_le_statut_actuel_en_sql(self):
        pool = faux_pool((5,))
        with patch.object(entreprises, "pool_central", pool):
            self.assertTrue(entreprises._changer_statut_si(5, "valide", ("en_attente",)))
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        requete, params = cur.execute.call_args[0]
        self.assertIn("statut = ANY(%s)", requete)
        self.assertEqual(params, ("valide", 5, ["en_attente"]))


class TestActivationControlee(Base):
    URLS = ("/api/entreprises/confirmer-paiement", "/api/entreprises/activer-essai")

    def test_sans_mode_demo_et_sans_jeton_refuse(self):
        with patch.object(entreprises, "_activer_entreprise") as activer:
            for url in self.URLS:
                with self.subTest(url=url):
                    rep = self.client.post(url, json={"entrepriseId": 1})
                    self.assertIn(rep.status_code, (401, 403))
            activer.assert_not_called()

    def test_mode_demo_active_laisse_passer_le_parcours_public(self):
        os.environ["ONBOARDING_AUTO_VALIDATION"] = "1"
        with patch.object(entreprises, "_activer_entreprise", return_value={"message": "ok"}) as activer:
            for url in self.URLS:
                with self.subTest(url=url):
                    rep = self.client.post(url, json={"entrepriseId": 1})
                    self.assertEqual(rep.status_code, 200, rep.text)
            self.assertEqual(activer.call_count, 2)

    def test_super_admin_authentifie_peut_activer_sans_mode_demo(self):
        with patch.object(entreprises, "obtenir_utilisateur_courant", return_value=SUPER_ADMIN), \
             patch.object(entreprises, "exiger_super_admin", return_value=SUPER_ADMIN), \
             patch.object(entreprises, "_activer_entreprise", return_value={"message": "ok"}) as activer:
            rep = self.client.post(self.URLS[0], json={"entrepriseId": 1},
                                   headers={"Authorization": "Bearer jeton-test"})
        self.assertEqual(rep.status_code, 200, rep.text)
        activer.assert_called_once()

    def test_kyc_refuse_pour_une_entreprise_deja_active(self):
        with patch.object(entreprises, "pool_central", faux_pool(("personne_physique", "actif"))), \
             patch.object(entreprises, "_exiger_jeton_inscription"):
            rep = self.client.post("/api/entreprises/kyc", json={
                "entrepriseId": 1, "documents": {"cin": "cin.pdf"}})
        self.assertEqual(rep.status_code, 409)

    def test_kyc_sans_mode_demo_ne_valide_pas_automatiquement(self):
        with patch.object(entreprises, "pool_central", faux_pool(("personne_physique", "en_attente"))), \
             patch.object(entreprises, "_exiger_jeton_inscription"), \
             patch.object(entreprises, "_valider_dossier") as valider:
            rep = self.client.post("/api/entreprises/kyc", json={
                "entrepriseId": 1, "documents": {"cin": "cin.pdf"}})
        self.assertEqual(rep.status_code, 200, rep.text)
        valider.assert_not_called()

    def test_kyc_en_mode_demo_valide_automatiquement(self):
        os.environ["ONBOARDING_AUTO_VALIDATION"] = "1"
        with patch.object(entreprises, "pool_central", faux_pool(("personne_physique", "en_attente"))), \
             patch.object(entreprises, "_valider_dossier") as valider:
            rep = self.client.post("/api/entreprises/kyc", json={
                "entrepriseId": 1, "documents": {"cin": "cin.pdf"}})
        self.assertEqual(rep.status_code, 200, rep.text)
        valider.assert_called_once_with(1)


class TestActiverEntreprise(Base):
    ADMIN_TEMP = {"nom": "Ali Test", "email": "ali@test.local", "mot_de_passe_hash": "hash"}

    def test_refuse_si_email_non_verifie(self):
        with patch.object(entreprises, "recuperer_admin_temporaire", return_value=self.ADMIN_TEMP), \
             patch.object(entreprises, "email_verifie", return_value=False), \
             patch.object(entreprises, "provisionner_entreprise") as prov:
            rep = entreprises._activer_entreprise(1)
        self.assertEqual(rep.status_code, 400)
        prov.assert_not_called()

    def test_refuse_si_dossier_non_valide(self):
        for statut in ("en_attente", "refuse", "actif", "suspendu"):
            with self.subTest(statut=statut):
                with patch.object(entreprises, "recuperer_admin_temporaire", return_value=self.ADMIN_TEMP), \
                     patch.object(entreprises, "email_verifie", return_value=True), \
                     patch.object(entreprises, "pool_central", faux_pool(("compte_x", statut))), \
                     patch.object(entreprises, "provisionner_entreprise") as prov:
                    rep = entreprises._activer_entreprise(1)
                self.assertEqual(rep.status_code, 409)
                prov.assert_not_called()

    def test_erreur_de_provisioning_ne_fuit_pas_de_detail_interne(self):
        with patch.object(entreprises, "recuperer_admin_temporaire", return_value=self.ADMIN_TEMP), \
             patch.object(entreprises, "email_verifie", return_value=True), \
             patch.object(entreprises, "pool_central", faux_pool(("compte_x", "valide"))), \
             patch.object(entreprises, "provisionner_entreprise",
                          side_effect=Exception("password=secret-interne host=db")):
            rep = entreprises._activer_entreprise(1)
        self.assertEqual(rep.status_code, 500)
        corps = rep.body.decode("utf-8")
        self.assertNotIn("secret-interne", corps)
        self.assertNotIn("password", corps)


class TestOtpEmailVerifie(unittest.TestCase):
    def test_email_verifie_seulement_apres_otp_valide(self):
        from app.security import onboarding_store as store
        store._entreprises_email_verifie.discard(987654)
        self.assertFalse(store.email_verifie(987654))
        code = store.generer_et_stocker_otp(987654)
        self.assertEqual(store.verifier_otp(987654, "000000" if code != "000000" else "111111")[0], False)
        self.assertFalse(store.email_verifie(987654))
        self.assertTrue(store.verifier_otp(987654, code)[0])
        self.assertTrue(store.email_verifie(987654))
        store._entreprises_email_verifie.discard(987654)


if __name__ == "__main__":
    unittest.main()
