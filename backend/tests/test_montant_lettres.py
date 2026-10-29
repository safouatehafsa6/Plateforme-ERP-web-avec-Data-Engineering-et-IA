"""Tests de montant_lettres (pur Python, aucune dépendance).

    python -m unittest tests.test_montant_lettres -v
"""
import unittest
from decimal import Decimal

from app.services import montant_lettres as ml


def fr(montant, devise="MAD"):
    return ml.montant_en_lettres(montant, devise, "fr")


def en(montant, devise="MAD"):
    return ml.montant_en_lettres(montant, devise, "en")


def ar(montant, devise="MAD"):
    return ml.montant_en_lettres(montant, devise, "ar")


class TestFrancais(unittest.TestCase):
    def test_petits_nombres(self):
        cas = {
            0: "zéro dirham", 1: "un dirham", 2: "deux dirhams", 16: "seize dirhams",
            17: "dix-sept dirhams", 21: "vingt et un dirhams", 22: "vingt-deux dirhams",
            31: "trente et un dirhams", 61: "soixante et un dirhams",
            70: "soixante-dix dirhams", 71: "soixante et onze dirhams",
            72: "soixante-douze dirhams", 77: "soixante-dix-sept dirhams",
            80: "quatre-vingts dirhams", 81: "quatre-vingt-un dirhams",
            91: "quatre-vingt-onze dirhams", 99: "quatre-vingt-dix-neuf dirhams",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(fr(valeur), attendu)

    def test_centaines_et_milliers(self):
        cas = {
            100: "cent dirhams", 101: "cent un dirhams", 180: "cent quatre-vingts dirhams",
            200: "deux cents dirhams", 201: "deux cent un dirhams",
            280: "deux cent quatre-vingts dirhams", 999: "neuf cent quatre-vingt-dix-neuf dirhams",
            1000: "mille dirhams", 1001: "mille un dirhams", 2000: "deux mille dirhams",
            21000: "vingt et un mille dirhams", 80000: "quatre-vingt mille dirhams",
            81000: "quatre-vingt-un mille dirhams", 200000: "deux cent mille dirhams",
            1200: "mille deux cents dirhams",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(fr(valeur), attendu)

    def test_millions_et_milliards(self):
        cas = {
            1_000_000: "un million de dirhams",
            2_000_000: "deux millions de dirhams",
            80_000_000: "quatre-vingts millions de dirhams",
            200_000_000: "deux cents millions de dirhams",
            1_000_001: "un million un dirhams",
            1_500_000: "un million cinq cent mille dirhams",
            1_000_000_000: "un milliard de dirhams",
            3_000_000_000: "trois milliards de dirhams",
            2_000_000_000_000 - 1: None,   # vérifié ci-dessous (hors plage)
        }
        for valeur, attendu in cas.items():
            if attendu is None:
                with self.assertRaises(ValueError):
                    fr(valeur)
                continue
            with self.subTest(valeur=valeur):
                self.assertEqual(fr(valeur), attendu)

    def test_elision_de_pour_euro(self):
        self.assertEqual(fr(1_000_000, "EUR"), "un million d'euros")
        self.assertEqual(fr(5_000_000, "EUR"), "cinq millions d'euros")
        self.assertEqual(fr(1_000_000, "USD"), "un million de dollars américains")

    def test_montants_avec_centimes(self):
        self.assertEqual(
            fr("1234567.89"),
            "un million deux cent trente-quatre mille cinq cent soixante-sept "
            "dirhams et quatre-vingt-neuf centimes")
        self.assertEqual(fr("1.01"), "un dirham et un centime")
        self.assertEqual(fr("0.50"), "cinquante centimes")
        self.assertEqual(fr("0.01"), "un centime")
        self.assertEqual(fr("1200.00", "EUR"), "mille deux cents euros")
        self.assertEqual(fr("2.05", "USD"), "deux dollars américains et cinq cents")
        self.assertEqual(fr("1000000.50"), "un million de dirhams et cinquante centimes")

    def test_negatif(self):
        self.assertEqual(fr(-5), "moins cinq dirhams")
        self.assertEqual(fr("-0.00"), "zéro dirham")

    def test_plus_grand_montant(self):
        texte = fr("999999999999.99")
        self.assertTrue(texte.startswith("neuf cent quatre-vingt-dix-neuf milliards"))
        self.assertTrue(texte.endswith("quatre-vingt-dix-neuf centimes"))


class TestAnglais(unittest.TestCase):
    def test_cas(self):
        cas = [
            (0, "MAD", "zero dirhams"),
            (1, "MAD", "one dirham"),
            (21, "MAD", "twenty-one dirhams"),
            (100, "EUR", "one hundred euros"),
            (1234, "MAD", "one thousand two hundred thirty-four dirhams"),
            ("1234.56", "MAD", "one thousand two hundred thirty-four dirhams and fifty-six centimes"),
            ("1.01", "USD", "one dollar and one cent"),
            ("0.99", "EUR", "ninety-nine cents"),
            (1_000_000, "USD", "one million dollars"),
            (2_000_001, "USD", "two million one dollars"),
            (-12, "EUR", "minus twelve euros"),
        ]
        for valeur, devise, attendu in cas:
            with self.subTest(valeur=valeur, devise=devise):
                self.assertEqual(en(valeur, devise), attendu)


class TestArabe(unittest.TestCase):
    def test_accord_du_nom(self):
        cas = {
            0: "صفر درهم",
            1: "درهم واحد",
            2: "درهمان",
            3: "ثلاثة دراهم",
            10: "عشرة دراهم",
            11: "أحد عشر درهماً",
            12: "اثنا عشر درهماً",
            21: "واحد وعشرون درهماً",
            22: "اثنان وعشرون درهماً",
            99: "تسعة وتسعون درهماً",
            100: "مائة درهم",
            101: "مائة ودرهم واحد",
            102: "مائة ودرهمان",
            103: "مائة وثلاثة دراهم",
            110: "مائة وعشرة دراهم",
            111: "مائة وأحد عشر درهماً",
            200: "مائتا درهم",
            201: "مائتان ودرهم واحد",
            325: "ثلاثمائة وخمسة وعشرون درهماً",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(ar(valeur), attendu)

    def test_milliers_et_millions(self):
        cas = {
            1000: "ألف درهم",
            2000: "ألفا درهم",
            3000: "ثلاثة آلاف درهم",
            10000: "عشرة آلاف درهم",
            11000: "أحد عشر ألف درهم",
            100000: "مائة ألف درهم",
            200000: "مائتا ألف درهم",
            101000: "مائة ألف وألف درهم",
            1001: "ألف ودرهم واحد",
            1234: "ألف ومائتان وأربعة وثلاثون درهماً",
            2002: "ألفان ودرهمان",
            1_000_000: "مليون درهم",
            2_000_000: "مليونا درهم",
            2_500_000: "مليونان وخمسمائة ألف درهم",
            3_000_000: "ثلاثة ملايين درهم",
            1_000_000_000: "مليار درهم",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(ar(valeur), attendu)

    def test_centimes_et_devises(self):
        self.assertEqual(ar("0.50"), "خمسون سنتيماً")
        self.assertEqual(ar("1.50"), "درهم واحد وخمسون سنتيماً")
        self.assertEqual(ar("5.03"), "خمسة دراهم وثلاثة سنتيمات")
        self.assertEqual(ar("3", "USD"), "ثلاثة دولارات")
        self.assertEqual(ar("12.75", "USD"), "اثنا عشر دولاراً وخمسة وسبعون سنتاً")
        self.assertEqual(ar("2", "EUR"), "اثنان يورو")
        self.assertEqual(ar("100", "EUR"), "مائة يورو")

    def test_negatif(self):
        self.assertEqual(ar(-3), "سالب ثلاثة دراهم")


class TestEntrees(unittest.TestCase):
    def test_formats_de_montant(self):
        for entree in ("1234.50", "1 234,50", "1 234,50", "1234,5", 1234.5,
                       Decimal("1234.50")):
            with self.subTest(entree=entree):
                self.assertEqual(ml.normaliser_montant(entree), Decimal("1234.50"))

    def test_arrondi_a_la_limite(self):
        with self.assertRaises(ValueError):
            ml.normaliser_montant("999999999999.996")
        self.assertEqual(ml.normaliser_montant("999999999999.994"), Decimal("999999999999.99"))

    def test_arrondi_demi_superieur(self):
        self.assertEqual(ml.normaliser_montant("1.005"), Decimal("1.01"))
        self.assertEqual(ml.normaliser_montant("1.004"), Decimal("1.00"))
        self.assertEqual(fr("0.995"), "un dirham")

    def test_montants_refuses(self):
        for mauvais in ("", "abc", "1.2.3", "NaN", "Infinity", None, True, [], "10" * 20,
                        10 ** 12, "-1000000000000"):
            with self.subTest(mauvais=mauvais):
                with self.assertRaises(ValueError):
                    ml.normaliser_montant(mauvais)

    def test_devises(self):
        self.assertEqual(fr(2, "dh"), "deux dirhams")
        self.assertEqual(fr(2, "€"), "deux euros")
        self.assertEqual(fr(2, " usd "), "deux dollars américains")
        for mauvaise in ("", "XYZ", None, "MAD; DROP"):
            with self.subTest(mauvaise=mauvaise):
                with self.assertRaises(ValueError):
                    fr(1, mauvaise)

    def test_langues(self):
        self.assertEqual(ml.montant_en_lettres(2, "MAD", "FR-ma"), "deux dirhams")
        self.assertEqual(ml.montant_en_lettres(2, "MAD", "en_US"), "two dirhams")
        for mauvaise in ("", "de", None):
            with self.subTest(mauvaise=mauvaise):
                with self.assertRaises(ValueError):
                    ml.montant_en_lettres(2, "MAD", mauvaise)

    def test_nombre_seul(self):
        self.assertEqual(ml.nombre_en_lettres(1980, "fr"), "mille neuf cent quatre-vingts")
        self.assertEqual(ml.nombre_en_lettres(1980, "en"), "one thousand nine hundred eighty")
        self.assertEqual(ml.nombre_en_lettres(0, "ar"), "صفر")
        for mauvais in (-1, 10 ** 12, 1.5, True, "3"):
            with self.subTest(mauvais=mauvais):
                with self.assertRaises(ValueError):
                    ml.nombre_en_lettres(mauvais)

    def test_libelles(self):
        self.assertEqual(ml.libelle_montant_en_lettres("fr"), "Montant en lettres")
        self.assertEqual(set(ml.LIBELLES), set(ml.LANGUES))


class TestCoherence(unittest.TestCase):
    """Balayage : jamais d'exception ni de résultat vide sur toute la plage
    utile, dans les trois langues."""

    def test_balayage(self):
        valeurs = list(range(0, 1300)) + [
            9999, 10000, 10001, 99999, 100000, 100001, 100100, 101000, 101001,
            999999, 1000000, 1000001, 1100000, 12345678, 999999999, 1000000000,
            1234567890, 999999999999,
        ]
        for valeur in valeurs:
            for langue in ml.LANGUES:
                for devise in ml.DEVISES:
                    texte = ml.montant_en_lettres(f"{valeur}.{valeur % 100:02d}", devise, langue)
                    self.assertTrue(texte.strip(), (valeur, langue, devise))
                    self.assertNotIn("  ", texte, (valeur, langue, devise, texte))
                    self.assertFalse(texte.startswith(" ") or texte.endswith(" "))

    def test_francais_sans_s_parasite(self):
        # « cents » / « vingts » seulement quand rien ne suit dans le nombre
        for valeur in (200000, 280000, 80000, 800000, 1_280_000):
            texte = ml.nombre_en_lettres(valeur, "fr")
            self.assertNotIn("cents mille", texte)
            self.assertNotIn("vingts mille", texte)


if __name__ == "__main__":
    unittest.main()
