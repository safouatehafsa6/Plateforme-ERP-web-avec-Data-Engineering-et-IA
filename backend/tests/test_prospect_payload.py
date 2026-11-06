import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.prospects import ArchivagePayload, ChangementStatutPayload, ProspectPayload, SuiviPayload


class ProspectPayloadTests(unittest.TestCase):
    def test_email_ou_telephone_obligatoire(self):
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas")
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas", email="  ", telephone="")
        self.assertEqual(ProspectPayload(nom="Atlas", telephone="+216 12 345 678").email, None)
        self.assertEqual(ProspectPayload(nom="Atlas", email="a@atlas.tn").source, "autre")

    def test_reutilise_les_controles_client(self):
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas", email="pas-un-email")
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas", telephone="06ABC123")
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="   ", email="a@atlas.tn")

    def test_source_et_champs_texte(self):
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas", email="a@atlas.tn", source="inconnue")
        p = ProspectPayload(nom=" Atlas ", email="a@atlas.tn", contact="  ", besoin=" Devis ")
        self.assertEqual((p.nom, p.contact, p.besoin), ("Atlas", None, "Devis"))
        with self.assertRaises(ValidationError):
            ProspectPayload(nom="Atlas", email="a@atlas.tn", besoin="x" * 2001)


class StatutEtSuiviTests(unittest.TestCase):
    def test_motif_obligatoire_pour_perdu(self):
        with self.assertRaises(ValidationError):
            ChangementStatutPayload(statut="perdu")
        with self.assertRaises(ValidationError):
            ChangementStatutPayload(statut="perdu", commentaire="   ")
        self.assertEqual(ChangementStatutPayload(statut="perdu", commentaire="Prix").statut, "perdu")
        self.assertIsNone(ChangementStatutPayload(statut="contacte").commentaire)

    def test_converti_ne_se_choisit_pas_a_la_main(self):
        with self.assertRaises(ValidationError):
            ChangementStatutPayload(statut="converti")

    def test_suivi(self):
        with self.assertRaises(ValidationError):
            SuiviPayload(type_evenement="appel", contenu="   ")
        with self.assertRaises(ValidationError):
            SuiviPayload(type_evenement="creation", contenu="x")
        s = SuiviPayload(type_evenement="appel", contenu=" ok ", date_evenement="2026-01-05T10:00:00")
        self.assertEqual(s.contenu, "ok")
        self.assertEqual(s.date_evenement, datetime(2026, 1, 5, 10, tzinfo=timezone.utc))

    def test_motif_archivage(self):
        with self.assertRaises(ValidationError):
            ArchivagePayload(motif="ok")
        self.assertEqual(ArchivagePayload(motif="  Plus actif ").motif, "Plus actif")


if __name__ == "__main__":
    unittest.main()
