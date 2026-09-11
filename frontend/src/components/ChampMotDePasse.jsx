import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

// Champ mot de passe réutilisable, avec icône permettant d'afficher ou
// masquer la saisie. Reçoit les mêmes props qu'un <input> classique
// (value, onChange, id, required, minLength, autoComplete...).
export default function ChampMotDePasse({ id, value, onChange, autoComplete, required, minLength, onPaste }) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="champ-mot-de-passe">
      <input
        id={id}
        type={visible ? "text" : "password"}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        onPaste={onPaste}
      />
      <button
        type="button"
        className="champ-mot-de-passe__oeil"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        tabIndex={-1}
      >
        {visible ? <EyeOff size={17} strokeWidth={1.75} /> : <Eye size={17} strokeWidth={1.75} />}
      </button>
    </div>
  );
}
