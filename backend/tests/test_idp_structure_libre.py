"""Tests de la structure libre IDP : assainissement, vérification contre le document, corrections."""
import unittest

from app.services import idp_structure_libre as sl

DOC = """CONTRAT DE PRESTATION
Entre la société ATLAS SARL (ICE 001234567000089) et Monsieur Karim Alaoui.
Durée : 12 mois à compter du 01/02/2026. Montant mensuel : 12 500,00 MAD.
Préavis de résiliation : 30 jours."""

REPONSE = {
    "nature_document": "contrat de prestation", "langue": "fr", "module_suggere": "Achats",
    "resume": "Contrat de prestation de 12 mois.",
    "sections": [
        {"cle": "Parties", "nom": "Parties concernées", "champs": [
            {"cle": "client_nom", "libelle": "Client", "type": "texte", "valeur": "ATLAS SARL",
             "source": "la société ATLAS SARL (ICE 001234567000089)"},
            {"cle": "prestataire", "libelle": "Prestataire", "type": "texte", "valeur": "Karim Alaoui",
             "source": "Monsieur Karim Alaoui"},
        ]},
        {"cle": "finances", "nom": "Conditions financières", "champs": [
            {"cle": "montant_mensuel", "libelle": "Montant mensuel", "type": "montant", "valeur": "12 500,00 MAD",
             "source": "Montant mensuel : 12 500,00 MAD"},
            {"cle": "penalite", "libelle": "Pénalité de retard", "type": "montant", "valeur": "5 %",
             "source": "pénalité de 5 % par mois"},                   # absente du document : inventée
            {"cle": "vide", "libelle": "Vide", "type": "texte", "valeur": ""},
        ]},
        {"cle": "duree", "nom": "Durée", "champs": [
            {"cle": "date_debut", "libelle": "Début", "type": "date", "valeur": "01/02/2026", "source": "01/02/2026"},
            {"cle": "preavis_jours", "libelle": "Préavis", "type": "nombre", "valeur": "30 jours",
             "source": "Préavis de résiliation : 30 jours"},
        ]},
    ],
    "tableaux": [{"cle": "t", "nom": "Livrables", "colonnes": ["Livrable", "Date"],
                  "lignes": [["Rapport", "01/03/2026"], ["", ""]]}],
    "relations": [
        {"de": "parties.client_nom", "vers": "finances.montant_mensuel", "nature": "paie"},
        {"de": "parties.client_nom", "vers": "inexistant.x", "nature": "lien fantôme"},
    ],
}


class AssainirTests(unittest.TestCase):
    def setUp(self):
        self.s = sl.assainir(REPONSE, DOC)
        self.champs = {(sec["cle"], c["cle"]): c for sec in self.s["sections"] for c in sec["champs"]}

    def test_cles_modules_et_champs_vides(self):
        self.assertEqual(self.s["module_suggere"], "achats")
        self.assertEqual([sec["cle"] for sec in self.s["sections"]], ["parties", "finances", "duree"])
        self.assertNotIn(("finances", "vide"), self.champs)

    def test_verification_contre_le_document(self):
        self.assertEqual(self.champs[("parties", "client_nom")]["verification"], "source_trouvee")
        self.assertEqual(self.champs[("finances", "penalite")]["verification"], "a_verifier")  # inventé

    def test_conversion_par_le_code(self):
        self.assertEqual(self.champs[("finances", "montant_mensuel")]["valeur"], "12500.00")
        self.assertEqual(self.champs[("duree", "date_debut")]["valeur"], "2026-02-01")

    def test_champs_nouveaux_et_relations(self):
        self.assertTrue(self.champs[("parties", "client_nom")]["nouveau"])
        self.assertEqual(len(self.s["relations"]), 1)            # le lien vers un champ inexistant est écarté

    def test_tableau_nettoye(self):
        self.assertEqual(self.s["tableaux"][0]["lignes"], [["Rapport", "01/03/2026"]])

    def test_types_et_tailles_bornes(self):
        enorme = {"sections": [{"cle": "s", "nom": "S", "champs": [
            {"cle": f"c{i}", "libelle": "x", "type": "inconnu", "valeur": "v"} for i in range(500)]}]}
        s = sl.assainir(enorme, "v")
        self.assertEqual(len(s["sections"][0]["champs"]), sl.MAX_CHAMPS_PAR_SECTION)
        self.assertEqual(s["sections"][0]["champs"][0]["type"], "texte")

    def test_sortie_invalide_refusee(self):
        with self.assertRaises(ValueError):
            sl.assainir(["pas", "un", "objet"], DOC)

    def test_cles_arabes_sans_latin(self):
        s = sl.assainir({"sections": [{"nom": "الأطراف", "champs": [{"libelle": "العميل", "valeur": "شركة أطلس"}]}]},
                        "شركة أطلس")
        self.assertEqual(s["sections"][0]["cle"], "section_1")
        self.assertEqual(s["sections"][0]["champs"][0]["cle"], "champ_1")
        self.assertEqual(s["sections"][0]["champs"][0]["verification"], "valeur_trouvee")


class ExtraireEtCorrectionTests(unittest.TestCase):
    def test_extraire_accepte_json_dans_un_bloc_markdown(self):
        import json
        s = sl.extraire(DOC, lambda texte: "```json\n" + json.dumps(REPONSE) + "\n```")
        self.assertEqual(s["nature_document"], "contrat de prestation")

    def test_champs_connus_reutilises_ne_sont_plus_nouveaux(self):
        s = sl.extraire(DOC, lambda t: REPONSE, champs_connus={"client_nom"})
        champs = {c["cle"]: c for sec in s["sections"] for c in sec["champs"]}
        self.assertFalse(champs["client_nom"]["nouveau"])
        self.assertTrue(champs["prestataire"]["nouveau"])

    def test_correction_humaine_conserve_la_preuve_des_champs_intacts(self):
        ancienne = sl.assainir(REPONSE, DOC)
        corrigee = sl.assainir(REPONSE, DOC)
        corrigee["sections"][0]["champs"][1]["valeur"] = "Karim ALAOUI"          # modifié
        corrigee["sections"][1]["champs"].append({"cle": "ajout", "libelle": "Ajout", "type": "texte", "valeur": "x"})
        s = sl.fusionner_correction(ancienne, corrigee)
        champs = {(sec["cle"], c["cle"]): c for sec in s["sections"] for c in sec["champs"]}
        self.assertEqual(champs[("parties", "client_nom")]["verification"], "source_trouvee")   # intact
        self.assertEqual(champs[("parties", "prestataire")]["verification"], "corrige")         # modifié
        self.assertEqual(champs[("parties", "prestataire")]["origine"], "utilisateur")
        self.assertEqual(champs[("finances", "ajout")]["origine"], "utilisateur")

    def test_registre_ignore_les_champs_non_verifies(self):
        s = sl.assainir(REPONSE, DOC)
        cles = {c["cle"] for c in sl.champs_a_enregistrer(s)}
        self.assertIn("client_nom", cles)
        self.assertNotIn("penalite", cles)


if __name__ == "__main__":
    unittest.main()
