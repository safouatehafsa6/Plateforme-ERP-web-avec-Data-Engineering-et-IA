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
  const [erreur, setErreur] = useState("");

  async function rafraichir() {
    setChargement(true);
    setErreur("");
    try {
      const data = await apiGet(endpoint);
      if (!data?.svg) {
        throw new Error("Réponse du serveur incomplète (image manquante).");
      }
      setCaptchaId(data.captchaId);
      setSvg(data.svg);
      onChangeValeur("");
    } catch (err) {
      // Auparavant l'erreur n'était pas interceptée : la case restait
      // simplement vide, sans indication de ce qui n'allait pas.
      setSvg("");
      setCaptchaId(null);
      setErreur("Impossible de charger le code de sécurité. Vérifiez que le serveur est démarré, puis réessayez.");
      console.error(`Captcha (${endpoint}) :`, err);
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
        <div className="captcha-image">
          {svg ? (
            <div className="captcha-image__svg" dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <span className="captcha-image__vide">
              {chargement ? "Chargement…" : "Indisponible"}
            </span>
          )}
        </div>
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

      {erreur && <div className="captcha-erreur">{erreur}</div>}

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
