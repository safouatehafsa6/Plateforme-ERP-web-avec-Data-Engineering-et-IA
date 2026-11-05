"""Tests Room Live : invitation par e-mail avec expiration + résumé de réunion.

Aucune base de données ni serveur SMTP/LLM n'est nécessaire : app.db est
remplacé par un faux module, l'envoi d'e-mail est intercepté et le LLM est
désactivé (LLM_PROVIDER=none) pour tester le repli local.
"""
import asyncio
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["LLM_PROVIDER"] = "none"

if "app.db" not in sys.modules:
    faux_db = types.ModuleType("app.db")
    faux_db.pool_central = MagicMock()
    faux_db.get_pool_entreprise = MagicMock()
    sys.modules["app.db"] = faux_db

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import room_live
from app.security.auth_dependency import utilisateur_connecte
from app.services.room_manager import RoomManager, room_manager
from app.services.room_summary import resume_local, resumer

HOTE = {"id": 1, "email": "hote@societe.ma", "entrepriseId": 10, "nomBase": "b1", "type": "interne"}
MEMBRE = {"id": 2, "email": "membre@societe.ma", "entrepriseId": 10, "nomBase": "b1", "type": "interne"}
AUTRE_ENTREPRISE = {"id": 9, "email": "x@autre.ma", "entrepriseId": 99, "nomBase": "b2", "type": "interne"}


def client_pour(utilisateur):
    app = FastAPI()
    app.include_router(room_live.router)
    app.dependency_overrides[utilisateur_connecte] = lambda: utilisateur
    return TestClient(app)


def creer_salle(prive=True):
    return asyncio.run(room_manager.create(HOTE, "Réunion\r\nBcc: pirate@x.ma", "", prive))["id"]


class InvitationTests(unittest.TestCase):
    def test_invitation_expiree_refuse_l_acces(self):
        rid = creer_salle()
        salle = room_manager.rooms[rid]
        room_manager.invite(salle, "membre@societe.ma")
        self.assertIsNotNone(room_manager.get_accessible(MEMBRE, rid))
        salle["invite_expiry"]["membre@societe.ma"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertIsNone(room_manager.get_accessible(MEMBRE, rid))
        self.assertNotIn("membre@societe.ma", salle["invited_emails"])

    def test_endpoint_invite_envoie_un_email_avec_lien(self):
        rid = creer_salle()
        with patch.object(room_live, "envoyer_email") as envoi:
            r = client_pour(HOTE).post(f"/api/room-live/rooms/{rid}/invite", json={"email": "Membre@Societe.ma"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["email_sent"])
        self.assertIn(f"/room-live?room={rid}", body["link"])
        dest, sujet, corps = envoi.call_args.args
        self.assertEqual(dest, "membre@societe.ma")
        self.assertNotIn("\n", sujet)          # pas d'injection d'en-tête
        self.assertNotIn("\r", sujet)
        self.assertIn(body["link"], corps)
        self.assertIsNotNone(room_manager.get_accessible(MEMBRE, rid))

    def test_echec_smtp_n_annule_pas_l_invitation(self):
        rid = creer_salle()
        with patch.object(room_live, "envoyer_email", side_effect=OSError("smtp down")):
            r = client_pour(HOTE).post(f"/api/room-live/rooms/{rid}/invite", json={"email": "membre@societe.ma"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["email_sent"])
        self.assertIsNotNone(room_manager.get_accessible(MEMBRE, rid))

    def test_email_invalide_et_non_hote(self):
        rid = creer_salle()
        self.assertEqual(client_pour(HOTE).post(f"/api/room-live/rooms/{rid}/invite", json={"email": "pas-un-email"}).status_code, 400)
        asyncio.run(room_manager.join(HOTE, rid))
        room_manager.invite(room_manager.rooms[rid], MEMBRE["email"])
        asyncio.run(room_manager.join(MEMBRE, rid))
        with patch.object(room_live, "envoyer_email"):
            r = client_pour(MEMBRE).post(f"/api/room-live/rooms/{rid}/invite", json={"email": "z@societe.ma"})
        self.assertEqual(r.status_code, 403)


class ResumeTests(unittest.TestCase):
    MSGS = [
        {"sender": "hote@societe.ma", "content": "Bonjour, on valide le devis client ?", "created_at": "2026-11-01T10:00:00+00:00"},
        {"sender": "membre@societe.ma", "content": "Oui, décision : envoyer avant le 5.", "created_at": "2026-11-01T10:05:00+00:00"},
    ]

    def test_resume_local(self):
        txt = resume_local("Salle A", ["hote@societe.ma", "membre@societe.ma"], self.MSGS)
        self.assertIn("2 message(s)", txt)
        self.assertIn("Questions posées", txt)
        self.assertIn("Décisions", txt)

    def test_sans_llm_repli_local_avec_note(self):
        res = resumer("Salle A", ["a"], self.MSGS)
        self.assertEqual(res["mode"], "local")
        self.assertIn("note", res)

    def test_salle_vide(self):
        self.assertEqual(resumer("S", [], [])["mode"], "local")

    def test_endpoint_membre_uniquement_et_cache(self):
        rid = creer_salle()
        salle = room_manager.rooms[rid]
        salle["messages"].extend(self.MSGS)
        r = client_pour(HOTE).post(f"/api/room-live/rooms/{rid}/summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["message_count"], 2)
        self.assertFalse(r.json()["cached"])
        self.assertTrue(client_pour(HOTE).post(f"/api/room-live/rooms/{rid}/summary").json()["cached"])
        # autre membre de la même entreprise non invité / autre entreprise : refus
        self.assertEqual(client_pour(MEMBRE).post(f"/api/room-live/rooms/{rid}/summary").status_code, 404)
        self.assertEqual(client_pour(AUTRE_ENTREPRISE).post(f"/api/room-live/rooms/{rid}/summary").status_code, 404)


if __name__ == "__main__":
    unittest.main()
