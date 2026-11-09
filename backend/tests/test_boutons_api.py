"""Tests d'intégration des boutons flottants contre un vrai PostgreSQL (base centrale TEMPORAIRE).

La base centrale réelle n'est jamais touchée : le routeur est branché sur une base créée pour le test
puis supprimée. Sans PostgreSQL joignable (variables DB_*), les tests sont ignorés.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_TEST = f"erp_test_boutons_{os.getpid()}"
_ctx = {}
SQL = Path(__file__).resolve().parents[1] / "database" / "central" / "015_boutons_flottants.sql"


def setUpModule():
    os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef0123")
    try:
        import psycopg2
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        from psycopg2.pool import SimpleConnectionPool

        from app.db import pool_central  # noqa: F401
        from app.routers import boutons_flottants as module
        from app.security.jwt_utils import exiger_super_admin

        params = dict(host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
                      user=os.getenv("DB_USER", "erp_user"), password=os.getenv("DB_PASSWORD", "erp_password"))
        admin = psycopg2.connect(dbname=os.getenv("DB_CENTRAL_NAME", "erp_db"), **params)
    except Exception as exc:
        raise unittest.SkipTest(f"Environnement d'intégration indisponible : {exc}")

    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{BASE_TEST}"')
    admin.close()
    direct = psycopg2.connect(dbname=BASE_TEST, **params)
    direct.autocommit = True
    cur = direct.cursor()
    cur.execute(SQL.read_text(encoding="utf-8"))

    pool = SimpleConnectionPool(1, 4, dbname=BASE_TEST, **params)
    _ctx["original_pool"] = module.pool_central
    module.pool_central = pool
    module._pret = False
    module._vider_cache()

    identite = {"courant": "super"}

    def faux_super_admin():
        if identite["courant"] != "super":
            raise HTTPException(status_code=403, detail="Accès réservé au Super Administrateur.")
        return {"type": "plateforme", "role": "super_admin", "id": 1, "email": "root@plateforme.tn"}

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[exiger_super_admin] = faux_super_admin
    _ctx.update(client=TestClient(app), cur=cur, direct=direct, pool=pool, module=module, identite=identite, params=params)


def tearDownModule():
    if not _ctx:
        return
    import psycopg2
    _ctx["module"].pool_central = _ctx["original_pool"]
    _ctx["module"]._pret = False
    _ctx["module"]._vider_cache()
    _ctx["pool"].closeall()
    _ctx["direct"].close()
    conn = psycopg2.connect(dbname=os.getenv("DB_CENTRAL_NAME", "erp_db"), **_ctx["params"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)')
    conn.close()


def corps(**extra):
    base = {"titres": {"fr": "Offre spéciale", "en": "Special offer"}, "icone": "gift", "action": "route", "cible": "/tarifs"}
    base.update(extra)
    return base


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.http = _ctx["client"]
        self.cur = _ctx["cur"]
        _ctx["identite"]["courant"] = "super"
        _ctx["module"]._vider_cache()

    def publics(self):
        _ctx["module"]._vider_cache()
        return self.http.get("/api/boutons-flottants").json()

    def creer(self, **extra):
        r = self.http.post("/api/admin/boutons-flottants", json=corps(**extra))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["bouton"]

    def cles_publiques(self):
        return [b["cle"] for b in self.publics()["boutons"]]


class AffichagePublicTests(ApiCase):
    def test_boutons_d_origine_sans_authentification(self):
        _ctx["identite"]["courant"] = "visiteur"          # la lecture reste publique
        d = self.publics()
        for cle in ("notifications", "assistant", "support", "whatsapp", "connexion", "inscription", "theme", "langue"):
            self.assertIn(cle, [b["cle"] for b in d["boutons"]])
        self.assertEqual(d["config"]["position"], "auto")
        self.assertTrue(all(b["systeme"] for b in d["boutons"] if b["cle"] in ("support", "theme")))
        ordres = [b["ordre"] for b in d["boutons"]]
        self.assertEqual(ordres, sorted(ordres))

    def test_bouton_cree_visible_immediatement(self):
        b = self.creer(titres={"fr": "Promo visible"})
        self.assertEqual(b["cle"], "promo-visible")
        self.assertIn("promo-visible", self.cles_publiques())

    def test_bouton_desactive_ou_hors_periode_non_diffuse(self):
        a = self.creer(titres={"fr": "Desactive"}, actif=False)
        passe = self.creer(titres={"fr": "Expire"}, affiche_jusqu_au=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                           affiche_du=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat())
        futur = self.creer(titres={"fr": "A venir"}, affiche_du=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat())
        en_cours = self.creer(titres={"fr": "En cours"}, affiche_du=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                              affiche_jusqu_au=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        publiques = self.cles_publiques()
        for b in (a, passe, futur):
            self.assertNotIn(b["cle"], publiques)
        self.assertIn(en_cours["cle"], publiques)
        tous = [x["cle"] for x in self.http.get("/api/admin/boutons-flottants").json()["boutons"]]
        for b in (a, passe, futur, en_cours):
            self.assertIn(b["cle"], tous, "l'administrateur voit aussi les boutons non diffusés")


class DroitsTests(ApiCase):
    def test_ecriture_reservee_au_super_admin(self):
        b = self.creer(titres={"fr": "Protege"})
        _ctx["identite"]["courant"] = "autre"
        base = "/api/admin/boutons-flottants"
        appels = [
            self.http.get(base), self.http.post(base, json=corps()), self.http.put(f"{base}/{b['id']}", json=corps()),
            self.http.delete(f"{base}/{b['id']}"), self.http.patch(f"{base}/{b['id']}/actif", json={"actif": False}),
            self.http.put(f"{base}/ordre", json={"ids": [b["id"]]}), self.http.put(f"{base}/config", json={}),
            self.http.post(f"{base}/restaurer"), self.http.get(f"{base}/historique"),
        ]
        self.assertEqual([r.status_code for r in appels], [403] * len(appels))
        self.assertIn("protege", self.cles_publiques(), "rien n'a été modifié")


class ValidationApiTests(ApiCase):
    def test_entrees_dangereuses_refusees(self):
        mauvaises = [
            dict(action="url", cible="javascript:alert(1)"), dict(action="url", cible="http://exemple.tn"),
            dict(action="route", cible="//evil.tn"), dict(action="route", cible="/../secret"),
            dict(couleur="red"), dict(icone="skull"), dict(titres={"en": "x"}), dict(placement="libre"),
            dict(audience="public", profils=["interne"]), dict(action="support", cible="/x"),
            dict(action="whatsapp", cible="abc"), dict(taille="geant"), dict(ordre=-5),
        ]
        for extra in mauvaises:
            r = self.http.post("/api/admin/boutons-flottants", json=corps(**extra))
            self.assertEqual(r.status_code, 422, f"{extra} -> {r.status_code}")

    def test_contraintes_en_base_en_dernier_rempart(self):
        import psycopg2
        for colonne, valeur in (("action", "eval"), ("couleur", "red"), ("audience", "vip"), ("taille", "xl")):
            champs = {"cle": f"direct-{colonne}", "titres": '{"fr":"x"}', "icone": "bell", "action": "support"}
            champs[colonne] = valeur
            with self.assertRaises(psycopg2.errors.CheckViolation, msg=colonne):
                self.cur.execute("INSERT INTO bouton_flottant (cle, titres, icone, action, couleur, audience, taille) "
                                 "VALUES (%(cle)s, %(titres)s, %(icone)s, %(action)s, %(couleur)s, %(audience)s, %(taille)s)",
                                 {"couleur": None, "audience": "tous", "taille": "moyen", **champs})

    def test_texte_hostile_stocke_tel_quel(self):
        b = self.creer(titres={"fr": "'; DROP TABLE bouton_flottant; --"})
        self.assertEqual(b["titres"]["fr"], "'; DROP TABLE bouton_flottant; --")
        self.cur.execute("SELECT COUNT(*) FROM bouton_flottant")
        self.assertGreater(self.cur.fetchone()[0], 8)

    def test_whatsapp_normalise(self):
        b = self.creer(titres={"fr": "Wa perso"}, action="whatsapp", cible="+216 12 345 678", nouvel_onglet=True)
        self.assertEqual(b["cible"], "21612345678")


class CrudTests(ApiCase):
    def test_identifiants_uniques(self):
        a = self.creer(titres={"fr": "Doublon titre"})
        b = self.creer(titres={"fr": "Doublon titre"})
        self.assertNotEqual(a["cle"], b["cle"])
        r = self.http.post("/api/admin/boutons-flottants", json=corps(cle=a["cle"]))
        self.assertEqual(r.status_code, 409)

    def test_modification_et_historique(self):
        b = self.creer(titres={"fr": "A modifier"})
        r = self.http.put(f"/api/admin/boutons-flottants/{b['id']}", json=corps(titres={"fr": "Modifie"}, couleur="#112233", ordre=5))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["bouton"]["titres"]["fr"], r.json()["bouton"]["couleur"], r.json()["bouton"]["cle"]), ("Modifie", "#112233", b["cle"]))
        h = self.http.get("/api/admin/boutons-flottants/historique").json()["historique"]
        self.assertEqual((h[0]["operation"], h[0]["cle"], h[0]["par_email"]), ("modification", b["cle"], "root@plateforme.tn"))
        self.assertIn("couleur", h[0]["details"]["champs"])
        self.assertEqual(self.http.put("/api/admin/boutons-flottants/999999", json=corps()).status_code, 404)

    def test_activation_rapide(self):
        b = self.creer(titres={"fr": "Bascule"})
        self.assertEqual(self.http.patch(f"/api/admin/boutons-flottants/{b['id']}/actif", json={"actif": False}).status_code, 200)
        self.assertNotIn(b["cle"], self.cles_publiques())
        self.http.patch(f"/api/admin/boutons-flottants/{b['id']}/actif", json={"actif": True})
        self.assertIn(b["cle"], self.cles_publiques())

    def test_suppression_bouton_ajoute_mais_pas_bouton_d_origine(self):
        b = self.creer(titres={"fr": "Jetable"})
        self.assertEqual(self.http.delete(f"/api/admin/boutons-flottants/{b['id']}").status_code, 200)
        self.assertNotIn(b["cle"], self.cles_publiques())
        self.assertEqual(self.http.delete(f"/api/admin/boutons-flottants/{b['id']}").status_code, 404)
        support = next(x for x in self.http.get("/api/admin/boutons-flottants").json()["boutons"] if x["cle"] == "support")
        r = self.http.delete(f"/api/admin/boutons-flottants/{support['id']}")
        self.assertEqual(r.status_code, 409)
        self.assertIn("support", self.cles_publiques())

    def test_ordre(self):
        tous = self.http.get("/api/admin/boutons-flottants").json()["boutons"]
        ids = [b["id"] for b in tous]
        inverse = list(reversed(ids))
        self.assertEqual(self.http.put("/api/admin/boutons-flottants/ordre", json={"ids": inverse}).status_code, 200)
        self.assertEqual([b["id"] for b in self.http.get("/api/admin/boutons-flottants").json()["boutons"]], inverse)
        self.assertEqual(self.http.put("/api/admin/boutons-flottants/ordre", json={"ids": [ids[0], 999999]}).status_code, 404)
        self.assertEqual(self.http.put("/api/admin/boutons-flottants/ordre", json={"ids": [ids[0], ids[0]]}).status_code, 422)
        self.http.put("/api/admin/boutons-flottants/ordre", json={"ids": ids})


class ConfigEtRestaurationTests(ApiCase):
    def test_config_globale_et_version(self):
        v0 = self.publics()["version"]
        r = self.http.put("/api/admin/boutons-flottants/config", json={"actif": True, "position": "haut-gauche", "taille": "grand", "couleur": "#AA0000", "icone": "star"})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.publics()
        self.assertEqual((d["config"]["position"], d["config"]["taille"], d["config"]["couleur"], d["config"]["icone"]), ("haut-gauche", "grand", "#aa0000", "star"))
        self.assertGreater(d["version"], v0)
        for mauvais in ({"position": "plafond"}, {"taille": "xxl"}, {"couleur": "bleu"}, {"icone": "skull"}):
            self.assertEqual(self.http.put("/api/admin/boutons-flottants/config", json=mauvais).status_code, 422)
        self.http.put("/api/admin/boutons-flottants/config", json={})

    def test_restauration_des_boutons_d_origine(self):
        custom = self.creer(titres={"fr": "Reste apres restauration"})
        support = next(x for x in self.http.get("/api/admin/boutons-flottants").json()["boutons"] if x["cle"] == "support")
        self.http.put(f"/api/admin/boutons-flottants/{support['id']}", json=corps(titres={"fr": "Aide perso"}, icone="star", action="support", cible=None, actif=False, couleur="#ff0000"))
        self.http.put("/api/admin/boutons-flottants/config", json={"position": "bas-gauche"})
        self.assertNotIn("support", self.cles_publiques())
        r = self.http.post("/api/admin/boutons-flottants/restaurer")
        self.assertEqual(r.status_code, 200, r.text)
        d = self.publics()
        retabli = next(b for b in d["boutons"] if b["cle"] == "support")
        self.assertEqual((retabli["titres"]["fr"], retabli["icone"], retabli["couleur"], retabli["actif"]), ("Assistance / Contact", "headset", None, True))
        self.assertEqual(d["config"]["position"], "auto")
        self.assertIn(custom["cle"], [b["cle"] for b in d["boutons"]], "les boutons ajoutés sont conservés")
        self.assertEqual(self.http.get("/api/admin/boutons-flottants/historique").json()["historique"][0]["operation"], "restauration")


if __name__ == "__main__":
    unittest.main()
