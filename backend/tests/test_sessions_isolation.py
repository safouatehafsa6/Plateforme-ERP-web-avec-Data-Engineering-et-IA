"""Isolation entre entreprises des routes /api/sessions (Lot 1).

    python -m unittest tests.test_sessions_isolation -v

Les identifiants utilisateur sont propres a chaque base entreprise : toute
requete sur les sessions doit donc aussi filtrer sur l'entreprise du jeton.
"""
import unittest
from unittest.mock import MagicMock, patch

from app.routers import sessions


def utilisateur(entreprise_id, uid=3):
    u = {"id": uid, "type": "interne", "email": "u%s@ent.test" % uid, "jti": "jti-courant"}
    if entreprise_id is not None:
        u["entrepriseId"] = entreprise_id
    return u


class TestIsolationSessions(unittest.TestCase):
    def _executer(self, fonction, *args, **kw):
        with patch.object(sessions, "_lire", return_value=[]) as lire, \
             patch.object(sessions, "_ecrire", return_value=1) as ecrire, \
             patch.object(sessions, "journaliser"):
            fonction(*args, **kw)
        appel = lire if lire.called else ecrire
        self.assertTrue(appel.called, "aucune requete SQL executee")
        requete, params = appel.call_args[0]
        return requete, params

    def _cas(self, u):
        return {
            "lister": lambda: self._executer(sessions.lister_mes_sessions, utilisateur=u),
            "evenements": lambda: self._executer(
                sessions.mes_evenements, limit=20, avant=None, type=None, utilisateur=u),
            "revoquer_autres": lambda: self._executer(
                sessions.revoquer_les_autres_sessions, MagicMock(), u),
            "revoquer_une": lambda: self._executer(
                sessions.revoquer_ma_session, "un-jti", MagicMock(), u),
        }

    def test_toutes_les_requetes_filtrent_sur_l_entreprise(self):
        for nom, lancer in self._cas(utilisateur(7)).items():
            with self.subTest(route=nom):
                requete, params = lancer()
                self.assertIn("entreprise_id IS NOT DISTINCT FROM", requete)
                self.assertIn("7", params)

    def test_meme_identifiant_dans_deux_entreprises_donne_des_requetes_distinctes(self):
        cas_a = self._cas(utilisateur(1, uid=3))
        cas_b = self._cas(utilisateur(2, uid=3))
        for nom in cas_a:
            with self.subTest(route=nom):
                _, params_a = cas_a[nom]()
                _, params_b = cas_b[nom]()
                self.assertNotEqual(params_a, params_b)
                self.assertIn("1", params_a)
                self.assertIn("2", params_b)
                self.assertNotIn("2", params_a)

    def test_super_admin_sans_entreprise_filtre_sur_null(self):
        for nom, lancer in self._cas(utilisateur(None)).items():
            with self.subTest(route=nom):
                requete, params = lancer()
                self.assertIn("entreprise_id IS NOT DISTINCT FROM", requete)
                self.assertIn(None, params)


if __name__ == "__main__":
    unittest.main()
