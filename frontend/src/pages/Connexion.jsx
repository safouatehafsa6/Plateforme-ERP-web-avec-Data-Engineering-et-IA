import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import ReCAPTCHA from "react-google-recaptcha";
import { apiPost, apiGet, API_BASE_URL } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";
import CaptchaLocal from "../components/CaptchaLocal";
import ChampMotDePasse from "../components/ChampMotDePasse";

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

  const [afficherCaptcha, setAfficherCaptcha] = useState(false);
  const [afficherRecaptcha, setAfficherRecaptcha] = useState(false);
  const [essaiExpireEmail, setEssaiExpireEmail] = useState(null);

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
      localStorage.setItem("email", email.trim().toLowerCase());
      if (data.essai) {
        // Message informatif sur les visites restantes de la période
        // d'essai, conformément à la demande de l'entreprise.
        localStorage.setItem("essaiInfo", JSON.stringify(data.essai));
        // Alerte explicitement demandée, en plus du bandeau affiché sur
        // le tableau de bord.
        window.alert(`Visites restantes : ${data.essai.visitesRestantes} - ${data.essai.visitesMax}`);
      } else {
        localStorage.removeItem("essaiInfo");
      }
      navigate("/dashboard");
    } catch (err) {
      const infos = err.data || {};
      setErreur(infos.message || t("erreur_identifiants"));

      if (infos.essaiExpire) {
        setEssaiExpireEmail(email);
      }
      if (infos.requiresCaptcha) {
        setAfficherCaptcha(true);
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
            <ChampMotDePasse
              id="mot-de-passe"
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

          {essaiExpireEmail && (
            <div className="bloc-compte-desactive">
              <p>
                Votre compte est désactivé : la période d'essai gratuite est
                terminée. Souscrivez un abonnement pour réactiver
                immédiatement l'accès à votre espace.
              </p>
              <Link
                className="bouton-principal"
                to={`/abonnement?email=${encodeURIComponent(essaiExpireEmail)}`}
                style={{ display: "block", textAlign: "center", textDecoration: "none", marginBottom: "0.6rem" }}
              >
                S'abonner maintenant
              </Link>
              <a
                className="bouton-secondaire-large"
                href={`${API_BASE_URL}/entreprises/export-donnees?email=${encodeURIComponent(essaiExpireEmail)}`}
                target="_blank"
                rel="noreferrer"
              >
                Exporter toutes mes données
              </a>
            </div>
          )}

          <Link className="lien-secondaire" to="/mot-de-passe-oublie">
            {t("mot_de_passe_oublie")}
          </Link>
        </form>
      </div>
    </div>
  );
}

function i18nCodeVersLangueGoogle() {
  const lang = document.documentElement.lang;
  return lang === "ar" ? "ar" : lang === "en" ? "en" : "fr";
}
