import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";

export default function Connexion() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  // Sécurité progressive mise en place par la binôme : après 2 échecs,
  // un captcha local (image SVG) est exigé ; après 4 échecs, un
  // reCAPTCHA est en plus requis.
  const [captchaRequis, setCaptchaRequis] = useState(false);
  const [captchaSvg, setCaptchaSvg] = useState("");
  const [captchaId, setCaptchaId] = useState("");
  const [captchaValeur, setCaptchaValeur] = useState("");
  const [recaptchaRequis, setRecaptchaRequis] = useState(false);

  async function chargerCaptcha() {
    const data = await apiPost("/auth/captcha", {}).catch(() => null);
    // La route captcha est en GET côté backend ; on utilise fetch direct
    // ici pour rester fidèle à sa définition (@router.get("/captcha")).
    const res = await fetch(
      `${import.meta.env.VITE_API_URL || "http://localhost:8000/api"}/auth/captcha`
    );
    const json = await res.json();
    setCaptchaSvg(json.svg);
    setCaptchaId(json.captchaId);
  }

  async function gererConnexion(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);

    try {
      const data = await apiPost("/auth/login", {
        email,
        motDePasse,
        captchaId: captchaRequis ? captchaId : undefined,
        captchaValeur: captchaRequis ? captchaValeur : undefined,
      });
      localStorage.setItem("token", data.token);
      navigate("/dashboard");
    } catch (err) {
      const info = err.data || {};
      setErreur(info.message || "Une erreur est survenue.");

      if (info.requiresCaptcha) {
        setCaptchaRequis(true);
        await chargerCaptcha();
      }
      if (info.requiresRecaptcha) {
        setRecaptchaRequis(true);
      }
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="connexion-layout">
      <aside className="connexion-marque">
        <ReseauDecoratif />
        <div className="connexion-marque__corps">
          <h1 className="connexion-marque__titre">{t("marque_titre")}</h1>
          <p className="connexion-marque__texte">{t("marque_texte")}</p>
        </div>
        <div className="connexion-marque__pied">© 2026 — Plateforme ERP SaaS</div>
      </aside>

      <div className="connexion-formulaire-zone">
        <form className="connexion-formulaire" onSubmit={gererConnexion}>
          <h1>{t("connexion_titre")}</h1>
          <p className="connexion-formulaire__soustitre">{t("connexion_soustitre")}</p>

          {erreur && <div className="erreur-message">{erreur}</div>}

          <div className="champ">
            <label htmlFor="email">{t("email")}</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="champ">
            <label htmlFor="mot-de-passe">{t("mot_de_passe")}</label>
            <input
              id="mot-de-passe"
              type="password"
              autoComplete="current-password"
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              required
            />
          </div>

          {captchaRequis && (
            <div className="champ">
              <label htmlFor="captcha">Code de sécurité</label>
              <div
                className="captcha-svg"
                dangerouslySetInnerHTML={{ __html: captchaSvg }}
              />
              <input
                id="captcha"
                type="text"
                value={captchaValeur}
                onChange={(e) => setCaptchaValeur(e.target.value)}
                required
              />
            </div>
          )}

          {recaptchaRequis && (
            <div className="app-page-note">
              Trop de tentatives échouées — vérification reCAPTCHA
              supplémentaire requise (à intégrer avec la clé du site).
            </div>
          )}

          <button className="bouton-principal" type="submit" disabled={enCours}>
            {enCours ? "..." : t("se_connecter")}
          </button>

          <Link className="lien-secondaire" to="/inscription">
            Pas encore de compte ? S'inscrire
          </Link>
        </form>
      </div>
    </div>
  );
}
