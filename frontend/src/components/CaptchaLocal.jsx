import { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import { RotateCw } from "lucide-react";
import { apiGet } from "../api/config";

// Le SVG et la réponse attendue sont générés côté SERVEUR : le frontend
// ne fait qu'afficher l'image et transmettre la valeur saisie, il ne
// connaît jamais la réponse correcte.
//
// `endpoint` permet de réutiliser ce composant sur plusieurs formulaires
// (connexion, inscription...), chacun avec son propre point d'accès
// captcha côté backend.
const CaptchaLocal = forwardRef(function CaptchaLocal(
  { valeur, onChangeValeur, endpoint = "/auth/captcha" },
  ref
) {
  const [captchaId, setCaptchaId] = useState(null);
  const [svg, setSvg] = useState("");
  const [chargement, setChargement] = useState(false);

  async function rafraichir() {
    setChargement(true);
    try {
      const data = await apiGet(endpoint);
      setCaptchaId(data.captchaId);
      setSvg(data.svg);
      onChangeValeur("");
    } finally {
      setChargement(false);
    }
  }

  useEffect(() => {
    rafraichir();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

  useImperativeHandle(ref, () => ({
    captchaId,
    rafraichir,
  }));

  return (
    <div className="champ">
      <label htmlFor="captcha">Code de sécurité</label>
      <div className="captcha-ligne">
        <div className="captcha-image" dangerouslySetInnerHTML={{ __html: svg }} />
        <button
          type="button"
          className="captcha-refresh"
          onClick={rafraichir}
          disabled={chargement}
          aria-label="Générer un nouveau code"
          title="Générer un nouveau code"
        >
          <RotateCw size={16} strokeWidth={2} className={chargement ? "captcha-refresh__icone--rotation" : ""} />
        </button>
      </div>
      <input
        id="captcha"
        type="text"
        value={valeur}
        onChange={(e) => onChangeValeur(e.target.value)}
        placeholder="Saisissez le code ci-dessus"
        autoComplete="off"
        required
      />
    </div>
  );
});

export default CaptchaLocal;
