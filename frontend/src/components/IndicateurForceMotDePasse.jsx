// Indicateur de force du mot de passe, mis à jour en temps réel selon les
// critères respectés (section 5 de la demande de l'entreprise : longueur,
// lettres, chiffres, caractères spéciaux).

function evaluerForce(motDePasse) {
  let score = 0;
  if (motDePasse.length >= 8) score += 1;
  if (motDePasse.length >= 12) score += 1;
  if (/[A-Za-zÀ-ÿ]/.test(motDePasse)) score += 1;
  if (/\d/.test(motDePasse)) score += 1;
  if (/[^A-Za-zÀ-ÿ0-9]/.test(motDePasse)) score += 1;
  return score; // 0 à 5
}

const NIVEAUX = [
  { seuil: 0, label: "Très faible", couleur: "#c0392b" },
  { seuil: 2, label: "Faible", couleur: "#d97706" },
  { seuil: 3, label: "Moyen", couleur: "#c98a2c" },
  { seuil: 4, label: "Fort", couleur: "#4a9b7f" },
  { seuil: 5, label: "Très fort", couleur: "#1f4a4d" },
];

export default function IndicateurForceMotDePasse({ motDePasse }) {
  if (!motDePasse) return null;

  const score = evaluerForce(motDePasse);
  const niveau = [...NIVEAUX].reverse().find((n) => score >= n.seuil);

  return (
    <div className="force-mdp">
      <div className="force-mdp__barres">
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="force-mdp__barre"
            style={{ backgroundColor: i <= score ? niveau.couleur : undefined }}
          />
        ))}
      </div>
      <span className="force-mdp__label" style={{ color: niveau.couleur }}>
        {niveau.label}
      </span>
    </div>
  );
}
