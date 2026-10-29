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

Montant en lettres : la facture indique le total en toutes lettres
(« Arrêtée la présente facture à la somme de ... »), dans la langue demandée.
Le PDF gère le français et l'anglais ; l'arabe n'est pas pris en charge ici
(la police standard ne contient pas les caractères arabes et reportlab ne
fait pas la mise en forme des lettres) : il retombe sur le français.
Les paramètres `langue` et `devise` sont facultatifs : sans eux, le rendu est
celui d'avant (français, MAD).
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from app.services import montant_lettres

BLEU_ENTETE = colors.HexColor("#1F4E79")
GRIS_TEXTE = colors.HexColor("#444444")

LANGUES_PDF = ("fr", "en")

TEXTES = {
    "fr": {
        "sous_titre": "Facture générée depuis le portail Utilisateurs externes",
        "facture": "Facture",
        "client": "Client",
        "date": "Date",
        "statut": "Statut",
        "total": "Montant total",
        "en_lettres": "Arrêtée la présente facture à la somme de",
        "scan_1": "Scannez pour vérifier",
        "scan_2": "l'authenticité du document",
        "code": "Code de vérification",
    },
    "en": {
        "sous_titre": "Invoice generated from the external users portal",
        "facture": "Invoice",
        "client": "Customer",
        "date": "Date",
        "statut": "Status",
        "total": "Total amount",
        "en_lettres": "Amount in words",
        "scan_1": "Scan to verify",
        "scan_2": "the authenticity of the document",
        "code": "Verification code",
    },
}


def _langue_pdf(langue) -> str:
    try:
        code = montant_lettres.normaliser_langue(langue)
    except ValueError:
        return "fr"
    return code if code in LANGUES_PDF else "fr"


def _dessiner_qr_code(url: str, taille_mm: float = 32) -> Drawing:
    widget = QrCodeWidget(url)
    x1, y1, x2, y2 = widget.getBounds()
    largeur_native = x2 - x1
    hauteur_native = y2 - y1
    taille_pt = taille_mm * mm

    dessin = Drawing(taille_pt, taille_pt, transform=[taille_pt / largeur_native, 0, 0, taille_pt / hauteur_native, 0, 0])
    dessin.add(widget)
    return dessin


def _texte_en_lettres(montant_total, devise: str, langue: str):
    """Montant en lettres, ou None si le montant ou la devise sont inexploitables :
    une facture ne doit jamais échouer à cause de cette ligne."""
    try:
        return montant_lettres.montant_en_lettres(montant_total, devise, langue)
    except ValueError:
        return None


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
    devise: str = "MAD",
    langue: str = "fr",
) -> bytes:
    langue = _langue_pdf(langue)
    t = TEXTES[langue]
    code_devise = str(devise or "MAD").strip().upper() or "MAD"

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    largeur_page, hauteur_page = A4

    # En-tête
    c.setFillColor(BLEU_ENTETE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, hauteur_page - 25 * mm, entreprise_nom or "BENJEDDOU ERP")

    c.setFillColor(GRIS_TEXTE)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, hauteur_page - 32 * mm, t["sous_titre"])

    c.setStrokeColor(colors.HexColor("#E4DFD6"))
    c.line(20 * mm, hauteur_page - 36 * mm, largeur_page - 20 * mm, hauteur_page - 36 * mm)

    # Corps
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, hauteur_page - 50 * mm, f"{t['facture']} {numero}")

    c.setFont("Helvetica", 11)
    date_texte = date_facture.strftime("%d/%m/%Y") if hasattr(date_facture, "strftime") else date_facture
    lignes = [
        f"{t['client']} : {client_nom}",
        f"{t['date']} : {date_texte}",
        f"{t['statut']} : {statut}",
        f"{t['total']} : {montant_total} {code_devise}",
    ]
    y = hauteur_page - 62 * mm
    for ligne in lignes:
        c.drawString(20 * mm, y, ligne)
        y -= 7 * mm

    # Montant en lettres (retour à la ligne automatique : le texte peut être long)
    en_lettres = _texte_en_lettres(montant_total, code_devise, langue)
    if en_lettres:
        y -= 3 * mm
        c.setFont("Helvetica-Oblique", 10)
        largeur_utile = largeur_page - 40 * mm
        for ligne in simpleSplit(f"{t['en_lettres']} : {en_lettres}.", "Helvetica-Oblique", 10, largeur_utile):
            c.drawString(20 * mm, y, ligne)
            y -= 5.5 * mm

    # QR code d'authenticité
    dessin_qr = _dessiner_qr_code(url_verification, taille_mm=32)
    renderPDF.draw(dessin_qr, c, largeur_page - 55 * mm, 25 * mm)

    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS_TEXTE)
    c.drawString(largeur_page - 55 * mm, 20 * mm, t["scan_1"])
    c.drawString(largeur_page - 55 * mm, 16 * mm, t["scan_2"])

    c.setFont("Helvetica", 6)
    c.drawString(20 * mm, 12 * mm, f"{t['code']} : {code_verification}")

    c.showPage()
    c.save()
    return tampon.getvalue()
