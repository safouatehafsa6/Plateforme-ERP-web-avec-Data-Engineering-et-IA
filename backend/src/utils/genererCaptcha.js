import crypto from "crypto";

const CARACTERES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // sans 0/O/1/I pour éviter la confusion

function genererCode(longueur = 5) {
  let code = "";
  for (let i = 0; i < longueur; i++) {
    code += CARACTERES[crypto.randomInt(0, CARACTERES.length)];
  }
  return code;
}

// Génère un SVG avec le code, des rotations aléatoires et des lignes de
// bruit — suffisant pour gêner un script basique, sans dépendance externe.
function genererSvg(code) {
  const largeur = 160;
  const hauteur = 56;
  let lignesBruit = "";
  for (let i = 0; i < 5; i++) {
    const x1 = crypto.randomInt(0, largeur);
    const y1 = crypto.randomInt(0, hauteur);
    const x2 = crypto.randomInt(0, largeur);
    const y2 = crypto.randomInt(0, hauteur);
    lignesBruit += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#c8c8c8" stroke-width="1"/>`;
  }

  let lettres = "";
  const espacement = largeur / (code.length + 1);
  for (let i = 0; i < code.length; i++) {
    const x = espacement * (i + 1);
    const y = hauteur / 2 + crypto.randomInt(-6, 6);
    const rotation = crypto.randomInt(-25, 25);
    const couleur = ["#0e2233", "#4c7a79", "#a9702b"][crypto.randomInt(0, 3)];
    lettres += `<text x="${x}" y="${y}" font-size="26" font-family="Georgia, serif" font-weight="700"
      fill="${couleur}" text-anchor="middle" transform="rotate(${rotation} ${x} ${y})">${code[i]}</text>`;
  }

  return `<svg viewBox="0 0 ${largeur} ${hauteur}" xmlns="http://www.w3.org/2000/svg">
    <rect width="${largeur}" height="${hauteur}" fill="#f3f1ec"/>
    ${lignesBruit}
    ${lettres}
  </svg>`;
}

export function genererCaptcha() {
  const code = genererCode();
  const svg = genererSvg(code);
  const id = crypto.randomUUID();
  return { id, code, svg };
}
