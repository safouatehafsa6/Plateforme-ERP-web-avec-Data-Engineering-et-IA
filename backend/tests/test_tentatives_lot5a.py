"""Protection anti-brute-force persistante (Lot 5a).

    python -m unittest tests.test_tentatives_lot5a -v
"""
import asyncio
import inspect
import json
import unittest
from unittest.mock import MagicMock, patch

from app.routers import auth
from app.security import protection, tentatives


def faux_pool(*lignes):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = list(lignes)
    return pool, cur


class TestTentatives(unittest.TestCase):
    def setUp(self):
        tentatives._secours.clear()

    def test_ajouter_ecrit_en_base_et_retourne_le_compteur(self):
        pool, cur = faux_pool((3,))
        with patch.object(tentatives, "pool_central", pool):
            self.assertEqual(tentatives.ajouter("email:a@b.c"), 3)
        requete = cur.execute.call_args_list[0][0][0]
        self.assertIn("ON CONFLICT (cle)", requete)
        self.assertEqual(cur.execute.call_args_list[0][0][1][0], "email:a@b.c")
        pool.getconn.return_value.commit.assert_called_once()

    def test_etat_lit_les_echecs_actifs_et_le_temps_restant(self):
        pool, _ = faux_pool((4, 600))
        with patch.object(tentatives, "pool_central", pool):
            self.assertEqual(tentatives.etat("ip:1.1.1.1"), (4, 600))
        pool, _ = faux_pool(None)
        with patch.object(tentatives, "pool_central", pool):
            self.assertEqual(tentatives.etat("ip:1.1.1.1"), (0, 0))

    def test_base_indisponible_bascule_sur_la_memoire(self):
        casse = MagicMock()
        casse.getconn.side_effect = RuntimeError("base indisponible")
        with patch.object(tentatives, "pool_central", casse):
            self.assertEqual(tentatives.ajouter("k"), 1)
            self.assertEqual(tentatives.ajouter("k"), 2)
            self.assertEqual(tentatives.etat("k")[0], 2)
            tentatives.reinitialiser("k")
            self.assertEqual(tentatives.etat("k"), (0, 0))

    def test_memoire_de_secours_expire_apres_la_fenetre(self):
        casse = MagicMock()
        casse.getconn.side_effect = RuntimeError("x")
        with patch.object(tentatives, "pool_central", casse):
            tentatives.ajouter("k")
            with patch.object(tentatives.time, "time", return_value=tentatives.time.time() + tentatives.FENETRE_S + 5):
                self.assertEqual(tentatives.etat("k"), (0, 0))

    def test_reinitialiser_supprime_la_ligne(self):
        pool, cur = faux_pool()
        with patch.object(tentatives, "pool_central", pool):
            tentatives.reinitialiser("email:a@b.c")
        self.assertIn("DELETE FROM limite_tentative WHERE cle", cur.execute.call_args[0][0])

    def test_schema_idempotent_et_jamais_bloquant(self):
        sql = tentatives.FICHIER_SCHEMA.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS limite_tentative", sql)
        self.assertNotIn("DROP ", sql.upper())
        casse = MagicMock()
        casse.getconn.side_effect = RuntimeError("x")
        with patch.object(tentatives, "pool_central", casse):
            tentatives.assurer_schema()


class TestProtection(unittest.TestCase):
    def test_etat_protection_utilise_le_compteur_persistant(self):
        with patch.object(protection.tentatives, "etat", return_value=(1, 100)):
            self.assertEqual(protection.etat_protection("a@b.c"), {"echecs": 1, "protection_active": False})
        with patch.object(protection.tentatives, "etat", return_value=(2, 100)):
            self.assertEqual(protection.etat_protection("a@b.c"), {"echecs": 2, "protection_active": True})

    def test_un_echec_incremente_email_couple_email_ip_et_ip(self):
        jeton = protection.ip_courante.set("10.0.0.1")
        try:
            with patch.object(protection.tentatives, "ajouter") as ajouter:
                protection.enregistrer_echec("a@b.c")
            cles = [c[0][0] for c in ajouter.call_args_list]
            self.assertEqual(cles, ["email:a@b.c", "ei:a@b.c|10.0.0.1", "ip:10.0.0.1"])
        finally:
            protection.ip_courante.reset(jeton)

    def test_sans_ip_seul_le_compteur_email_est_incremente(self):
        with patch.object(protection.tentatives, "ajouter") as ajouter:
            protection.enregistrer_echec("a@b.c")
        self.assertEqual([c[0][0] for c in ajouter.call_args_list], ["email:a@b.c"])

    def test_reussite_remet_a_zero_email_et_couple_email_ip(self):
        jeton = protection.ip_courante.set("10.0.0.1")
        try:
            with patch.object(protection.tentatives, "reinitialiser") as raz:
                protection.reinitialiser_tentatives("a@b.c")
            self.assertEqual([c[0][0] for c in raz.call_args_list], ["email:a@b.c", "ei:a@b.c|10.0.0.1"])
        finally:
            protection.ip_courante.reset(jeton)

    def _verrou(self, etats, ip="10.0.0.1"):
        with patch.object(protection.tentatives, "etat", side_effect=lambda cle: etats.get(cle, (0, 0))):
            return protection.verrouillage("a@b.c", ip)

    def test_verrouillage_du_couple_email_ip(self):
        self.assertEqual(self._verrou({"ei:a@b.c|10.0.0.1": (protection.SEUIL_VERROU_EMAIL_IP, 420)}), 420)
        self.assertEqual(self._verrou({"ei:a@b.c|10.0.0.1": (protection.SEUIL_VERROU_EMAIL_IP - 1, 420)}), 0)

    def test_verrouillage_de_l_adresse_ip(self):
        self.assertEqual(self._verrou({"ip:10.0.0.1": (protection.SEUIL_VERROU_IP, 300)}), 300)
        self.assertEqual(self._verrou({"ip:10.0.0.1": (protection.SEUIL_VERROU_IP - 1, 300)}), 0)

    def test_un_autre_poste_n_est_pas_verrouille(self):
        etats = {"ei:a@b.c|10.0.0.1": (99, 420), "ip:10.0.0.1": (99, 420)}
        self.assertEqual(self._verrou(etats, ip="10.0.0.2"), 0)

    def test_sans_ip_pas_de_verrouillage(self):
        self.assertEqual(self._verrou({}, ip=None), 0)


class TestLogin(unittest.TestCase):
    def _requete(self):
        r = MagicMock()
        r.headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}
        r.client.host = "10.0.0.1"
        return r

    def test_compte_verrouille_recoit_429_avec_retry_after(self):
        charge = auth.LoginPayload(email="A@b.c", motDePasse="x")
        with patch.object(auth, "verrouillage", return_value=600), patch.object(auth, "journaliser") as journal, \
             patch.object(auth, "etat_protection", return_value={"echecs": 0, "protection_active": False}):
            rep = asyncio.run(auth.login(charge, self._requete()))
        self.assertEqual(rep.status_code, 429)
        self.assertEqual(rep.headers["retry-after"], "600")
        self.assertIn("10 minute", json.loads(rep.body)["message"])
        self.assertEqual(journal.call_args[0][0], "connexion_bloquee")

    def test_le_verrou_est_controle_avant_tout_le_reste(self):
        source = inspect.getsource(auth.login)
        self.assertLess(source.index("verrouillage"), source.index("verifier_et_consommer_captcha"))
        self.assertLess(source.index("verrouillage"), source.index("bcrypt") if "bcrypt" in source else 10**9)
        self.assertIn("ip_courante.set(", source)

    def test_demarrage_applique_le_schema(self):
        from app import main
        self.assertIn("assurer_schema_tentatives()", inspect.getsource(main.preparer_securite))


if __name__ == "__main__":
    unittest.main()
