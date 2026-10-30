"""compte_index : un email ne doit jamais etre detourne vers une autre
entreprise (Lot 1).

    python -m unittest tests.test_compte_index_conflit -v
"""
import unittest
from unittest.mock import MagicMock, patch

from app.services import provisioning


def faux_pool(ligne):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ligne
    return pool, cur


class TestIndexerCompteCentral(unittest.TestCase):
    def test_sql_ne_modifie_pas_l_entreprise_et_refuse_les_conflits(self):
        pool, cur = faux_pool(("a@test.local",))
        with patch.object(provisioning, "pool_central", pool):
            provisioning.indexer_compte_central("A@Test.local", 1, "compte_a")
        requete, params = cur.execute.call_args[0]
        self.assertNotIn("SET entreprise_id", requete)
        self.assertIn("WHERE compte_index.entreprise_id = EXCLUDED.entreprise_id", requete)
        self.assertIn("RETURNING email", requete)
        self.assertEqual(params[0], "a@test.local")

    def test_conflit_avec_une_autre_entreprise_leve_une_erreur(self):
        pool, _ = faux_pool(None)  # aucune ligne renvoyee : la mise a jour a ete refusee
        with patch.object(provisioning, "pool_central", pool):
            with self.assertRaises(provisioning.CompteDejaIndexeError):
                provisioning.indexer_compte_central("victime@test.local", 2, "compte_b")


class TestEmailDisponiblePour(unittest.TestCase):
    def _dispo(self, ligne, entreprise_id):
        pool, _ = faux_pool(ligne)
        with patch.object(provisioning, "pool_central", pool):
            return provisioning.email_disponible_pour("x@test.local", entreprise_id)

    def test_email_libre(self):
        self.assertTrue(self._dispo(None, 1))

    def test_email_deja_dans_la_meme_entreprise(self):
        self.assertTrue(self._dispo((1,), 1))
        self.assertTrue(self._dispo((1,), "1"))

    def test_email_d_une_autre_entreprise(self):
        self.assertFalse(self._dispo((2,), 1))


if __name__ == "__main__":
    unittest.main()
