import unittest

from app.services.assistant_text import consigne_reformulation


class TestReformulation(unittest.TestCase):
    def test_langues_fr_ar_en(self):
        self.assertIn("français", consigne_reformulation("fr", "correction"))
        self.assertIn("anglais", consigne_reformulation("en", "correction"))
        self.assertIn("arabe", consigne_reformulation("ar", "correction"))

    def test_reformulation_preserve_donnees_metier(self):
        consigne = consigne_reformulation("fr", "reformulation")
        for terme in ("références", "dates", "montants", "quantités", "N'ajoute aucune information"):
            self.assertIn(terme, consigne)


if __name__ == "__main__":
    unittest.main()
