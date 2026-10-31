"""Connexions inhabituelles et alertes (Lot 5c).

    python -m unittest tests.test_alertes_lot5c -v
"""
import inspect
import unittest
from unittest.mock import MagicMock, patch

from app.security import alertes
from app.security import appareils as appareils_mod
from app.security import sessions as sessions_mod

CLAIMS = {"id": 3, "email": "a@test.local", "type": "interne", "entrepriseId": 7, "nomBase": "compte_x"}
INFO = {"systeme": "Windows", "navigateur": "Chrome", "appareil": "ordinateur"}


def faux_pool(historique, echecs):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [historique, (echecs,)]
    return pool, cur


class TestEvaluer(unittest.TestCase):
    def _evaluer(self, historique, echecs=0, nouveau=False, ip="10.0.0.1"):
        pool, cur = faux_pool(historique, echecs)
        with patch.object(alertes, "pool_central", pool):
            raisons = alertes.evaluer(CLAIMS, INFO, ip, {"id": 1, "nouveau": nouveau}, "jti1")
        return raisons, cur

    def test_connexion_habituelle_ne_declenche_rien(self):
        self.assertEqual(self._evaluer((12, 5, 12))[0], [])

    def test_premiere_connexion_du_compte_n_est_pas_inhabituelle(self):
        self.assertEqual(self._evaluer((0, 0, 0))[0], [])

    def test_nouvelle_ip_et_nouveau_systeme(self):
        self.assertEqual(self._evaluer((4, 0, 4))[0], ["nouvelle_adresse_ip"])
        self.assertEqual(self._evaluer((4, 2, 0))[0], ["nouveau_systeme"])
        self.assertEqual(self._evaluer((4, 0, 0))[0], ["nouvelle_adresse_ip", "nouveau_systeme"])

    def test_nouvel_appareil_signale(self):
        self.assertEqual(self._evaluer((4, 2, 4), nouveau=True)[0], ["nouvel_appareil"])

    def test_echecs_repetes_avant_la_reussite(self):
        self.assertEqual(self._evaluer((4, 2, 4), echecs=3)[0], ["apres_echecs_repetes"])
        self.assertEqual(self._evaluer((4, 2, 4), echecs=2)[0], [])

    def test_ip_inconnue_n_est_pas_comptee_comme_nouvelle(self):
        self.assertEqual(self._evaluer((4, 0, 4), ip=None)[0], [])

    def test_la_session_en_cours_est_exclue_de_l_historique(self):
        _, cur = self._evaluer((4, 2, 4))
        requete, params = cur.execute.call_args_list[0][0]
        self.assertIn("jti <> %s", requete)
        self.assertEqual(params[-1], "jti1")
        self.assertIn("3", params)
        self.assertIn("7", params)


class TestTraiter(unittest.TestCase):
    def _lancer(self, raisons, erreur_notif=False, email="1"):
        notif = MagicMock(side_effect=RuntimeError("x") if erreur_notif else None)
        with patch.object(alertes, "evaluer", return_value=raisons), \
             patch.object(alertes, "journaliser") as journal, \
             patch.object(alertes, "_notifier", notif), \
             patch.object(alertes, "administrateurs", return_value=["9"]), \
             patch.object(alertes.threading, "Thread") as fil, \
             patch.dict("os.environ", {"ALERTES_EMAIL": email}):
            res = alertes.traiter_connexion(CLAIMS, None, INFO, "10.0.0.1", {"nouveau": True}, "jti1")
        return res, journal, notif, fil

    def test_rien_a_signaler_aucune_action(self):
        res, journal, notif, fil = self._lancer([])
        self.assertEqual(res, [])
        journal.assert_not_called()
        notif.assert_not_called()
        fil.assert_not_called()

    def test_alerte_complete(self):
        res, journal, notif, fil = self._lancer(["nouvelle_adresse_ip"])
        self.assertEqual(res, ["nouvelle_adresse_ip"])
        args, kw = journal.call_args
        self.assertEqual(args[0], "connexion_inhabituelle")
        self.assertEqual(kw["gravite"], "avertissement")
        self.assertEqual(kw["details"], {"raison": "nouvelle_adresse_ip"})
        # une notification pour la personne, une pour l'administrateur
        self.assertEqual(notif.call_count, 2)
        self.assertEqual(notif.call_args_list[0][0][:3], ("interne", 3, 7))
        self.assertEqual(notif.call_args_list[1][0][:3], ("interne", "9", 7))
        fil.return_value.start.assert_called_once()

    def test_gravite_critique_si_echecs_repetes_et_autre_signal(self):
        _, journal, _, _ = self._lancer(["nouvelle_adresse_ip", "apres_echecs_repetes"])
        self.assertEqual(journal.call_args[1]["gravite"], "critique")
        _, journal, _, _ = self._lancer(["apres_echecs_repetes"])
        self.assertEqual(journal.call_args[1]["gravite"], "avertissement")

    def test_email_desactivable(self):
        _, _, _, fil = self._lancer(["nouveau_systeme"], email="0")
        fil.assert_not_called()

    def test_une_panne_de_notification_ne_casse_rien(self):
        res, journal, _, fil = self._lancer(["nouveau_systeme"], erreur_notif=True)
        self.assertEqual(res, ["nouveau_systeme"])
        journal.assert_called_once()
        fil.return_value.start.assert_called_once()

    def test_ne_leve_jamais_meme_si_l_analyse_echoue(self):
        with patch.object(alertes, "evaluer", side_effect=RuntimeError("base indisponible")):
            self.assertEqual(alertes.traiter_connexion(CLAIMS, None, INFO, "1.1.1.1", {}, "j"), [])


class TestAdministrateurs(unittest.TestCase):
    def test_uniquement_les_comptes_internes_d_entreprise(self):
        for claims in ({"type": "externe", "id": 1, "nomBase": "x"}, {"type": "plateforme", "id": 1}):
            self.assertEqual(alertes.administrateurs(claims), [])

    def test_requete_exclut_l_utilisateur_et_filtre_le_role_admin(self):
        pool = MagicMock()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [(5,), (8,)]
        with patch.object(alertes, "get_pool_entreprise", return_value=pool):
            self.assertEqual(alertes.administrateurs(CLAIMS), ["5", "8"])
        requete, params = cur.execute.call_args[0]
        self.assertIn("r.nom = 'Admin'", requete)
        self.assertIn("u.id <> %s", requete)
        self.assertEqual(params, (3,))
        pool.putconn.assert_called_once()


class TestAppareilEnAttente(unittest.TestCase):
    def test_notifie_la_personne_et_les_administrateurs(self):
        with patch.object(alertes, "_notifier") as notif, \
             patch.object(alertes, "administrateurs", return_value=["9"]):
            alertes.notifier_appareil_en_attente(CLAIMS, "Edge sur Windows")
        self.assertEqual(notif.call_count, 2)
        self.assertIn("attend votre autorisation", notif.call_args[0][4])

    def test_ne_leve_jamais(self):
        with patch.object(alertes, "administrateurs", side_effect=RuntimeError("x")):
            alertes.notifier_appareil_en_attente(CLAIMS, "Edge sur Windows")


class TestBranchement(unittest.TestCase):
    def test_la_connexion_declenche_l_analyse_apres_l_enregistrement(self):
        source = inspect.getsource(sessions_mod.emettre_jeton)
        self.assertIn("traiter_connexion(", source)
        self.assertGreater(source.index("traiter_connexion("), source.index("INSERT INTO session_utilisateur"))

    def test_le_mode_strict_alerte_les_administrateurs(self):
        source = inspect.getsource(appareils_mod.enregistrer_connexion)
        self.assertIn("notifier_appareil_en_attente(", source)


if __name__ == "__main__":
    unittest.main()
