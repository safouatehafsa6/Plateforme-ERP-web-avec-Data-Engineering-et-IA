"""Comptes externes : unicite de l'email et fermeture des sessions (Lot 1b).

    python -m unittest tests.test_utilisateurs_externes_isolation -v
"""
import unittest
from unittest.mock import MagicMock, patch

from app.routers import utilisateurs_externes as ue

ADMIN = {"id": 1, "email": "admin@test.local", "type": "interne", "role": "Admin",
         "nomBase": "compte_a", "entrepriseId": 1}


class TestCreation(unittest.TestCase):
    def test_email_deja_rattache_refuse_avant_toute_creation(self):
        payload = ue.NouvelUtilisateurExternePayload(email="Victime@Test.local", clientNom="Client")
        with patch.object(ue, "email_disponible_pour", return_value=False) as dispo, \
             patch.object(ue, "get_pool_entreprise") as pool, \
             patch.object(ue, "indexer_compte_central") as indexer:
            with self.assertRaises(ue.HTTPException) as ctx:
                ue.creer_utilisateur_externe(payload, utilisateur=dict(ADMIN))
        self.assertEqual(ctx.exception.status_code, 409)
        dispo.assert_called_once_with("victime@test.local", 1)
        pool.assert_not_called()
        indexer.assert_not_called()


class TestDesactivation(unittest.TestCase):
    def _basculer(self, actif):
        pool = MagicMock()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (5, "externe@test.local")
        with patch.object(ue, "get_pool_entreprise", return_value=pool), \
             patch.object(ue, "revoquer_sessions_par_email") as revoquer:
            ue.basculer_actif(5, ue.ToggleActifPayload(actif=actif), utilisateur=dict(ADMIN))
        return revoquer, cur

    def test_desactiver_ferme_les_sessions_du_compte(self):
        revoquer, cur = self._basculer(False)
        revoquer.assert_called_once_with("externe@test.local", "compte_desactive", "externe")
        self.assertIn("RETURNING id, email", cur.execute.call_args[0][0])

    def test_reactiver_ne_ferme_rien(self):
        revoquer, _ = self._basculer(True)
        revoquer.assert_not_called()

    def test_compte_introuvable_donne_404(self):
        pool = MagicMock()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None
        with patch.object(ue, "get_pool_entreprise", return_value=pool), \
             patch.object(ue, "revoquer_sessions_par_email") as revoquer:
            with self.assertRaises(ue.HTTPException) as ctx:
                ue.basculer_actif(99, ue.ToggleActifPayload(actif=False), utilisateur=dict(ADMIN))
        self.assertEqual(ctx.exception.status_code, 404)
        revoquer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
