"""IDP : dates en toutes lettres et contrôles adaptés au type de document (un rapport n'est pas une facture)."""
import unittest
from datetime import date

from app.services import idp_controles as ct


def codes(donnees):
    return {a.code: a.gravite for a in ct.verifier_document(donnees, aujourdhui=date(2026, 11, 15))}


class DatesEnLettresTests(unittest.TestCase):
    def test_formats_francais_anglais_arabe(self):
        attendu = date(2026, 11, 9)
        for texte in ("09 novembre 2026", "9 Novembre 2026", "le 9 nov. 2026", "9 nov 2026",
                      "November 9, 2026", "Nov 9th 2026", "9 November 2026", "9 نوفمبر 2026", "٩ نونبر ٢٠٢٦"):
            self.assertEqual(ct.convertir_date(texte), attendu, texte)

    def test_mois_accentues_et_ordinal(self):
        self.assertEqual(ct.convertir_date("1er février 2026"), date(2026, 2, 1))
        self.assertEqual(ct.convertir_date("15 août 2025"), date(2025, 8, 15))
        self.assertEqual(ct.convertir_date("3 décembre 2024"), date(2024, 12, 3))

    def test_dates_invalides_refusees(self):
        for texte in ("31 février 2026", "32 novembre 2026", "novembre 2026", "bientôt", "9 foobar 2026"):
            self.assertIsNone(ct.convertir_date(texte), texte)

    def test_formats_numeriques_inchanges(self):
        self.assertEqual(ct.convertir_date("2026-11-09"), date(2026, 11, 9))
        self.assertEqual(ct.convertir_date("09/11/2026"), date(2026, 11, 9))


class TypeDeDocumentTests(unittest.TestCase):
    RAPPORT = {"type_document": "rapport de stage", "numero": "N° 57 / 78", "date": "09 novembre 2026",
               "fournisseur": {"nom": "BENJEDDOU Technologie Services"}, "devise": "EUR"}

    def test_un_rapport_n_est_pas_bloque_par_les_regles_de_facture(self):
        anomalies = codes(self.RAPPORT)
        self.assertFalse(ct.a_des_erreurs(ct.verifier_document(self.RAPPORT, aujourdhui=date(2026, 11, 15))))
        self.assertNotIn("lignes_manquantes", anomalies)
        self.assertNotIn("total_ttc_manquant", anomalies)

    def test_un_rapport_sans_numero_ni_date_donne_des_avertissements_seulement(self):
        anomalies = codes({"type_document": "contrat de prestation"})
        self.assertEqual(anomalies["numero_manquant"], "avertissement")
        self.assertEqual(anomalies["date_manquante"], "avertissement")
        self.assertNotIn("erreur", anomalies.values())

    def test_une_facture_reste_controlee(self):
        anomalies = codes({"type_document": "facture", "date": "09/11/2026"})
        for code in ("numero_manquant", "fournisseur_manquant", "lignes_manquantes", "total_ttc_manquant"):
            self.assertEqual(anomalies[code], "erreur", code)

    def test_type_absent_garde_le_comportement_historique(self):
        anomalies = codes({"numero": "F1"})
        self.assertEqual(anomalies["lignes_manquantes"], "erreur")
        self.assertEqual(anomalies["total_ttc_manquant"], "erreur")

    def test_types_commerciaux_reconnus(self):
        for t in ("facture", "Invoice", "bon de commande", "devis", "avoir", "فاتورة", "bon de livraison"):
            self.assertTrue(ct.est_document_commercial(t), t)
        for t in ("rapport de stage", "contrat de prestation", "cv", "pièce d'identité"):
            self.assertFalse(ct.est_document_commercial(t), t)

    def test_montants_incoherents_d_un_document_non_commercial_restent_signales(self):
        donnees = {**self.RAPPORT, "total_ht": "100", "total_tva": "20", "total_ttc": "500"}
        self.assertEqual(codes(donnees)["total_ttc_incoherent"], "erreur")


if __name__ == "__main__":
    unittest.main()


try:                                   # idp_structuration exige pydantic et httpx (présents dans le container)
    from app.services import idp_structuration as _st  # noqa: F401
    _DEPENDANCES = True
except ImportError:
    _DEPENDANCES = False


@unittest.skipUnless(_DEPENDANCES, "pydantic / httpx absents de cet environnement")
class ReglagesModeleTests(unittest.TestCase):
    """Limites de texte et délais de l'analyse IDP selon le modèle configuré."""

    def setUp(self):
        import os
        from unittest import mock
        self.env = mock.patch.dict(os.environ, {"IDP_MAX_CARACTERES": "", "IDP_LLM_TIMEOUT": "",
                                                "OPENAI_API_KEY": "", "LLM_PROVIDER": "ollama"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_modele_local_recoit_moins_de_texte_et_plus_de_temps(self):
        from app.services import idp_structuration as st
        self.assertEqual(st.limite_caracteres(), st.LIMITE_MODELE_LOCAL)
        self.assertGreaterEqual(st.delai_modele(), 600.0)

    def test_reglages_explicites_l_emportent(self):
        import os
        from app.services import idp_structuration as st
        os.environ["IDP_MAX_CARACTERES"] = "12000"
        os.environ["IDP_LLM_TIMEOUT"] = "90"
        self.assertEqual(st.limite_caracteres(), 12000)
        self.assertEqual(st.delai_modele(), 90.0)
        os.environ["IDP_MAX_CARACTERES"] = "abc"
        self.assertEqual(st.limite_caracteres(), st.MAX_CARACTERES_MODELE)   # valeur invalide ignorée
