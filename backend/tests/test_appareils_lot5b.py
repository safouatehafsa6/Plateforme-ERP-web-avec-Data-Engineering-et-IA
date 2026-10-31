"""Gestion avancee des appareils (Lot 5b).

    python -m unittest tests.test_appareils_lot5b -v
"""
import asyncio
import inspect
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import appareils as routeur
from app.security import appareils as svc
from app.security import sessions as sessions_mod

INFO = {"systeme": "Windows", "navigateur": "Chrome", "appareil": "ordinateur"}
CLAIMS = {"id": 3, "email": "a@test.local", "type": "interne", "entrepriseId": 7}
ID_VALIDE = "0123456789abcdef-0123456789abcdef"


def requete(id_appareil=None, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120"):
    entetes = {"user-agent": ua}
    if id_appareil is not None:
        entetes["x-appareil-id"] = id_appareil
    r = MagicMock()
    r.headers = entetes
    return r


def faux_pool(*lignes, rowcount=2):
    pool = MagicMock()
    cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = list(lignes)
    cur.rowcount = rowcount
    return pool, cur


class TestEmpreinte(unittest.TestCase):
    def test_empreinte_stable_et_sans_identifiant_en_clair(self):
        a = svc.empreinte(requete(ID_VALIDE))
        self.assertEqual(a, svc.empreinte(requete(ID_VALIDE)))
        self.assertEqual(len(a), 64)
        self.assertNotIn(ID_VALIDE, a)

    def test_deux_navigateurs_deux_empreintes(self):
        self.assertNotEqual(svc.empreinte(requete(ID_VALIDE)), svc.empreinte(requete("f" * 32)))

    def test_identifiant_invalide_ou_absent_retombe_sur_le_user_agent(self):
        sans = svc.empreinte(requete(None))
        for faux in ("court", "x" * 80, "avec espace et <script>", ""):
            with self.subTest(faux=faux):
                self.assertEqual(svc.empreinte(requete(faux)), sans)
        self.assertNotEqual(sans, svc.empreinte(requete(None, ua="Autre navigateur")))


class TestEnregistrerConnexion(unittest.TestCase):
    def _lancer(self, existant, ligne, claims=CLAIMS, strict=False):
        pool, cur = faux_pool((existant,), ligne)
        env = {"APPAREILS_MODE_STRICT": "1" if strict else "0"}
        with patch.object(svc, "pool_central", pool), patch.object(svc, "journaliser") as journal, \
             patch.dict(os.environ, env):
            try:
                res = svc.enregistrer_connexion(claims, requete(ID_VALIDE), INFO, "10.0.0.1")
                erreur = None
            except svc.AppareilRefuse as e:
                res, erreur = None, e
        insert = [c for c in cur.execute.call_args_list if "INSERT INTO appareil" in c[0][0]][0]
        return res, erreur, journal, insert[0][1]

    def test_premier_appareil_autorise_et_pas_considere_nouveau(self):
        res, erreur, journal, params = self._lancer(False, (5, "autorise", True))
        self.assertEqual(res, {"id": 5, "nouveau": False})
        self.assertIsNone(erreur)
        self.assertEqual(params[-1], "autorise")

    def test_deuxieme_appareil_est_signale_nouveau(self):
        res, _, _, _ = self._lancer(True, (6, "autorise", True))
        self.assertEqual(res, {"id": 6, "nouveau": True})

    def test_appareil_deja_connu_n_est_pas_nouveau(self):
        res, _, _, _ = self._lancer(True, (6, "autorise", False))
        self.assertFalse(res["nouveau"])

    def test_appareil_bloque_refuse_et_journalise(self):
        res, erreur, journal, _ = self._lancer(True, (6, "bloque", False))
        self.assertIsNone(res)
        self.assertIn("bloqu", erreur.message)
        self.assertEqual(journal.call_args[0][0], "connexion_refusee")
        self.assertEqual(journal.call_args[1]["details"], {"raison": "appareil_bloque"})

    def test_appareil_en_attente_refuse(self):
        res, erreur, journal, _ = self._lancer(True, (6, "en_attente", True), strict=True)
        self.assertIsNone(res)
        self.assertIn("autoris", erreur.message)
        self.assertEqual(journal.call_args[0][0], "appareil_en_attente")

    def test_mode_strict_met_le_nouvel_appareil_en_attente(self):
        _, _, _, params = self._lancer(True, (6, "en_attente", True), strict=True)
        self.assertEqual(params[-1], "en_attente")

    def test_mode_strict_n_affecte_ni_le_premier_appareil_ni_le_super_admin(self):
        _, _, _, params = self._lancer(False, (5, "autorise", True), strict=True)
        self.assertEqual(params[-1], "autorise")
        admin = {"id": 1, "email": "root@test.local", "type": "plateforme"}
        _, _, _, params = self._lancer(True, (5, "autorise", True), claims=admin, strict=True)
        self.assertEqual(params[-1], "autorise")

    def test_l_identifiant_est_stocke_sous_forme_d_empreinte(self):
        _, _, _, params = self._lancer(False, (5, "autorise", True))
        self.assertIn(svc.empreinte(requete(ID_VALIDE)), params)
        self.assertNotIn(ID_VALIDE, params)

    def test_entreprise_dans_la_cle_d_appareil(self):
        _, _, _, params = self._lancer(False, (5, "autorise", True))
        self.assertEqual(params[:3], ("interne", "3", "7"))


class TestAgir(unittest.TestCase):
    def _agir(self, action, statut="autorise", courant=99, trouve=True, appareil_id=5):
        ligne = (appareil_id, statut, "cible@test.local") if trouve else None
        pool, cur = faux_pool(ligne, rowcount=2)
        with patch.object(svc, "pool_central", pool):
            try:
                res = svc.agir(action, appareil_id, svc.portee_compte(CLAIMS), courant, "a@test.local")
                erreur = None
            except (svc.AppareilIntrouvable, svc.ActionInterdite) as e:
                res, erreur = None, e
        requetes = [(c[0][0], c[0][1] if len(c[0]) > 1 else None) for c in cur.execute.call_args_list]
        return res, erreur, requetes

    def test_bloquer_change_le_statut_et_ferme_les_sessions(self):
        res, erreur, req = self._agir("bloquer")
        self.assertIsNone(erreur)
        self.assertEqual(res["sessionsFermees"], 2)
        maj = [p for q, p in req if q.startswith("UPDATE appareil")][0]
        self.assertEqual(maj[0], "bloque")
        rev = [p for q, p in req if "UPDATE session_utilisateur" in q][0]
        self.assertEqual(rev, ("appareil_bloque", 5))

    def test_reactiver_et_autoriser_ne_ferment_aucune_session(self):
        for action, statut in (("reactiver", "bloque"), ("autoriser", "en_attente")):
            with self.subTest(action=action):
                res, erreur, req = self._agir(action, statut=statut)
                self.assertIsNone(erreur)
                self.assertEqual(res["sessionsFermees"], 0)
                self.assertFalse(any("session_utilisateur" in q for q, _ in req))
                self.assertEqual([p for q, p in req if q.startswith("UPDATE appareil")][0][0], "autorise")

    def test_conditions_sur_le_statut(self):
        self.assertIsInstance(self._agir("autoriser", statut="autorise")[1], svc.ActionInterdite)
        self.assertIsInstance(self._agir("reactiver", statut="autorise")[1], svc.ActionInterdite)

    def test_deconnecter_garde_l_appareil_et_ferme_les_sessions(self):
        res, _, req = self._agir("deconnecter")
        self.assertEqual(res["sessionsFermees"], 2)
        self.assertFalse(any(q.startswith("UPDATE appareil") or q.startswith("DELETE") for q, _ in req))
        self.assertEqual([p for q, p in req if "UPDATE session_utilisateur" in q][0][0], "deconnexion_distance")

    def test_supprimer_ferme_les_sessions_puis_efface(self):
        _, _, req = self._agir("supprimer")
        ordre = [q for q, _ in req]
        i_rev = next(i for i, q in enumerate(ordre) if "UPDATE session_utilisateur" in q)
        i_del = next(i for i, q in enumerate(ordre) if q.startswith("DELETE FROM appareil"))
        self.assertLess(i_rev, i_del)

    def test_impossible_d_agir_sur_l_appareil_utilise(self):
        for action in ("bloquer", "deconnecter", "supprimer"):
            with self.subTest(action=action):
                _, erreur, req = self._agir(action, courant=5, appareil_id=5)
                self.assertIsInstance(erreur, svc.ActionInterdite)
                self.assertFalse(any(q.startswith(("UPDATE", "DELETE")) for q, _ in req))

    def test_appareil_hors_portee_est_introuvable(self):
        _, erreur, req = self._agir("bloquer", trouve=False)
        self.assertIsInstance(erreur, svc.AppareilIntrouvable)
        self.assertFalse(any(q.startswith(("UPDATE", "DELETE")) for q, _ in req))

    def test_la_portee_est_dans_la_requete_de_selection(self):
        _, _, req = self._agir("bloquer")
        select, params = req[0]
        self.assertIn("a.utilisateur_id = %s", select)
        self.assertIn("a.entreprise_id IS NOT DISTINCT FROM %s", select)
        self.assertEqual(params, (5, "interne", "3", "7"))

    def test_action_inconnue(self):
        self.assertIsInstance(self._agir("exploser")[1], svc.ActionInterdite)

    def test_portee_entreprise_filtre_sur_l_entreprise_du_jeton(self):
        clause, params = svc.portee_entreprise({"entrepriseId": 7})
        self.assertEqual(clause, "a.entreprise_id = %s")
        self.assertEqual(params, ("7",))


class TestLister(unittest.TestCase):
    def test_format_de_liste(self):
        maintenant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ligne = (5, "a@test.local", "interne", "3", "Chrome sur Windows", "Windows", "Chrome",
                 "ordinateur", "10.0.0.1", "autorise", maintenant, maintenant, 2)
        pool = MagicMock()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [ligne]
        with patch.object(svc, "pool_central", pool):
            res = svc.lister(svc.portee_compte(CLAIMS), 5)
        self.assertEqual(res[0]["statut"], "autorise")
        self.assertTrue(res[0]["courant"])
        self.assertEqual(res[0]["sessionsActives"], 2)
        self.assertNotIn("empreinte", json.dumps(res))


class TestRoutes(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routeur.router)
        app.include_router(routeur.router_admin)
        self.client = TestClient(app)

    def test_toutes_les_routes_exigent_une_authentification(self):
        appels = [
            ("get", "/api/appareils"), ("post", "/api/appareils/1/bloquer"),
            ("delete", "/api/appareils/1"), ("get", "/api/admin/appareils"),
            ("post", "/api/admin/appareils/1/bloquer"), ("delete", "/api/admin/appareils/1"),
        ]
        for methode, chemin in appels:
            with self.subTest(chemin=chemin, methode=methode):
                self.assertIn(getattr(self.client, methode)(chemin).status_code, (401, 403))

    def _executer(self, action, erreur=None, admin=False):
        acteur = {"id": 3, "email": "a@test.local", "type": "interne", "entrepriseId": 7, "jti": "j1"}
        with patch.object(routeur.svc, "appareil_courant", return_value=99), \
             patch.object(routeur, "journaliser") as journal, \
             patch.object(routeur.svc, "agir", side_effect=erreur,
                          return_value={"email": "cible@test.local", "sessionsFermees": 2}) as agir:
            try:
                rep = routeur._executer(action, 5, ("clause", ()), acteur, None, admin)
            except Exception as e:  # HTTPException
                rep = e
        return rep, journal, agir

    def test_action_reussie_est_journalisee(self):
        rep, journal, _ = self._executer("bloquer")
        self.assertEqual(rep["sessionsFermees"], 2)
        self.assertEqual(journal.call_args[0][0], "appareil_bloque")
        self.assertEqual(journal.call_args[1]["gravite"], "avertissement")

    def test_action_admin_trace_l_acteur_et_la_cible(self):
        _, journal, _ = self._executer("bloquer", admin=True)
        self.assertEqual(journal.call_args[1]["acteur_email"], "a@test.local")
        self.assertEqual(journal.call_args[1]["email"], "cible@test.local")

    def test_erreurs_traduites_en_http(self):
        rep, journal, _ = self._executer("bloquer", erreur=svc.AppareilIntrouvable())
        self.assertEqual(rep.status_code, 404)
        journal.assert_not_called()
        rep, _, _ = self._executer("bloquer", erreur=svc.ActionInterdite("non"))
        self.assertEqual(rep.status_code, 400)


class TestIntegration(unittest.TestCase):
    def test_la_connexion_enregistre_l_appareil_et_le_lie_a_la_session(self):
        source = inspect.getsource(sessions_mod.emettre_jeton)
        self.assertIn("enregistrer_connexion(", source)
        self.assertIn("appareil_id", source)
        self.assertLess(source.index("enregistrer_connexion("), source.index("INSERT INTO session_utilisateur"))
        self.assertIn("nouvel_appareil", source)

    def test_refus_d_appareil_renvoye_en_403_avec_message(self):
        from app import main
        gestionnaire = main.app.exception_handlers[svc.AppareilRefuse]
        rep = asyncio.run(gestionnaire(None, svc.AppareilRefuse("Appareil bloqué.")))
        self.assertEqual(rep.status_code, 403)
        self.assertEqual(json.loads(rep.body)["message"], "Appareil bloqué.")

    def test_routes_branchees_et_schema_applique_au_demarrage(self):
        from app import main
        chemins = {r.path for r in main.app.routes}
        self.assertIn("/api/appareils", chemins)
        self.assertIn("/api/admin/appareils", chemins)
        self.assertIn("assurer_schema_appareils()", inspect.getsource(main.preparer_securite))

    def test_fichier_de_schema_present_et_idempotent(self):
        sql = svc.FICHIER_SCHEMA.read_text(encoding="utf-8")
        self.assertTrue(svc.FICHIER_SCHEMA.exists())
        self.assertIn("CREATE TABLE IF NOT EXISTS appareil", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS appareil_id", sql)
        self.assertNotIn("DROP ", sql.upper())

    def test_assurer_schema_execute_le_fichier_et_ne_bloque_jamais(self):
        pool = MagicMock()
        with patch.object(svc, "pool_central", pool):
            svc.assurer_schema()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        self.assertIn("CREATE TABLE IF NOT EXISTS appareil", cur.execute.call_args[0][0])
        casse = MagicMock()
        casse.getconn.side_effect = RuntimeError("base indisponible")
        with patch.object(svc, "pool_central", casse):
            svc.assurer_schema()  # ne leve rien


if __name__ == "__main__":
    unittest.main()
