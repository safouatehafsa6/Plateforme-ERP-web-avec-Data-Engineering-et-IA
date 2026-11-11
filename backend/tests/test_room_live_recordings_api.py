"""Tests Room Live : enregistrements (droits, consentement, ordre des fragments, isolation entre
entreprises) et rechargement des salles persistées.

Sans base de données : app.db est un faux module et room_store est remplacé par un faux magasin
en mémoire dont les enregistrements sont rangés PAR BASE (comme en production), ce qui permet de
vérifier qu'une entreprise ne peut pas lire ceux d'une autre.
"""
import asyncio
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["LLM_PROVIDER"] = "none"
os.environ["ROOM_LIVE_PERSIST"] = "0"

if "app.db" not in sys.modules:
    faux_db = types.ModuleType("app.db")
    faux_db.pool_central = MagicMock()
    faux_db.get_pool_entreprise = MagicMock()
    sys.modules["app.db"] = faux_db
try:
    import psycopg2.errors  # noqa: F401
except ImportError:  # environnement de test minimal
    pg = types.ModuleType("psycopg2")
    pg_err = types.ModuleType("psycopg2.errors")
    pg_err.UniqueViolation = type("UniqueViolation", (Exception,), {})
    pg.errors = pg_err
    sys.modules.update({"psycopg2": pg, "psycopg2.errors": pg_err})

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import room_live, room_live_recordings
from app.security.auth_dependency import utilisateur_connecte
from app.services import recording_storage as stockage
from app.services import room_store
from app.services.room_manager import room_manager

HOTE = {"id": 1, "email": "hote@societe.ma", "entrepriseId": 10, "nomBase": "b1", "type": "interne"}
MEMBRE = {"id": 2, "email": "membre@societe.ma", "entrepriseId": 10, "nomBase": "b1", "type": "interne"}
AUTRE = {"id": 9, "email": "x@autre.ma", "entrepriseId": 99, "nomBase": "b2", "type": "interne"}


class FauxMagasin:
    def __init__(self):
        self.recs, self.consents, self.journal = {}, {}, []

    def creer(self, room, user, rec_id, mime, chemin, retention_jours):
        if any(k[0] == room["db"] and r["room_id"] == room["id"] and r["status"] == "en_cours"
               for k, r in self.recs.items()):
            raise room_store.RecordingConflict()
        now = datetime.now(timezone.utc)
        self.recs[(room["db"], rec_id)] = {
            "id": rec_id, "room_id": room["id"], "room_name": room["name"], "owner_id": room["owner_id"],
            "started_by_id": str(user["id"]), "started_by": user["email"], "started_at": now, "ended_at": None,
            "status": "en_cours", "mime": mime, "size": 0, "path": chemin, "next_sequence": 0,
            "retention_until": now + timedelta(days=retention_jours)}
        return {"id": rec_id, "retention_until": self.recs[(room["db"], rec_id)]["retention_until"].isoformat()}

    def fragment(self, key, rec_id, seq, taille):
        r = self.recs.get((key, rec_id))
        if not r or r["status"] != "en_cours" or r["next_sequence"] != seq:
            return False
        r["next_sequence"] += 1
        r["size"] += taille
        return True

    def terminer(self, key, rec_id, user, statut="termine"):
        r = self.recs.get((key, rec_id))
        if not r or r["status"] != "en_cours":
            return False
        r["status"], r["ended_at"] = statut, datetime.now(timezone.utc)
        return True

    def lire(self, key, rec_id):
        return self.recs.get((key, rec_id))

    def lister(self, key, room_id=None):
        return [r for (k, _), r in self.recs.items() if k == key and (not room_id or r["room_id"] == room_id)]

    def supprimer(self, key, rec_id, user, action="suppression"):
        self.recs.pop((key, rec_id), None)


def client_pour(utilisateur):
    app = FastAPI()
    app.include_router(room_live.router)
    app.include_router(room_live_recordings.router)
    app.dependency_overrides[utilisateur_connecte] = lambda: utilisateur
    return TestClient(app)


class EnregistrementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ancien_dossier = stockage.RECORDINGS_DIR
        stockage.RECORDINGS_DIR = Path(self.tmp.name)
        self.magasin = FauxMagasin()
        m = self.magasin
        self.patchs = [
            patch.object(room_store, "creer_enregistrement", m.creer),
            patch.object(room_store, "ajouter_fragment", m.fragment),
            patch.object(room_store, "terminer_enregistrement", m.terminer),
            patch.object(room_store, "lire_enregistrement", m.lire),
            patch.object(room_store, "lister_enregistrements", m.lister),
            patch.object(room_store, "supprimer_enregistrement", m.supprimer),
            patch.object(room_store, "purger_expires", lambda key: []),
            patch.object(room_store, "enregistrer_consentement", lambda *a, **k: None),
            patch.object(room_store, "journaliser_acces", lambda *a, **k: None),
        ]
        for p in self.patchs:
            p.start()
        room_manager.rooms.clear()
        self.room_id = asyncio.run(room_manager.create(HOTE, "Réunion", "", False))["id"]
        asyncio.run(room_manager.join(MEMBRE, self.room_id))

    def tearDown(self):
        for p in self.patchs:
            p.stop()
        stockage.RECORDINGS_DIR = self.ancien_dossier
        self.tmp.cleanup()
        room_manager.rooms.clear()

    def demarrer(self):
        r = client_pour(HOTE).post(f"/api/room-live/rooms/{self.room_id}/recordings/start", json={})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["recording"]["id"]

    def test_un_membre_ne_peut_pas_enregistrer(self):
        r = client_pour(MEMBRE).post(f"/api/room-live/rooms/{self.room_id}/recordings/start", json={})
        self.assertEqual(r.status_code, 403)

    def test_un_seul_enregistrement_a_la_fois(self):
        self.demarrer()
        r = client_pour(HOTE).post(f"/api/room-live/rooms/{self.room_id}/recordings/start", json={})
        self.assertEqual(r.status_code, 409)

    def test_format_non_webm_refuse(self):
        r = client_pour(HOTE).post(f"/api/room-live/rooms/{self.room_id}/recordings/start",
                                   json={"mime": "application/x-sh"})
        self.assertEqual(r.status_code, 400)

    def test_consentement_enregistre_et_visible(self):
        rec_id = self.demarrer()
        r = client_pour(MEMBRE).post(f"/api/room-live/recordings/{rec_id}/consent", json={"decision": "refuse"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(room_manager.rooms[self.room_id]["recording"]["consents"][str(MEMBRE["id"])], "refuse")
        self.assertEqual(client_pour(MEMBRE).post(f"/api/room-live/recordings/{rec_id}/consent",
                                                  json={"decision": "peut-etre"}).status_code, 422)
        # Celui qui enregistre a déjà consenti : pas de changement possible.
        self.assertEqual(client_pour(HOTE).post(f"/api/room-live/recordings/{rec_id}/consent",
                                                json={"decision": "refuse"}).status_code, 400)

    def test_fragments_dans_l_ordre_uniquement(self):
        rec_id = self.demarrer()
        c = client_pour(HOTE)
        url = f"/api/room-live/recordings/{rec_id}/chunk"
        h = {"Content-Type": "application/octet-stream"}
        self.assertEqual(c.post(url + "?seq=0", content=b"AAA", headers=h).status_code, 200)
        self.assertEqual(c.post(url + "?seq=2", content=b"CCC", headers=h).status_code, 409)  # trou
        self.assertEqual(c.post(url + "?seq=0", content=b"AAA", headers=h).status_code, 409)  # rejeu
        self.assertEqual(c.post(url + "?seq=1", content=b"BB", headers=h).status_code, 200)
        fichier = stockage.absolute_path(self.magasin.lire("b1", rec_id)["path"])
        self.assertEqual(fichier.read_bytes(), b"AAABB")
        self.assertEqual(self.magasin.lire("b1", rec_id)["size"], 5)

    def test_seul_l_enregistreur_envoie_des_fragments(self):
        rec_id = self.demarrer()
        r = client_pour(MEMBRE).post(f"/api/room-live/recordings/{rec_id}/chunk?seq=0", content=b"x",
                                     headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(r.status_code, 403)

    def test_arret_puis_telechargement_par_l_hote(self):
        rec_id = self.demarrer()
        c = client_pour(HOTE)
        c.post(f"/api/room-live/recordings/{rec_id}/chunk?seq=0", content=b"DATA",
               headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(c.get(f"/api/room-live/recordings/{rec_id}/download").status_code, 409)  # en cours
        self.assertEqual(c.post(f"/api/room-live/recordings/{rec_id}/stop").status_code, 200)
        self.assertIsNone(room_manager.rooms[self.room_id].get("recording"))
        r = c.get(f"/api/room-live/recordings/{rec_id}/download")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"DATA")
        self.assertIn("attachment", r.headers["content-disposition"])

    def test_membre_simple_et_autre_entreprise_ne_voient_rien(self):
        rec_id = self.demarrer()
        client_pour(HOTE).post(f"/api/room-live/recordings/{rec_id}/stop")
        for qui in (MEMBRE, AUTRE):
            c = client_pour(qui)
            self.assertEqual(c.get(f"/api/room-live/recordings/{rec_id}/download").status_code, 404)
            self.assertEqual(c.delete(f"/api/room-live/recordings/{rec_id}").status_code, 404)
            self.assertEqual(c.get("/api/room-live/recordings").json()["recordings"], [])
        self.assertEqual(len(client_pour(HOTE).get("/api/room-live/recordings").json()["recordings"]), 1)

    def test_identifiant_invalide_introuvable(self):
        self.assertEqual(client_pour(HOTE).get("/api/room-live/recordings/../../etc/passwd/download").status_code, 404)
        self.assertEqual(client_pour(HOTE).get("/api/room-live/recordings/ZZZ/download").status_code, 404)

    def test_suppression_efface_fichier_et_metadonnee(self):
        rec_id = self.demarrer()
        c = client_pour(HOTE)
        c.post(f"/api/room-live/recordings/{rec_id}/chunk?seq=0", content=b"DATA",
               headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(c.delete(f"/api/room-live/recordings/{rec_id}").status_code, 409)  # en cours
        fichier = stockage.absolute_path(self.magasin.lire("b1", rec_id)["path"])
        c.post(f"/api/room-live/recordings/{rec_id}/stop")
        self.assertEqual(c.delete(f"/api/room-live/recordings/{rec_id}").status_code, 200)
        self.assertFalse(fichier.exists())
        self.assertIsNone(self.magasin.lire("b1", rec_id))

    def test_depart_de_l_enregistreur_interrompt(self):
        rec_id = self.demarrer()
        client_pour(HOTE).post(f"/api/room-live/rooms/{self.room_id}/leave")
        self.assertEqual(self.magasin.lire("b1", rec_id)["status"], "interrompu")


class RechargementTests(unittest.TestCase):
    def test_salle_rechargee_apres_redemarrage_et_cloisonnee(self):
        room_manager.rooms.clear()
        room_manager._charges.clear()
        salle = {"id": "c" * 12, "name": "Persistée", "description": "", "is_private": True, "tenant": "10",
                 "db": "b1", "owner_id": "1", "owner_email": "hote@societe.ma",
                 "created_at": datetime.now(timezone.utc).isoformat(), "invited_emails": set(),
                 "invite_expiry": {}, "last_summary": None, "messages": [],
                 "participants": {"1": {"user_id": "1", "email": "hote@societe.ma", "role": "host",
                                        "joined_at": datetime.now(timezone.utc).isoformat(), "blocked": False}}}
        with patch.dict(os.environ, {"ROOM_LIVE_PERSIST": "1"}), \
                patch.object(room_store, "charger_salles", lambda cle, tenant: {salle["id"]: salle} if cle == "b1" else {}):
            self.assertIsNotNone(room_manager.get_accessible(HOTE, salle["id"], require_member=True))
            self.assertIsNone(room_manager.get_accessible(AUTRE, salle["id"]))  # autre base, autre tenant
        room_manager.rooms.clear()
        room_manager._charges.clear()

    def test_echec_de_chargement_reessaye_plus_tard(self):
        room_manager.rooms.clear()
        room_manager._charges.clear()
        with patch.dict(os.environ, {"ROOM_LIVE_PERSIST": "1"}), \
                patch.object(room_store, "charger_salles", lambda cle, tenant: None):
            room_manager.hydrate(HOTE)
            self.assertNotIn("b1", room_manager._charges)


if __name__ == "__main__":
    unittest.main()
