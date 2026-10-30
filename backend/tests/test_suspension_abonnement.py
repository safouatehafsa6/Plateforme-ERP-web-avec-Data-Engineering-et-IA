"""Suspension d'abonnement effective (Lot 3).

    python -m unittest tests.test_suspension_abonnement -v
"""
import inspect
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin, auth

ADMIN = {"id": 1, "email": "root@test.local"}


def faux_pool(*lignes, rowcount=3):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = list(lignes)
    cur.rowcount = rowcount
    return pool, cur


class TestChangerStatutAbonnement(unittest.TestCase):
    def _appeler(self, abonnement_id, statut, lignes):
        pool, cur = faux_pool(*lignes)
        with patch.object(admin, "pool_central", pool), \
             patch.object(admin, "journaliser") as journal:
            rep = admin._changer_statut_abonnement(abonnement_id, statut, ADMIN, None)
        requetes = [c[0][0] for c in cur.execute.call_args_list]
        params = [c[0][1] for c in cur.execute.call_args_list]
        return rep, requetes, params, journal

    def test_suspension_ferme_les_sessions_de_l_entreprise(self):
        rep, requetes, params, journal = self._appeler(5, "suspendu", [(5, 7), (5,)])
        indices = [i for i, r in enumerate(requetes) if "UPDATE session_utilisateur" in r]
        self.assertEqual(len(indices), 1)
        self.assertEqual(params[indices[0]], ("7",))
        self.assertEqual(rep["sessionsFermees"], 3)
        args, kwargs = journal.call_args
        self.assertEqual(args[0], "entreprise_suspendue")
        self.assertEqual(kwargs["entreprise_id"], 7)
        self.assertEqual(kwargs["acteur_email"], "root@test.local")

    def test_suspendre_un_ancien_abonnement_ne_ferme_rien(self):
        rep, requetes, _, _ = self._appeler(4, "suspendu", [(4, 7), (5,)])
        self.assertFalse(any("session_utilisateur" in r for r in requetes))
        self.assertEqual(rep["sessionsFermees"], 0)

    def test_reactivation_ne_ferme_aucune_session_et_est_journalisee(self):
        rep, requetes, _, journal = self._appeler(5, "actif", [(5, 7)])
        self.assertFalse(any("session_utilisateur" in r for r in requetes))
        self.assertEqual(rep["sessionsFermees"], 0)
        self.assertEqual(journal.call_args[0][0], "entreprise_reactivee")

    def test_abonnement_introuvable_donne_404_sans_journal(self):
        rep, _, _, journal = self._appeler(99, "suspendu", [None])
        self.assertEqual(rep.status_code, 404)
        journal.assert_not_called()

    def test_routes_reservees_au_super_admin(self):
        app = FastAPI()
        app.include_router(admin.router)
        client = TestClient(app)
        for action in ("suspendre", "reactiver"):
            with self.subTest(action=action):
                rep = client.post("/api/admin/abonnements/5/" + action)
                self.assertIn(rep.status_code, (401, 403))


class TestLoginEtSuspension(unittest.TestCase):
    def _suspendu(self, ligne):
        pool, _ = faux_pool(ligne)
        with patch.object(auth, "pool_central", pool):
            return auth._abonnement_suspendu(7)

    def test_abonnement_suspendu_detecte_sur_le_plus_recent(self):
        self.assertTrue(self._suspendu(("suspendu",)))
        self.assertFalse(self._suspendu(("actif",)))
        self.assertFalse(self._suspendu(None))

    def test_refus_403_et_journal_si_suspendu(self):
        with patch.object(auth, "_abonnement_suspendu", return_value=True), \
             patch.object(auth, "journaliser") as journal:
            rep = auth._refus_si_abonnement_suspendu(7, "interne", "a@test.local", None)
        self.assertEqual(rep.status_code, 403)
        self.assertIn("suspendu", json.loads(rep.body)["message"])
        self.assertEqual(journal.call_args[1]["details"], {"raison": "abonnement_suspendu"})

    def test_pas_de_refus_si_abonnement_actif(self):
        with patch.object(auth, "_abonnement_suspendu", return_value=False), \
             patch.object(auth, "journaliser") as journal:
            self.assertIsNone(auth._refus_si_abonnement_suspendu(7, "interne", "a@test.local", None))
        journal.assert_not_called()

    def test_login_controle_l_abonnement_pour_les_deux_profils(self):
        source = inspect.getsource(auth.login)
        self.assertEqual(source.count("_refus_si_abonnement_suspendu("), 2)
        # Le controle vient APRES la verification du mot de passe.
        self.assertLess(source.index("bcrypt.checkpw"), source.index("_refus_si_abonnement_suspendu("))


if __name__ == "__main__":
    unittest.main()
