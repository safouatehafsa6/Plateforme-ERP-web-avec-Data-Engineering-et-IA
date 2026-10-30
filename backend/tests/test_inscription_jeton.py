"""Jeton d'inscription signe (Lot 2).

    python -m unittest tests.test_inscription_jeton -v
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import entreprises

SECRET = "secret-de-test-" + "x" * 40
SUPER_ADMIN = {"id": 1, "email": "root@test.local", "type": "plateforme", "role": "super_admin"}


def faux_pool(ligne):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ligne
    return pool


class Base(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"JWT_SECRET": SECRET})
        self._env.start()
        os.environ.pop("ONBOARDING_AUTO_VALIDATION", None)
        self.app = FastAPI()
        self.app.include_router(entreprises.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self._env.stop()

    def entetes(self, entreprise_id=5):
        return {"X-Jeton-Inscription": entreprises._emettre_jeton_inscription(entreprise_id)}


class TestJeton(Base):
    def test_verifier_otp_renvoie_un_jeton_pour_cette_entreprise(self):
        with patch.object(entreprises, "verifier_otp", return_value=(True, "ok")):
            rep = self.client.post("/api/entreprises/verifier-otp",
                                   json={"entrepriseId": 5, "code": "123456"})
        self.assertEqual(rep.status_code, 200, rep.text)
        jeton = rep.json()["jetonInscription"]
        charge = jwt.decode(jeton, SECRET, algorithms=["HS256"], audience="inscription")
        self.assertEqual(charge["sub"], "5")
        self.assertEqual(charge["scope"], "inscription")

    def test_otp_incorrect_ne_donne_aucun_jeton(self):
        with patch.object(entreprises, "verifier_otp", return_value=(False, "code_incorrect")):
            rep = self.client.post("/api/entreprises/verifier-otp",
                                   json={"entrepriseId": 5, "code": "000000"})
        self.assertEqual(rep.status_code, 400)
        self.assertNotIn("jetonInscription", rep.text)

    def test_jeton_valide_uniquement_pour_sa_propre_entreprise(self):
        jeton = entreprises._emettre_jeton_inscription(5)
        entreprises._exiger_jeton_inscription(5, jeton)  # ne leve rien
        with self.assertRaises(entreprises.HTTPException) as ctx:
            entreprises._exiger_jeton_inscription(6, jeton)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_jeton_absent_invalide_expire_ou_mal_signe(self):
        expire = jwt.encode(
            {"sub": "5", "scope": "inscription", "aud": "inscription",
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            SECRET, algorithm="HS256")
        autre_cle = jwt.encode(
            {"sub": "5", "scope": "inscription", "aud": "inscription",
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "une-autre-cle-" + "y" * 40, algorithm="HS256")
        for nom, jeton in (("absent", None), ("vide", ""), ("n_importe_quoi", "abc"),
                           ("expire", expire), ("mal_signe", autre_cle)):
            with self.subTest(cas=nom):
                with self.assertRaises(entreprises.HTTPException) as ctx:
                    entreprises._exiger_jeton_inscription(5, jeton)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_jeton_d_inscription_inutilisable_comme_jeton_de_session(self):
        # Meme decodage que security/auth_dependency.py (sans audience).
        jeton = entreprises._emettre_jeton_inscription(5)
        with self.assertRaises(jwt.InvalidTokenError):
            jwt.decode(jeton, SECRET, algorithms=["HS256"])


class TestRoutesProtegeesParLeJeton(Base):
    CORPS = {"entrepriseId": 5, "documents": {"cin": "cin.pdf"}}

    def test_kyc_sans_jeton_refuse(self):
        rep = self.client.post("/api/entreprises/kyc", json=self.CORPS)
        self.assertEqual(rep.status_code, 401)

    def test_kyc_avec_jeton_d_une_autre_entreprise_refuse(self):
        rep = self.client.post("/api/entreprises/kyc", json=self.CORPS, headers=self.entetes(6))
        self.assertEqual(rep.status_code, 403)

    def test_kyc_avec_bon_jeton_accepte_mais_ne_valide_pas_seul(self):
        with patch.object(entreprises, "pool_central", faux_pool(("personne_physique", "en_attente"))), \
             patch.object(entreprises, "_valider_dossier") as valider:
            rep = self.client.post("/api/entreprises/kyc", json=self.CORPS, headers=self.entetes(5))
        self.assertEqual(rep.status_code, 200, rep.text)
        valider.assert_not_called()

    def test_abonnement_exige_jeton_et_plan_valide(self):
        corps = {"entrepriseId": 5, "plan": "standard"}
        self.assertEqual(self.client.post("/api/entreprises/abonnement", json=corps).status_code, 401)
        rep = self.client.post("/api/entreprises/abonnement",
                               json={"entrepriseId": 5, "plan": "gratuit-illimite"},
                               headers=self.entetes(5))
        self.assertEqual(rep.status_code, 400)
        with patch.object(entreprises, "_statut_est", return_value=True), \
             patch.object(entreprises, "pool_central", MagicMock()):
            rep = self.client.post("/api/entreprises/abonnement", json=corps, headers=self.entetes(5))
        self.assertEqual(rep.status_code, 200, rep.text)
        self.assertTrue(rep.json()["requiertPaiement"])

    def test_activer_essai_sans_jeton_refuse(self):
        with patch.object(entreprises, "_activer_entreprise") as activer:
            rep = self.client.post("/api/entreprises/activer-essai", json={"entrepriseId": 5})
        self.assertEqual(rep.status_code, 401)
        activer.assert_not_called()

    def test_activer_essai_refuse_si_le_plan_choisi_n_est_pas_l_essai(self):
        with patch.object(entreprises, "_plan_est_essai", return_value=False), \
             patch.object(entreprises, "_activer_entreprise") as activer:
            rep = self.client.post("/api/entreprises/activer-essai",
                                   json={"entrepriseId": 5}, headers=self.entetes(5))
        self.assertEqual(rep.status_code, 403)
        activer.assert_not_called()

    def test_activer_essai_accepte_avec_jeton_et_plan_essai(self):
        with patch.object(entreprises, "_plan_est_essai", return_value=True), \
             patch.object(entreprises, "_activer_entreprise", return_value={"message": "ok"}) as activer:
            rep = self.client.post("/api/entreprises/activer-essai",
                                   json={"entrepriseId": 5}, headers=self.entetes(5))
        self.assertEqual(rep.status_code, 200, rep.text)
        activer.assert_called_once_with(5)

    def test_confirmer_paiement_jamais_accessible_avec_le_seul_jeton(self):
        with patch.object(entreprises, "_activer_entreprise") as activer:
            rep = self.client.post("/api/entreprises/confirmer-paiement",
                                   json={"entrepriseId": 5}, headers=self.entetes(5))
        self.assertEqual(rep.status_code, 403)
        activer.assert_not_called()

    def test_jeton_d_inscription_refuse_comme_authentification_super_admin(self):
        # Envoye par erreur dans Authorization : doit etre refuse (401), pas accepte.
        jeton = entreprises._emettre_jeton_inscription(5)
        with patch.object(entreprises, "_activer_entreprise") as activer:
            rep = self.client.post("/api/entreprises/confirmer-paiement",
                                   json={"entrepriseId": 5},
                                   headers={"Authorization": "Bearer " + jeton})
        self.assertIn(rep.status_code, (401, 403))
        activer.assert_not_called()

    def test_mode_demo_ne_demande_pas_de_jeton(self):
        os.environ["ONBOARDING_AUTO_VALIDATION"] = "1"
        with patch.object(entreprises, "_activer_entreprise", return_value={"message": "ok"}):
            rep = self.client.post("/api/entreprises/activer-essai", json={"entrepriseId": 5})
        self.assertEqual(rep.status_code, 200, rep.text)


class TestPlanEstEssai(unittest.TestCase):
    def _plan(self, ligne):
        with patch.object(entreprises, "pool_central", faux_pool(ligne)):
            return entreprises._plan_est_essai(5)

    def test_cas(self):
        self.assertTrue(self._plan(("essai",)))
        self.assertFalse(self._plan(("standard",)))
        self.assertFalse(self._plan(None))


if __name__ == "__main__":
    unittest.main()
