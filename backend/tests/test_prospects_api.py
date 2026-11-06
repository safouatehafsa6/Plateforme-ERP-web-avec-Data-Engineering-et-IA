"""Tests d'intégration du module Prospects contre un vrai PostgreSQL.

Prérequis : un PostgreSQL joignable avec les variables DB_HOST / DB_PORT / DB_USER / DB_PASSWORD /
DB_CENTRAL_NAME (mêmes valeurs que l'application) et un utilisateur pouvant créer des bases.
Sans base disponible, les tests sont ignorés (skip). Une base temporaire est créée puis supprimée.

    python -m unittest tests.test_prospects_api -v
"""
import os
import random
import string
import unittest
from datetime import datetime, timedelta, timezone

BASE_TEST = f"erp_test_prospects_{os.getpid()}"
_ctx = {}


def setUpModule():
    os.environ.setdefault("JWT_SECRET", "test-secret")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.db import pool_central  # noqa: F401  (échoue si la base centrale est injoignable)
        from app.security import auth_dependency
        from app.services import provisioning
        from app.routers import clients, prospects
    except Exception as exc:  # pas de base / dépendances manquantes
        raise unittest.SkipTest(f"Environnement d'intégration indisponible : {exc}")

    import psycopg2

    conn = provisioning._connexion_maintenance()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)')
    finally:
        conn.close()
    provisioning.creer_base_entreprise(BASE_TEST)
    provisioning.initialiser_schema_entreprise(BASE_TEST)
    provisioning.creer_administrateur_entreprise(BASE_TEST, "Alice Admin", "admin@acme.tn", "hash")
    provisioning.appliquer_seed_rbac(BASE_TEST)

    db = psycopg2.connect(host=provisioning.DB_HOST, port=provisioning.DB_PORT, user=provisioning.DB_USER,
                          password=provisioning.DB_PASSWORD, dbname=BASE_TEST)
    db.autocommit = True
    cur = db.cursor()

    def creer_role(nom, droits):
        cur.execute("INSERT INTO role (nom) VALUES (%s) ON CONFLICT (nom) DO NOTHING", (nom,))
        for module, action in droits:
            cur.execute(
                """INSERT INTO role_permission (role_id, permission_id)
                   SELECT r.id, p.id FROM role r, permission p
                   WHERE r.nom = %s AND p.module = %s AND p.action = %s ON CONFLICT DO NOTHING""",
                (nom, module, action),
            )

    creer_role("Lecteur", [("prospects", "consulter"), ("clients", "consulter")])
    creer_role("Modificateur", [("prospects", "consulter"), ("prospects", "modifier"), ("clients", "consulter")])
    creer_role("Aucun", [])

    def creer_user(email, prenom, nom, role):
        cur.execute(
            "INSERT INTO utilisateur (nom, prenom, email, mot_de_passe, role_id) "
            "VALUES (%s, %s, %s, 'x', (SELECT id FROM role WHERE nom = %s)) ON CONFLICT (email) DO UPDATE SET nom = EXCLUDED.nom "
            "RETURNING id", (nom, prenom, email, role))
        return cur.fetchone()[0]

    cur.execute("SELECT id FROM utilisateur WHERE email = 'admin@acme.tn'")
    ids = {"admin": cur.fetchone()[0]}
    ids["commercial"] = creer_user("com@acme.tn", "Sami", "Commercial", "Responsable Commercial")
    ids["lecteur"] = creer_user("lec@acme.tn", "Lina", "Lecteur", "Lecteur")
    ids["modificateur"] = creer_user("mod@acme.tn", "Marc", "Modif", "Modificateur")
    ids["aucun"] = creer_user("non@acme.tn", "Nadia", "Aucun", "Aucun")
    cur.execute("INSERT INTO utilisateur (nom, prenom, email, mot_de_passe, role_id, actif) VALUES ('Off','Omar','off@acme.tn','x',NULL,FALSE) RETURNING id")
    ids["inactif"] = cur.fetchone()[0]

    app = FastAPI()
    app.include_router(prospects.router)
    app.include_router(clients.router)
    courant = {"cle": "admin"}

    def identite():
        return {"id": ids[courant["cle"]], "email": f"{courant['cle']}@acme.tn", "type": "interne", "nomBase": BASE_TEST}

    app.dependency_overrides[auth_dependency.utilisateur_connecte] = identite
    _ctx.update(client=TestClient(app), db=db, cur=cur, ids=ids, courant=courant, provisioning=provisioning)


def tearDownModule():
    if not _ctx:
        return
    from app import db as app_db

    pool = app_db._pools_entreprise.pop(BASE_TEST, None)
    if pool:
        pool.closeall()
    _ctx["db"].close()
    conn = _ctx["provisioning"]._connexion_maintenance()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)')
    finally:
        conn.close()


_compteur = {"n": 0}


def unique():
    _compteur["n"] += 1
    return _compteur["n"]


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.http = _ctx["client"]
        self.cur = _ctx["cur"]
        self.ids = _ctx["ids"]
        self.en_tant_que("admin")

    def en_tant_que(self, cle):
        _ctx["courant"]["cle"] = cle

    def donnees(self, **extra):
        n = unique()
        # Noms aléatoires (graine = n) : jamais « proches » les uns des autres, e-mails et téléphones uniques.
        nom = "".join(random.Random(n).choices(string.ascii_lowercase, k=10)).capitalize()
        base = {"nom": nom, "email": f"p{n}@zenith.tn", "telephone": f"2{n:07d}", "source": "salon"}
        base.update(extra)
        return base

    def creer(self, **extra):
        r = self.http.post("/api/prospects", json=self.donnees(**extra))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["prospect"]

    def historique(self, pid):
        r = self.http.get(f"/api/prospects/{pid}/historique")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["historique"]

    def types(self, pid):
        return [e["type_evenement"] for e in self.historique(pid)]


class CreationEtDoublonsTests(ApiTestCase):
    def test_creation_historise_et_attribue_le_responsable(self):
        p = self.creer()
        self.assertEqual(p["statut"], "nouveau")
        self.assertEqual(p["responsable_id"], self.ids["admin"])
        h = self.historique(p["id"])
        self.assertEqual([e["type_evenement"] for e in h], ["creation"])
        self.assertEqual(h[0]["auteur_nom"], "Alice Admin")

    def test_contact_obligatoire(self):
        r = self.http.post("/api/prospects", json={"nom": "Sans contact"})
        self.assertEqual(r.status_code, 422)

    def test_responsable_inconnu_ou_inactif_refuse(self):
        for rid in (999999, self.ids["inactif"]):
            r = self.http.post("/api/prospects", json=self.donnees(responsable_id=rid))
            self.assertEqual(r.status_code, 400, r.text)

    def test_doublon_email_non_contournable(self):
        p = self.creer()
        d = self.donnees(nom="Totalement autre", email=p["email"].upper())
        r = self.http.post("/api/prospects", json=d)
        self.assertEqual(r.status_code, 409)
        corps = r.json()
        self.assertEqual(corps["code"], "DOUBLON_FORT")
        self.assertFalse(corps["confirmable"])
        self.assertEqual(corps["doublons"][0]["id"], p["id"])
        self.assertIn("email", corps["doublons"][0]["motifs"])
        r = self.http.post("/api/prospects", json={**d, "confirmer_doublon": True})
        self.assertEqual(r.status_code, 409, "un doublon fort ne se confirme pas")

    def test_doublon_telephone_malgre_le_format(self):
        p = self.creer(telephone="+216 55 123 456")
        r = self.http.post("/api/prospects", json=self.donnees(nom="Autre nom", telephone="0055123456"))
        self.assertEqual(r.status_code, 409)
        self.assertIn("telephone", r.json()["doublons"][0]["motifs"])
        self.assertEqual(r.json()["doublons"][0]["id"], p["id"])

    def test_doublon_possible_sur_le_nom_se_confirme(self):
        p = self.creer(nom="Societe Horizon Bleu SARL")
        d = self.donnees(nom="HORIZON BLEU")
        r = self.http.post("/api/prospects", json=d)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "DOUBLON_POSSIBLE")
        self.assertTrue(r.json()["confirmable"])
        r = self.http.post("/api/prospects", json={**d, "confirmer_doublon": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotEqual(r.json()["prospect"]["id"], p["id"])

    def test_doublon_avec_un_client_existant(self):
        n = unique()
        self.cur.execute("INSERT INTO client (nom, email, telephone) VALUES (%s, %s, %s)",
                         (f"Client Orion {n}", f"orion{n}@client.tn", f"7{n:07d}"))
        r = self.http.post("/api/prospects", json=self.donnees(email=f"orion{n}@client.tn"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["doublons"][0]["entite"], "client")

    def test_index_unique_protege_contre_les_creations_concurrentes(self):
        """Même si deux requêtes passent le contrôle applicatif en même temps, la base refuse le doublon."""
        import psycopg2
        p = self.creer()
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            self.cur.execute("INSERT INTO prospect (nom, email) VALUES ('Concurrent', %s)", (p["email"].upper(),))
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            self.cur.execute("INSERT INTO prospect (nom, telephone) VALUES ('Concurrent', %s)", ("+216 " + p["telephone"],))
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self.cur.execute("INSERT INTO prospect (nom) VALUES ('Sans contact')")

    def test_verification_en_direct(self):
        p = self.creer()
        r = self.http.get("/api/prospects/verification-doublon", params={"email": p["email"]})
        self.assertEqual([d["id"] for d in r.json()["doublons"]], [p["id"]])
        r = self.http.get("/api/prospects/verification-doublon", params={"email": p["email"], "exclure_id": p["id"]})
        self.assertEqual(r.json()["doublons"], [])

    def test_prospect_archive_bloque_toujours_un_nouveau_doublon(self):
        p = self.creer()
        self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "Inactif depuis un an"})
        r = self.http.post("/api/prospects", json=self.donnees(email=p["email"]))
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()["doublons"][0]["archive"])
        self.assertIn("archivé", r.json()["detail"])


class ModificationEtStatutTests(ApiTestCase):
    def test_modification_historise_les_champs_changes(self):
        p = self.creer()
        corps = self.donnees(nom="Nom modifié Zenith", email=p["email"], telephone=p["telephone"])
        r = self.http.patch(f"/api/prospects/{p['id']}", json=corps)
        self.assertEqual(r.status_code, 200, r.text)
        h = self.historique(p["id"])
        self.assertEqual(h[0]["type_evenement"], "modification")
        self.assertEqual(h[0]["details"]["changements"]["nom"]["apres"], "Nom modifié Zenith")
        self.assertNotIn("email", h[0]["details"]["changements"])

    def test_modification_sans_changement_ne_cree_pas_d_evenement(self):
        p = self.creer()
        corps = {"nom": p["nom"], "email": p["email"], "telephone": p["telephone"], "source": p["source"]}
        r = self.http.patch(f"/api/prospects/{p['id']}", json=corps)
        self.assertEqual(r.json()["message"], "Aucune modification.")
        self.assertEqual(self.types(p["id"]), ["creation"])

    def test_modification_vers_un_doublon_refusee(self):
        a, b = self.creer(), self.creer()
        r = self.http.patch(f"/api/prospects/{b['id']}", json=self.donnees(email=a["email"], telephone=b["telephone"]))
        self.assertEqual(r.status_code, 409)

    def test_workflow_des_statuts(self):
        p = self.creer()
        url = f"/api/prospects/{p['id']}/statut"
        self.assertEqual(self.http.post(url, json={"statut": "contacte"}).status_code, 200)
        self.assertEqual(self.http.post(url, json={"statut": "contacte"}).status_code, 409)
        self.assertEqual(self.http.post(url, json={"statut": "nouveau"}).status_code, 409)
        self.assertEqual(self.http.post(url, json={"statut": "converti"}).status_code, 422)
        self.assertEqual(self.http.post(url, json={"statut": "perdu"}).status_code, 422)
        r = self.http.post(url, json={"statut": "perdu", "commentaire": "Budget insuffisant"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.http.post(url, json={"statut": "nouveau"}).status_code, 200)
        statuts = [e for e in self.historique(p["id"]) if e["type_evenement"] == "statut"]
        self.assertEqual([(e["details"]["avant"], e["details"]["apres"]) for e in reversed(statuts)],
                         [("nouveau", "contacte"), ("contacte", "perdu"), ("perdu", "nouveau")])
        self.assertEqual(statuts[1]["contenu"], "Budget insuffisant")


class SuiviCommercialTests(ApiTestCase):
    def test_suivi_date_et_tri_chronologique(self):
        p = self.creer()
        url = f"/api/prospects/{p['id']}/suivis"
        ancien = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertEqual(self.http.post(url, json={"type_evenement": "appel", "contenu": "Premier appel", "date_evenement": ancien}).status_code, 200)
        r = self.http.post(url, json={"type_evenement": "rendez_vous", "contenu": "RDV showroom", "date_evenement": recent})
        self.assertEqual(r.status_code, 200, r.text)
        h = self.historique(p["id"])
        contenus = [e["contenu"] for e in h if e["type_evenement"] in ("appel", "rendez_vous")]
        self.assertEqual(contenus, ["RDV showroom", "Premier appel"], "le plus récent d'abord")
        self.assertEqual(h[-1]["type_evenement"], "creation" if h[-1]["date_evenement"] < ancien else h[-1]["type_evenement"])
        fiche = self.http.get(f"/api/prospects/{p['id']}").json()
        self.assertTrue(fiche["derniere_interaction_le"].startswith(recent[:10]))

    def test_dates_incoherentes_refusees(self):
        p = self.creer()
        url = f"/api/prospects/{p['id']}/suivis"
        futur = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.assertEqual(self.http.post(url, json={"type_evenement": "note", "contenu": "x", "date_evenement": futur}).status_code, 400)
        hier = (datetime.now(timezone.utc) - timedelta(days=3))
        r = self.http.post(url, json={"type_evenement": "appel", "contenu": "x", "date_evenement": hier.isoformat(),
                                      "prochaine_relance": (hier.date() - timedelta(days=1)).isoformat()})
        self.assertEqual(r.status_code, 400)

    def test_relance_planifiee_et_retard(self):
        p = self.creer()
        url = f"/api/prospects/{p['id']}/suivis"
        r = self.http.post(url, json={"type_evenement": "appel", "contenu": "À rappeler",
                                      "prochaine_relance": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["prospect"]["relance_en_retard"])
        self.cur.execute("UPDATE prospect SET prochaine_relance_le = CURRENT_DATE - 2 WHERE id = %s", (p["id"],))
        self.assertTrue(self.http.get(f"/api/prospects/{p['id']}").json()["relance_en_retard"])

    def test_historique_non_modifiable_en_base(self):
        p = self.creer()
        import psycopg2
        for requete in ("UPDATE suivi_commercial SET contenu = 'piraté' WHERE entite_id = %s",
                        "DELETE FROM suivi_commercial WHERE entite_id = %s"):
            with self.assertRaises(psycopg2.Error):
                self.cur.execute(requete, (p["id"],))
        self.assertEqual(self.types(p["id"]), ["creation"])


class ConversionTests(ApiTestCase):
    def test_conversion_cree_le_client_et_conserve_l_historique(self):
        p = self.creer(nom="Prospect Convertible", adresse="12 rue des Oliviers")
        self.http.post(f"/api/prospects/{p['id']}/suivis", json={"type_evenement": "appel", "contenu": "Intéressé"})
        self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "qualifie"})
        r = self.http.post(f"/api/prospects/{p['id']}/convertir", json={})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["client_id"]
        fiche = r.json()["prospect"]
        self.assertEqual((fiche["statut"], fiche["client_id"]), ("converti", cid))
        client = self.http.get(f"/api/clients/{cid}").json()
        self.assertEqual((client["nom"], client["adresse"], client["prospect_origine_id"]), ("Prospect Convertible", "12 rue des Oliviers", p["id"]))
        types_prospect = self.types(p["id"])
        self.assertEqual(types_prospect[0], "conversion")
        self.assertIn("appel", types_prospect)
        h_client = self.http.get(f"/api/clients/{cid}/historique").json()["historique"]
        self.assertIn("appel", [e["type_evenement"] for e in h_client], "l'historique du prospect suit le client")
        self.assertIn(("client", "conversion"), [(e["entite_type"], e["type_evenement"]) for e in h_client])

    def test_conversion_refusee_dans_les_cas_invalides(self):
        p = self.creer()
        self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "perdu", "commentaire": "Abandon"})
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 409)
        self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "nouveau"})
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 200)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 409)
        self.assertEqual(self.http.post("/api/prospects/999999/convertir", json={}).status_code, 404)

    def test_conversion_bloquee_par_un_client_doublon_puis_rattachement(self):
        n = unique()
        p = self.creer(email=f"deja{n}@client.tn")
        # Le client est créé après le prospect (ex. saisi à la main par un autre collaborateur).
        self.cur.execute("INSERT INTO client (nom, email, telephone) VALUES (%s, %s, %s) RETURNING id",
                         (f"Client Deja Present {n}", f"deja{n}@client.tn", f"6{n:07d}"))
        client_id = self.cur.fetchone()[0]
        r = self.http.post(f"/api/prospects/{p['id']}/convertir", json={"confirmer_doublon": True})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "DOUBLON_FORT")
        self.assertEqual(r.json()["doublons"][0]["id"], client_id)
        r = self.http.post(f"/api/prospects/{p['id']}/convertir", json={"client_existant_id": client_id})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["client_id"], client_id)
        self.cur.execute("SELECT COUNT(*) FROM client WHERE id = %s", (client_id,))
        self.assertEqual(self.cur.fetchone()[0], 1)

    def test_nom_de_client_identique_bloque_la_conversion(self):
        n = unique()
        p = self.creer(nom=f"entreprise jumelle {n} SARL")
        self.cur.execute("INSERT INTO client (nom) VALUES (%s)", (f"Entreprise Jumelle {n}",))
        r = self.http.post(f"/api/prospects/{p['id']}/convertir", json={"confirmer_doublon": True})
        self.assertEqual(r.status_code, 409)

    def test_rattachement_a_un_client_archive_ou_inconnu_refuse(self):
        p = self.creer()
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={"client_existant_id": 999999}).status_code, 404)
        self.cur.execute("INSERT INTO client (nom, archive) VALUES (%s, TRUE) RETURNING id", (f"Ancien client {unique()}",))
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={"client_existant_id": self.cur.fetchone()[0]}).status_code, 409)


class ArchivageProspectTests(ApiTestCase):
    def test_archivage_puis_reactivation_sans_perte_d_historique(self):
        p = self.creer()
        self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "qualifie"})
        avant = len(self.historique(p["id"]))
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "x"}).status_code, 422)
        r = self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "Plus de réponse"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "Encore"}).status_code, 409)

        ids_actifs = [x["id"] for x in self.http.get("/api/prospects").json()["prospects"]]
        ids_archives = [x["id"] for x in self.http.get("/api/prospects", params={"archives": "archives"}).json()["prospects"]]
        self.assertNotIn(p["id"], ids_actifs)
        self.assertIn(p["id"], ids_archives)

        # Archivé = lecture seule
        corps = self.donnees(email=p["email"], telephone=p["telephone"], nom="Autre nom Delta")
        self.assertEqual(self.http.patch(f"/api/prospects/{p['id']}", json=corps).status_code, 409)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/suivis", json={"type_evenement": "note", "contenu": "x"}).status_code, 409)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 409)
        self.assertEqual(len(self.historique(p["id"])), avant + 1, "l'historique reste lisible")

        r = self.http.post(f"/api/prospects/{p['id']}/reactiver")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["prospect"]["statut"], "qualifie")
        self.assertFalse(r.json()["prospect"]["archive"])
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/reactiver").status_code, 409)
        h = self.types(p["id"])
        self.assertEqual(h[:2], ["reactivation", "archivage"])
        self.assertEqual(len(h), avant + 2)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/suivis", json={"type_evenement": "note", "contenu": "de retour"}).status_code, 200)

    def test_recherche_et_filtre_statut(self):
        p = self.creer(nom="Recherchable Quasar")
        ids = [x["id"] for x in self.http.get("/api/prospects", params={"q": "quasar"}).json()["prospects"]]
        self.assertEqual(ids, [p["id"]])
        ids = [x["id"] for x in self.http.get("/api/prospects", params={"q": "quasar", "statut": "qualifie"}).json()["prospects"]]
        self.assertEqual(ids, [])
        self.assertEqual(self.http.get("/api/prospects", params={"q": "100%_"}).json()["total"], 0)
        self.assertEqual(self.http.get("/api/prospects", params={"statut": "n-importe-quoi"}).status_code, 422)


class PermissionsTests(ApiTestCase):
    def test_permissions_exposees(self):
        self.assertEqual(sorted(self.http.get("/api/prospects/permissions").json()["actions"]),
                         sorted(["consulter", "creer", "modifier", "supprimer", "valider", "exporter"]))
        self.en_tant_que("commercial")
        actions = self.http.get("/api/prospects/permissions").json()["actions"]
        self.assertIn("valider", actions)
        self.en_tant_que("lecteur")
        self.assertEqual(self.http.get("/api/prospects/permissions").json()["actions"], ["consulter"])

    def test_lecteur_consulte_sans_rien_ecrire(self):
        p = self.creer()
        self.en_tant_que("lecteur")
        self.assertEqual(self.http.get("/api/prospects").status_code, 200)
        self.assertEqual(self.http.get(f"/api/prospects/{p['id']}").status_code, 200)
        self.assertEqual(self.http.get(f"/api/prospects/{p['id']}/historique").status_code, 200)
        self.assertEqual(self.http.post("/api/prospects", json=self.donnees()).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/suivis", json={"type_evenement": "note", "contenu": "x"}).status_code, 403)
        self.assertEqual(self.http.patch(f"/api/prospects/{p['id']}", json=self.donnees()).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "contacte"}).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "Test"}).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/reactiver").status_code, 403)

    def test_modificateur_ne_peut_ni_convertir_ni_archiver(self):
        p = self.creer()
        self.en_tant_que("modificateur")
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/statut", json={"statut": "contacte"}).status_code, 200)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 403)
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/archiver", json={"motif": "Test"}).status_code, 403)
        self.assertEqual(self.http.post("/api/prospects", json=self.donnees()).status_code, 403)

    def test_sans_droit_ou_compte_desactive(self):
        for cle in ("aucun", "inactif"):
            self.en_tant_que(cle)
            self.assertIn(self.http.get("/api/prospects").status_code, (401, 403), cle)

    def test_commercial_a_les_droits_par_defaut(self):
        self.en_tant_que("commercial")
        p = self.creer()
        self.assertEqual(self.http.post(f"/api/prospects/{p['id']}/convertir", json={}).status_code, 200)
        self.assertEqual(self.http.get(f"/api/prospects/{p['id']}/historique").json()["historique"][0]["auteur_nom"], "Sami Commercial")


class ClientsArchivageTests(ApiTestCase):
    def nouveau_client(self):
        r = self.http.post("/api/clients", json={"nom": f"Client Archivable {unique()}", "email": f"ca{unique()}@c.tn"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["client"]

    def test_archivage_reactivation_client_et_historique(self):
        c = self.nouveau_client()
        r = self.http.post(f"/api/clients/{c['id']}/archiver", json={"motif": "Cessation d'activité"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(c["id"], [x["id"] for x in self.http.get("/api/clients").json()["clients"]])
        self.assertIn(c["id"], [x["id"] for x in self.http.get("/api/clients", params={"archives": "archives"}).json()["clients"]])
        self.assertIn(c["id"], [x["id"] for x in self.http.get("/api/clients", params={"archives": "tous"}).json()["clients"]])
        self.assertEqual(self.http.patch(f"/api/clients/{c['id']}", json={"nom": "Nouveau nom"}).status_code, 409)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/suivis", json={"type_evenement": "note", "contenu": "x"}).status_code, 409)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/archiver", json={"motif": "Encore"}).status_code, 409)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/reactiver").status_code, 200)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/reactiver").status_code, 409)
        types = [e["type_evenement"] for e in self.http.get(f"/api/clients/{c['id']}/historique").json()["historique"]]
        self.assertEqual(types[:3], ["reactivation", "archivage", "creation"])

    def test_archivage_refuse_si_commande_ou_devis_en_cours(self):
        c = self.nouveau_client()
        self.cur.execute("INSERT INTO commande (client_id, statut) VALUES (%s, 'en_cours')", (c["id"],))
        r = self.http.post(f"/api/clients/{c['id']}/archiver", json={"motif": "Test archivage"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("1 commande", r.json()["detail"])
        self.cur.execute("UPDATE commande SET statut = 'livree' WHERE client_id = %s", (c["id"],))
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/archiver", json={"motif": "Test archivage"}).status_code, 200)
        self.cur.execute("SELECT COUNT(*) FROM commande WHERE client_id = %s", (c["id"],))
        self.assertEqual(self.cur.fetchone()[0], 1, "les commandes passées sont conservées")

    def test_modification_client_historisee_et_suivi_manuel(self):
        c = self.nouveau_client()
        self.http.patch(f"/api/clients/{c['id']}", json={"nom": f"{c['nom']} Bis", "email": c["email"]})
        self.http.post(f"/api/clients/{c['id']}/suivis", json={"type_evenement": "appel", "contenu": "Satisfait"})
        types = [e["type_evenement"] for e in self.http.get(f"/api/clients/{c['id']}/historique").json()["historique"]]
        self.assertEqual(types[:3], ["appel", "modification", "creation"])

    def test_permissions_client(self):
        c = self.nouveau_client()
        self.en_tant_que("commercial")  # clients.consulter/creer/modifier mais pas supprimer
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/archiver", json={"motif": "Test archivage"}).status_code, 403)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/reactiver").status_code, 403)
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/suivis", json={"type_evenement": "note", "contenu": "ok"}).status_code, 200)
        self.assertNotIn("supprimer", self.http.get("/api/clients/permissions").json()["actions"])
        self.en_tant_que("lecteur")
        self.assertEqual(self.http.post(f"/api/clients/{c['id']}/suivis", json={"type_evenement": "note", "contenu": "ok"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
