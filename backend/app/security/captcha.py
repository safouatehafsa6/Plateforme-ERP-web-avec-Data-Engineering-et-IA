import secrets
import uuid

CARACTERES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I


def _generer_code(longueur: int = 5) -> str:
    return "".join(secrets.choice(CARACTERES) for _ in range(longueur))


def _generer_svg(code: str) -> str:
    largeur, hauteur = 160, 56
    lignes_bruit = "".join(
        f'<line x1="{secrets.randbelow(largeur)}" y1="{secrets.randbelow(hauteur)}" '
        f'x2="{secrets.randbelow(largeur)}" y2="{secrets.randbelow(hauteur)}" '
        f'stroke="#c8c8c8" stroke-width="1"/>'
        for _ in range(5)
    )

    espacement = largeur / (len(code) + 1)
    couleurs = ["#0e2233", "#4c7a79", "#a9702b"]
    lettres = ""
    for i, caractere in enumerate(code):
        x = espacement * (i + 1)
        y = hauteur / 2 + secrets.randbelow(13) - 6
        rotation = secrets.randbelow(51) - 25
        couleur = secrets.choice(couleurs)
        lettres += (
            f'<text x="{x}" y="{y}" font-size="26" font-family="Georgia, serif" '
            f'font-weight="700" fill="{couleur}" text-anchor="middle" '
            f'transform="rotate({rotation} {x} {y})">{caractere}</text>'
        )

    return (
        f'<svg viewBox="0 0 {largeur} {hauteur}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{largeur}" height="{hauteur}" fill="#f3f1ec"/>'
        f"{lignes_bruit}{lettres}</svg>"
    )


def generer_captcha() -> dict:
    code = _generer_code()
    svg = _generer_svg(code)
    identifiant = str(uuid.uuid4())
    return {"id": identifiant, "code": code, "svg": svg}
