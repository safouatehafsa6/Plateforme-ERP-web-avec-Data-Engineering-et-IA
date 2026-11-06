import unittest

from app.services import prospects as r


class NormalisationTests(unittest.TestCase):
    def test_email_normalise(self):
        self.assertEqual(r.normaliser_email("  Contact@Atlas.TN "), "contact@atlas.tn")
        self.assertIsNone(r.normaliser_email("   "))
        self.assertIsNone(r.normaliser_email(None))

    def test_cle_telephone_ignore_format_et_indicatif(self):
        formats = ["+216 12 345 678", "0021612345678", "12.345.678", "(216) 12-345-678"]
        self.assertEqual({r.cle_telephone(f) for f in formats}, {"12345678"})
        self.assertIsNone(r.cle_telephone(""))
        self.assertIsNone(r.cle_telephone(None))

    def test_nom_sans_accents_ponctuation_ni_forme_juridique(self):
        self.assertEqual(r.normaliser_nom("Société ATLAS, S.A.R.L."), "atlas")
        self.assertEqual(r.normaliser_nom("  Étoile-du-Sud  "), "etoile du sud")

    def test_mot_cle_nom(self):
        self.assertEqual(r.mot_cle_nom("Ste Atlas Meuble"), "meuble")
        self.assertIsNone(r.mot_cle_nom("AB"))

    def test_similarite(self):
        self.assertEqual(r.similarite_noms("Atlas SARL", "ATLAS"), 1.0)
        self.assertEqual(r.similarite_noms("Mohamed Ben Ali", "Ben Ali Mohamed"), 1.0)
        self.assertGreaterEqual(r.similarite_noms("Meubles Atlas", "Meuble Atlas"), r.SEUIL_NOM_SIMILAIRE)
        self.assertLess(r.similarite_noms("Atlas", "Carthage"), 0.5)
        self.assertEqual(r.similarite_noms("", "Atlas"), 0.0)

    def test_des_nombres_differents_ne_sont_pas_similaires(self):
        self.assertEqual(r.similarite_noms("Agence Atlas 1", "Agence Atlas 2"), 0.0)
        self.assertEqual(r.similarite_noms("Agence Atlas 2", "agence atlas 2"), 1.0)


class DoublonsTests(unittest.TestCase):
    existant = {"id": 1, "entite": "prospect", "nom": "Atlas", "email": "a@atlas.tn", "telephone": "+216 12 345 678"}

    def test_email_identique_est_fort(self):
        d = r.evaluer_candidat(self.existant, nom="Autre", email="A@ATLAS.TN")
        self.assertEqual(d["niveau"], "fort")
        self.assertEqual(d["motifs"], ["email"])

    def test_telephone_autre_format_est_fort(self):
        d = r.evaluer_candidat(self.existant, nom="Autre", telephone="12345678")
        self.assertEqual(d["niveau"], "fort")
        self.assertIn("telephone", d["motifs"])

    def test_nom_seul_est_possible(self):
        d = r.evaluer_candidat(self.existant, nom="ATLAS SARL", email="x@y.tn")
        self.assertEqual(d["niveau"], "possible")
        self.assertEqual(d["motifs"], ["nom_identique"])

    def test_aucun_motif(self):
        self.assertIsNone(r.evaluer_candidat(self.existant, nom="Carthage", email="c@c.tn", telephone="99 888 777"))

    def test_tri_fort_en_premier_et_message(self):
        possible = r.evaluer_candidat(self.existant, nom="Atlas")
        fort = r.evaluer_candidat({**self.existant, "id": 2, "nom": "Zed"}, email="a@atlas.tn")
        tries = r.trier_doublons([possible, fort])
        self.assertEqual(tries[0]["niveau"], "fort")
        self.assertTrue(r.contient_doublon_fort(tries))
        self.assertIn("même adresse e-mail", r.message_doublons(tries))
        self.assertIn("1 autre", r.message_doublons(tries))

    def test_nom_identique_client_devient_fort(self):
        d = r.evaluer_candidat({**self.existant, "entite": "client"}, nom="Atlas")
        self.assertEqual(r.elever_nom_identique_client([d])[0]["niveau"], "fort")
        p = r.evaluer_candidat(self.existant, nom="Atlas")
        self.assertEqual(r.elever_nom_identique_client([p])[0]["niveau"], "possible")


class WorkflowTests(unittest.TestCase):
    def test_transitions(self):
        self.assertTrue(r.transition_autorisee("nouveau", "contacte"))
        self.assertTrue(r.transition_autorisee("perdu", "nouveau"))
        self.assertFalse(r.transition_autorisee("contacte", "nouveau"))
        self.assertFalse(r.transition_autorisee("converti", "nouveau"))
        self.assertFalse(r.transition_autorisee("nouveau", "converti"))

    def test_conversion_possible(self):
        self.assertTrue(r.peut_etre_converti("qualifie", False))
        self.assertFalse(r.peut_etre_converti("qualifie", True))
        self.assertFalse(r.peut_etre_converti("perdu", False))
        self.assertFalse(r.peut_etre_converti("converti", False))

    def test_differences(self):
        avant = {"nom": "A", "email": "a@a.tn", "contact": None, "adresse": ""}
        apres = {"nom": "B", "email": "a@a.tn", "contact": "", "adresse": None}
        self.assertEqual(r.differences(avant, apres), {"nom": {"avant": "A", "apres": "B"}})


if __name__ == "__main__":
    unittest.main()
