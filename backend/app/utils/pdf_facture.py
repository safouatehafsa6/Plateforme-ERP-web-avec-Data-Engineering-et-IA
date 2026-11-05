"""
pdf_facture.py — Génère le PDF d'une facture téléchargeable depuis le
portail Utilisateurs externes, avec un QR code d'authenticité (lettre de
cadrage, section 4 : "télécharger ses documents au format PDF intégrant
un QR Code d'authenticité").

Le QR code encode un lien public de vérification
(FRONTEND_URL/verifier/<nom_base>/<code_verification>) : n'importe qui
peut le scanner, même sans être connecté au portail, pour confirmer que
le document est authentique — sans jamais révéler le mot de passe ni les
autres factures du client.
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

BLEU_ENTETE = colors.HexColor("#1F4E79")
GRIS_TEXTE = colors.HexColor("#444444")


def _dessiner_qr_code(url: str, taille_mm: float = 32) -> Drawing:
    widget = QrCodeWidget(url)
    x1, y1, x2, y2 = widget.getBounds()
    largeur_native = x2 - x1
    hauteur_native = y2 - y1
    taille_pt = taille_mm * mm

    dessin = Drawing(taille_pt, taille_pt, transform=[taille_pt / largeur_native, 0, 0, taille_pt / hauteur_native, 0, 0])
    dessin.add(widget)
    return dessin


def generer_pdf_facture(
    *,
    numero: str,
    date_facture,
    montant_total,
    statut: str,
    client_nom: str,
    entreprise_nom: str,
    code_verification: str,
    url_verification: str,
) -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    largeur_page, hauteur_page = A4

    # En-tête
    c.setFillColor(BLEU_ENTETE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, hauteur_page - 25 * mm, entreprise_nom or "BENJEDDOU ERP")

    c.setFillColor(GRIS_TEXTE)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, hauteur_page - 32 * mm, "Facture générée depuis le portail Utilisateurs externes")

    c.setStrokeColor(colors.HexColor("#E4DFD6"))
    c.line(20 * mm, hauteur_page - 36 * mm, largeur_page - 20 * mm, hauteur_page - 36 * mm)

    # Corps
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, hauteur_page - 50 * mm, f"Facture {numero}")

    c.setFont("Helvetica", 11)
    lignes = [
        f"Client : {client_nom}",
        f"Date : {date_facture.strftime('%d/%m/%Y') if hasattr(date_facture, 'strftime') else date_facture}",
        f"Statut : {statut}",
        f"Montant total : {montant_total} MAD",
    ]
    y = hauteur_page - 62 * mm
    for ligne in lignes:
        c.drawString(20 * mm, y, ligne)
        y -= 7 * mm

    # QR code d'authenticité
    dessin_qr = _dessiner_qr_code(url_verification, taille_mm=32)
    renderPDF.draw(dessin_qr, c, largeur_page - 55 * mm, 25 * mm)

    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS_TEXTE)
    c.drawString(largeur_page - 55 * mm, 20 * mm, "Scannez pour vérifier")
    c.drawString(largeur_page - 55 * mm, 16 * mm, "l'authenticité du document")

    c.setFont("Helvetica", 6)
    c.drawString(20 * mm, 12 * mm, f"Code de vérification : {code_verification}")

    c.showPage()
    c.save()
    return tampon.getvalue()
