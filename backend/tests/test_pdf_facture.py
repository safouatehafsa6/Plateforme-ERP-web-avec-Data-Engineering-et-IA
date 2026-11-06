"""Tests de la facture PDF avec montant en lettres.

Le texte est relu dans le PDF généré (pypdf, déjà installé avec le backend).

    python -m unittest tests.test_pdf_facture -v
"""
import io
import unittest
from datetime import date
from decimal import Decimal

from pypdf import PdfReader

from app.utils.pdf_facture import generer_pdf_facture


def facture(**kw):
    donnees = dict(
        numero="FA-2026-0042", date_facture=date(2026, 3, 15),
        montant_total=Decimal("1234.50"), statut="Payée", client_nom="Société Atlas",
        entreprise_nom="BENJEDDOU ERP", code_verification="abc123",
        url_verification="http://localhost:3000/verifier/base/abc123",
    )
    donnees.update(kw)
    return generer_pdf_facture(**donnees)


def texte(pdf: bytes) -> str:
    lecteur = PdfReader(io.BytesIO(pdf))
    assert len(lecteur.pages) == 1
    return " ".join(lecteur.pages[0].extract_text().split())


class TestPdfFacture(unittest.TestCase):
    def test_appel_historique_inchange_en_francais_mad(self):
        # Même appel qu'avant : aucun paramètre de langue ni de devise.
        t = texte(facture())
        self.assertIn("Facture FA-2026-0042", t)
        self.assertIn("Montant total : 1234.50 MAD", t)
        self.assertIn("Arrêtée la présente facture à la somme de : "
                      "mille deux cent trente-quatre dirhams et cinquante centimes.", t)

    def test_anglais_et_devise(self):
        t = texte(facture(langue="en", devise="EUR"))
        self.assertIn("Invoice FA-2026-0042", t)
        self.assertIn("Total amount : 1234.50 EUR", t)
        self.assertIn("Amount in words : one thousand two hundred thirty-four euros "
                      "and fifty cents.", t)

    def test_arabe_retombe_sur_le_francais(self):
        t = texte(facture(langue="ar"))
        self.assertIn("Arrêtée la présente facture", t)

    def test_langue_inconnue_retombe_sur_le_francais(self):
        self.assertIn("Facture FA-2026-0042", texte(facture(langue="zz")))

    def test_montant_long_retourne_a_la_ligne_sans_deborder(self):
        t = texte(facture(montant_total=Decimal("999999999999.99")))
        self.assertIn("neuf cent quatre-vingt-dix-neuf milliards", t)
        self.assertIn("quatre-vingt-dix-neuf centimes.", t)

    def test_montant_ou_devise_inexploitable_ne_casse_pas_la_facture(self):
        for kw in ({"montant_total": "abc"}, {"montant_total": None}, {"devise": "XYZ"},
                   {"montant_total": Decimal("1e15")}):
            with self.subTest(kw=kw):
                pdf = facture(**kw)
                self.assertTrue(pdf.startswith(b"%PDF"))
                self.assertNotIn("Arrêtée", texte(pdf))

    def test_montant_texte_du_portail(self):
        # Le portail peut transmettre un montant déjà converti en chaîne.
        self.assertIn("deux cents dirhams", texte(facture(montant_total="200.00")))


if __name__ == "__main__":
    unittest.main()
