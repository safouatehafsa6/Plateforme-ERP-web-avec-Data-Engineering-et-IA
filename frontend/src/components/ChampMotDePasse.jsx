import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

// Champ mot de passe réutilisable avec icône œil pour afficher/masquer
// la saisie (retour de l'encadrant du 10/09/2026, demandé pour TOUS les
// champs de mot de passe de la plateforme : connexion, inscription,
// réinitialisation).
//
// Purement cosmétique côté sécurité : la valeur reste toujours envoyée
// telle quelle au backend, seul le type d'affichage de l'input change.
//
// Deux modes d'utilisation :
//  - avec `label` : le composant s'occupe de tout (div.champ + label + champ)
//  - sans `label` : le composant ne rend que le champ lui-même, à utiliser
//    à l'intérieur d'un <div className="champ"><label>...</label>...</div>
//    déjà présent côté appelant (cas de Connexion.jsx / Inscription.jsx).
export default function ChampMotDePasse({
  id,
  label,
  value,
  onChange,
  autoComplete = "new-password",
  required = false,
  minLength,
  onPaste,
  ariaDescribedBy,
}) {
  const [visible, setVisible] = useState(false);

  const champ = (
    <div className="champ-mot-de-passe">
      <input
        id={id}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        onChange={onChange}
        onPaste={onPaste}
        required={required}
        minLength={minLength}
        aria-describedby={ariaDescribedBy}
      />
      <button
        type="button"
        className="champ-mot-de-passe__bascule"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        aria-pressed={visible}
        title={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        tabIndex={-1}
      >
        {visible ? <EyeOff size={17} strokeWidth={1.75} /> : <Eye size={17} strokeWidth={1.75} />}
      </button>
    </div>
  );

  if (!label) return champ;

  return (
    <div className="champ">
      <label htmlFor={id}>{label}</label>
      {champ}
    </div>
  );
}
