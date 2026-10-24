import unittest

from app.services.suggestions import normaliser, suggerer

CAT = [
    {"texte": "Société Atlas", "type": "client", "detail": ""},
    {"texte": "Atelier Orion", "type": "fournisseur", "detail": ""},
    {"texte": "Ciment CPJ 45", "type": "produit", "detail": "REF-001"},
    {"texte": "Ciment blanc", "type": "produit", "detail": "REF-002"},
]


def textes(res):
    return [r["texte"] for r in res]


class SuggestionsTests(unittest.TestCase):
    def test_french_term_from_first_letters_with_translations(self):
        res = suggerer("Créer une fact", [], "fr")
        self.assertEqual(res[0]["texte"], "facture")
        self.assertEqual(res[0]["remplace"], "fact")
        self.assertIn("invoice", res[0]["detail"])
        self.assertIn("فاتورة", res[0]["detail"])

    def test_english_and_arabic_input(self):
        self.assertEqual(suggerer("show inv", [], "en")[0]["texte"], "invoice")
        self.assertEqual(suggerer("فات", [], "ar")[0]["texte"], "فاتورة")
        # les formes arabes avec ة / ه ou alef différent sont unifiées
        self.assertEqual(normaliser("أحمد"), normaliser("احمد"))

    def test_accent_insensitive(self):
        self.assertEqual(suggerer("echea", [], "fr")[0]["texte"], "échéance")

    def test_real_company_names_and_internal_word_match(self):
        self.assertEqual(suggerer("Soc", CAT)[0]["texte"], "Société Atlas")
        self.assertIn("Société Atlas", textes(suggerer("atl", CAT)))

    def test_multiword_fragment_replaces_whole_typed_part(self):
        res = suggerer("commande pour Société At", CAT)
        self.assertEqual(res[0]["texte"], "Société Atlas")
        self.assertEqual(res[0]["remplace"], "Société At")

    def test_module_context_prioritises_matching_entity(self):
        cat = [{"texte": "Cimenterie Nord", "type": "fournisseur", "detail": ""},
               {"texte": "Ciment CPJ 45", "type": "produit", "detail": ""}]
        self.assertEqual(suggerer("cim", cat, module="stock")[0]["type"], "produit")
        self.assertEqual(suggerer("cim", cat, module="achats")[0]["type"], "fournisseur")

    def test_language_boost(self):
        # « sto » : stock existe dans les 3 langues ; « invo » : seulement en anglais
        self.assertEqual(suggerer("qua", [], "en")[0]["texte"], "quantity")
        self.assertEqual(suggerer("qua", [], "fr")[0]["texte"], "quantité")

    def test_no_suggestion_cases(self):
        self.assertEqual(suggerer("f", CAT), [])            # trop court
        self.assertEqual(suggerer("facture ", CAT), [])     # espace final : mot terminé
        self.assertEqual(suggerer("facture", [], "fr"), [])  # déjà saisi en entier
        self.assertEqual(suggerer("zzzzz", CAT), [])

    def test_limit_and_no_duplicates(self):
        res = suggerer("ci", CAT, limite=2)
        self.assertLessEqual(len(res), 2)
        all_res = suggerer("ci", CAT, limite=10)
        self.assertEqual(len(textes(all_res)), len(set(textes(all_res))))


if __name__ == "__main__":
    unittest.main()
