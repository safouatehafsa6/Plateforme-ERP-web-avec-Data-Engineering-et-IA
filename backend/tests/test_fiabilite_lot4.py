"""Fiabilite et durcissement (Lot 4).

    python -m unittest tests.test_fiabilite_lot4 -v
"""
import inspect
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

import psycopg2
from psycopg2 import extensions, pool as pgpool
from pydantic import ValidationError

from app import db
from app.routers import auth, entreprises
from app.services import provisioning


class TestPoolParesseux(unittest.TestCase):
    def test_aucune_connexion_a_la_creation(self):
        with patch.object(db.pool, "ThreadedConnectionPool") as fabrique:
            db.PoolParesseux(5, host="h", dbname="d")
            fabrique.assert_not_called()

    def test_pool_cree_une_seule_fois_et_thread_safe(self):
        with patch.object(db.pool, "ThreadedConnectionPool") as fabrique:
            p = db.PoolParesseux(5, host="h", dbname="d")
            fabrique.return_value.getconn.return_value = MagicMock()
            fils = [threading.Thread(target=p.getconn) for _ in range(12)]
            [f.start() for f in fils]
            [f.join() for f in fils]
            self.assertEqual(fabrique.call_count, 1)

    def test_putconn_annule_une_transaction_ouverte(self):
        with patch.object(db.pool, "ThreadedConnectionPool") as fabrique:
            p = db.PoolParesseux(5, host="h", dbname="d")
            conn = MagicMock(closed=0, status=extensions.STATUS_IN_TRANSACTION)
            p.putconn(conn)
            conn.rollback.assert_called_once()
            fabrique.return_value.putconn.assert_called_once()

    def test_putconn_ne_touche_pas_une_connexion_propre(self):
        with patch.object(db.pool, "ThreadedConnectionPool"):
            p = db.PoolParesseux(5, host="h", dbname="d")
            conn = MagicMock(closed=0, status=extensions.STATUS_READY)
            p.putconn(conn)
            conn.rollback.assert_not_called()

    def test_attente_puis_succes_quand_le_pool_est_sature(self):
        with patch.object(db.pool, "ThreadedConnectionPool") as fabrique:
            conn = MagicMock()
            fabrique.return_value.getconn.side_effect = [pgpool.PoolError("pleine"), conn]
            p = db.PoolParesseux(1, attente_max=2, host="h", dbname="d")
            self.assertIs(p.getconn(), conn)

    def test_erreur_si_le_pool_reste_sature(self):
        with patch.object(db.pool, "ThreadedConnectionPool") as fabrique:
            fabrique.return_value.getconn.side_effect = pgpool.PoolError("pleine")
            p = db.PoolParesseux(1, attente_max=0.1, host="h", dbname="d")
            with self.assertRaises(pgpool.PoolError):
                p.getconn()

    def test_cache_des_pools_entreprise_sans_doublon(self):
        db._pools_entreprise.pop("base_test_lot4", None)
        try:
            resultats = []
            fils = [threading.Thread(target=lambda: resultats.append(db.get_pool_entreprise("base_test_lot4")))
                    for _ in range(10)]
            [f.start() for f in fils]
            [f.join() for f in fils]
            self.assertEqual(len({id(r) for r in resultats}), 1)
        finally:
            db._pools_entreprise.pop("base_test_lot4", None)


class TestMain(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app import main
        self.main = main
        self.client = TestClient(main.app)

    def test_origine_inconnue_refusee_et_origine_locale_acceptee(self):
        mauvais = self.client.get("/api/health", headers={"Origin": "http://evil.example"})
        self.assertNotIn("access-control-allow-origin", mauvais.headers)
        bon = self.client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(bon.headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_entetes_de_securite_presents(self):
        rep = self.client.get("/api/health")
        self.assertEqual(rep.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(rep.headers.get("referrer-policy"), "no-referrer")
        self.assertEqual(rep.headers.get("cache-control"), "no-store")

    def test_secret_jwt_obligatoire_et_assez_long(self):
        for valeur in (None, "", "court"):
            with self.subTest(valeur=valeur):
                env = {} if valeur is None else {"JWT_SECRET": valeur}
                with patch.dict(os.environ, env):
                    if valeur is None:
                        os.environ.pop("JWT_SECRET", None)
                    with self.assertRaises(RuntimeError):
                        self.main.verifier_configuration()
        with patch.dict(os.environ, {"JWT_SECRET": "x" * 40}):
            self.main.verifier_configuration()

    def test_index_des_sessions_cree_et_jamais_bloquant(self):
        pool = MagicMock()
        with patch.object(self.main, "pool_central", pool):
            self.main.assurer_index_sessions()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        self.assertIn("idx_session_utilisateur_expire", cur.execute.call_args[0][0])
        casse = MagicMock()
        casse.getconn.side_effect = RuntimeError("base indisponible")
        with patch.object(self.main, "pool_central", casse):
            self.main.assurer_index_sessions()  # ne leve rien


class TestAuth(unittest.TestCase):
    def test_login_ne_bloque_plus_le_serveur(self):
        source = inspect.getsource(auth.login)
        self.assertNotIn("bcrypt.checkpw(", source)
        self.assertEqual(source.count("run_in_threadpool("), 4)  # 3 profils + faux hash

    def test_captcha_jamais_affiche_par_defaut(self):
        with patch.dict(os.environ, {}), patch("builtins.print") as imprimer:
            os.environ.pop("ENV", None)
            auth.obtenir_captcha()
            imprimer.assert_not_called()
        with patch.dict(os.environ, {"ENV": "dev"}), patch("builtins.print") as imprimer:
            auth.obtenir_captcha()
            imprimer.assert_called_once()

    def test_longueurs_maximales_du_login(self):
        with self.assertRaises(ValidationError):
            auth.LoginPayload(email="a" * 151, motDePasse="x")
        with self.assertRaises(ValidationError):
            auth.LoginPayload(email="a@b.c", motDePasse="x" * 73)
        auth.LoginPayload(email="a@b.c", motDePasse="x" * 72)


class TestInscriptionBornee(unittest.TestCase):
    CORPS = dict(typeCompte="personne_physique", nomAdmin="Ali Test", email="a@b.co",
                 emailConfirmation="a@b.co", motDePasse="Abcdef1!", motDePasseConfirmation="Abcdef1!",
                 cguAccepte=True, captchaId="x", captchaValeur="y")

    def test_champs_trop_longs_refuses(self):
        entreprises.InscriptionPayload(**self.CORPS)
        for champ, taille in (("nomAdmin", 151), ("email", 151), ("telephone", 31),
                              ("motDePasse", 73), ("nomEntreprise", 151), ("secteur", 101)):
            with self.subTest(champ=champ):
                with self.assertRaises(ValidationError):
                    entreprises.InscriptionPayload(**{**self.CORPS, champ: "x" * taille})

    def test_mot_de_passe_depassant_72_octets_refuse(self):
        charge = entreprises.InscriptionPayload(**{**self.CORPS, "motDePasse": "é" * 40 + "1!",
                                                   "motDePasseConfirmation": "é" * 40 + "1!"})
        trop_long = entreprises._erreurs_validation_inscription(charge)
        ok = entreprises._erreurs_validation_inscription(entreprises.InscriptionPayload(
            **{**self.CORPS, "motDePasse": "a" * 40 + "1!", "motDePasseConfirmation": "a" * 40 + "1!"}))
        self.assertGreater(len(trop_long), len(ok))

    def test_kyc_refuse_un_document_inattendu(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        pool = MagicMock()
        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = ("personne_physique", "en_attente")
        app = FastAPI()
        app.include_router(entreprises.router)
        with patch.dict(os.environ, {"ONBOARDING_AUTO_VALIDATION": "1"}), \
             patch.object(entreprises, "pool_central", pool), \
             patch.object(entreprises, "_valider_dossier"):
            rep = TestClient(app).post("/api/entreprises/kyc", json={
                "entrepriseId": 1,
                "documents": {**{d: "ok.pdf" for d in entreprises.DOCUMENTS_REQUIS["personne_physique"]},
                              "intrus": "intrus.pdf"}})
        self.assertEqual(rep.status_code, 400)


class TestProvisioningRejouable(unittest.TestCase):
    def _lancer(self, schema, admin):
        appels = []
        def enreg(nom):
            return lambda *a, **k: appels.append(nom)
        with patch.object(provisioning, "creer_base_entreprise", enreg("base")), \
             patch.object(provisioning, "_schema_existe", return_value=schema), \
             patch.object(provisioning, "_admin_existe", return_value=admin), \
             patch.object(provisioning, "initialiser_schema_entreprise", enreg("schema")), \
             patch.object(provisioning, "creer_administrateur_entreprise", enreg("admin")), \
             patch.object(provisioning, "appliquer_seed_rbac", enreg("seed")), \
             patch.object(provisioning, "indexer_compte_central", enreg("index")):
            provisioning.provisionner_entreprise("compte_x", "Ali Test", "a@b.co", "hash", 1)
        return appels

    def test_premiere_tentative_execute_toutes_les_etapes(self):
        self.assertEqual(self._lancer(False, False), ["base", "schema", "admin", "seed", "index"])

    def test_reprise_apres_echec_saute_ce_qui_existe(self):
        self.assertEqual(self._lancer(True, True), ["base", "seed", "index"])
        self.assertEqual(self._lancer(True, False), ["base", "admin", "seed", "index"])

    def test_creation_de_base_ignoree_si_elle_existe(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (1,)
        with patch.object(provisioning, "_connexion_maintenance", return_value=conn):
            provisioning.creer_base_entreprise("compte_x")
        self.assertEqual(cur.execute.call_count, 1)  # le SELECT seulement

    def test_creation_de_base_utilise_un_identifiant_protege(self):
        from psycopg2 import sql
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None
        with patch.object(provisioning, "_connexion_maintenance", return_value=conn):
            provisioning.creer_base_entreprise('compte_x"; DROP DATABASE erp_db; --')
        requete = cur.execute.call_args[0][0]
        self.assertIsInstance(requete, sql.Composed)


if __name__ == "__main__":
    unittest.main()
