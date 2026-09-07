import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import ReCAPTCHA from "react-google-recaptcha";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";
import CaptchaLocal from "../components/CaptchaLocal";

// Clé de TEST officielle de Google reCAPTCHA v2 (case à cocher) : elle
// valide toujours la vérification, pratique en développement. Avant la
// mise en production, remplacez-la par votre propre clé de site, obtenue
// gratuitement sur https://www.google.com/recaptcha/admin
const RECAPTCHA_SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY
  || "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI";

export default function Connexion() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const captchaRef = useRef(null);
  const recaptchaRef = useRef(null);

  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [captchaValeur, setCaptchaValeur] = useState("");
  const [recaptchaToken, setRecaptchaToken] = useState(null);
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  // Ces deux indicateurs viennent du BACKEND, jamais calculés seul côté
  // client : c'est le serveur qui décide, selon le nombre d'échecs réels
  // pour cet email, si le captcha / reCAPTCHA doivent être affichés.
  const [afficherCaptcha, setAfficherCaptcha] = useState(false);
  const [afficherRecaptcha, setAfficherRecaptcha] = useState(false);

  async function gererConnexion(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);

    try {
      const corps = { email, motDePasse };
      if (afficherCaptcha) {
        corps.captchaId = captchaRef.current?.captchaId;
        corps.captchaValeur = captchaValeur;
      }
      if (afficherRecaptcha) {
        corps.recaptchaToken = recaptchaToken;
      }

      const data = await apiPost("/auth/login", corps);
      localStorage.setItem("token", data.token);
      navigate("/dashboard");
    } catch (err) {
      const infos = err.data || {};
      setErreur(infos.message || t("erreur_identifiants"));

      if (infos.requiresCaptcha) {
        setAfficherCaptcha(true);
        // Renouvellement automatique du captcha après chaque tentative,
        // qu'elle ait échoué à cause du mot de passe ou du code lui-même.
        captchaRef.current?.rafraichir();
        setCaptchaValeur("");
      }
      if (infos.requiresRecaptcha) {
        setAfficherRecaptcha(true);
        recaptchaRef.current?.reset();
        setRecaptchaToken(null);
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

          {afficherCaptcha && (
            <CaptchaLocal ref={captchaRef} valeur={captchaValeur} onChangeValeur={setCaptchaValeur} />
          )}

          {afficherRecaptcha && (
            <div className="champ">
              <ReCAPTCHA
                ref={recaptchaRef}
                sitekey={RECAPTCHA_SITE_KEY}
                onChange={(token) => setRecaptchaToken(token)}
                hl={i18nCodeVersLangueGoogle()}
              />
            </div>
          )}

          <button className="bouton-principal" type="submit" disabled={enCours}>
            {enCours ? "..." : t("se_connecter")}
          </button>

          <a className="lien-secondaire" href="#">
            {t("mot_de_passe_oublie")}
          </a>
        </form>
      </div>
    </div>
  );
}

function i18nCodeVersLangueGoogle() {
  const lang = document.documentElement.lang;
  return lang === "ar" ? "ar" : lang === "en" ? "en" : "fr";
}
