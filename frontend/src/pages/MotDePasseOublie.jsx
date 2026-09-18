import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";
import CaptchaLocal from "../components/CaptchaLocal";
import ChampMotDePasse from "../components/ChampMotDePasse";
import IndicateurForceMotDePasse from "../components/IndicateurForceMotDePasse";

// Parcours "Mot de passe oublié" en 3 étapes, conformément au retour de
// l'encadrant du 10/09/2026 :
//   1) email -> envoi d'un code OTP par e-mail
//   2) vérification du code OTP
//   3) création d'un nouveau mot de passe, soumis aux MÊMES règles de
//      sécurité que l'inscription (politique de mot de passe, indicateur
//      de force, CAPTCHA)
//
// Comme pour la connexion et l'inscription, toute validation faite ici
// côté client est un simple confort UX : le backend revérifie tout
// (politique de mot de passe, jeton de session, CAPTCHA) avant
// d'accepter le changement.
export default function MotDePasseOublie() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const captchaRef = useRef(null);

  const [etape, setEtape] = useState(0); // 0 = email, 1 = code, 2 = nouveau mdp, 3 = terminé
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [jetonReset, setJetonReset] = useState(null);

  const [nouveauMotDePasse, setNouveauMotDePasse] = useState("");
  const [nouveauMotDePasseConfirmation, setNouveauMotDePasseConfirmation] = useState("");
  const [captchaValeur, setCaptchaValeur] = useState("");

  async function gererDemandeCode(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      const data = await apiPost("/auth/mot-de-passe-oublie", { email });
      setInfo(data.message);
      setEtape(1);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  async function gererRenvoiCode() {
    setErreur("");
    setEnCours(true);
    try {
      const data = await apiPost("/auth/renvoyer-code-reinitialisation", { email });
      setInfo(data.message);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  async function gererVerificationCode(e) {
    e.preventDefault();
    setErreur("");
    setInfo("");
    setEnCours(true);
    try {
      const data = await apiPost("/auth/verifier-code-reinitialisation", { email, code });
      setJetonReset(data.jetonReset);
      setEtape(2);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  function validerNouveauMotDePasseAvantEnvoi() {
    const mdp = nouveauMotDePasse;
    const politiqueOk =
      mdp.length >= 8 && /[A-Za-zÀ-ÿ]/.test(mdp) && /\d/.test(mdp) && /[^A-Za-zÀ-ÿ0-9]/.test(mdp);
    if (!politiqueOk) {
      return t("erreur_politique_mot_de_passe");
    }
    if (nouveauMotDePasse !== nouveauMotDePasseConfirmation) {
      return t("erreur_confirmation_mot_de_passe");
    }
    return null;
  }

  async function gererNouveauMotDePasse(e) {
    e.preventDefault();
    setErreur("");

    const erreurLocale = validerNouveauMotDePasseAvantEnvoi();
    if (erreurLocale) {
      setErreur(erreurLocale);
      return;
    }

    setEnCours(true);
    try {
      await apiPost("/auth/reinitialiser-mot-de-passe", {
        email,
        jetonReset,
        nouveauMotDePasse,
        nouveauMotDePasseConfirmation,
        captchaId: captchaRef.current?.captchaId,
        captchaValeur,
      });
      setEtape(3);
    } catch (err) {
      setErreur(err.data?.message || err.message);
      captchaRef.current?.rafraichir();
      setCaptchaValeur("");
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
        <div className="connexion-formulaire">
          {erreur && <div className="erreur-message">{erreur}</div>}
          {!erreur && info && <div className="succes-message">{info}</div>}

          {etape === 0 && (
            <form onSubmit={gererDemandeCode}>
              <h1>{t("reset_titre")}</h1>
              <p className="connexion-formulaire__soustitre">{t("reset_soustitre")}</p>
              <div className="champ">
                <label htmlFor="reset-email">{t("email")}</label>
                <input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : t("bouton_envoyer_code")}
              </button>
              <Link className="lien-secondaire" to="/">{t("retour_connexion")}</Link>
            </form>
          )}

          {etape === 1 && (
            <form onSubmit={gererVerificationCode}>
              <h1>{t("verification_titre")}</h1>
              <p className="connexion-formulaire__soustitre">{t("verification_soustitre", { email })}</p>
              <div className="champ">
                <label htmlFor="reset-code">{t("label_code_verification")}</label>
                <input
                  id="reset-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  maxLength={6}
                  required
                />
              </div>
              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : t("bouton_verifier")}
              </button>
              <button
                type="button"
                className="lien-secondaire"
                onClick={gererRenvoiCode}
                style={{ display: "block", background: "none", border: "none", cursor: "pointer" }}
              >
                {t("bouton_renvoyer_code")}
              </button>
            </form>
          )}

          {etape === 2 && (
            <form onSubmit={gererNouveauMotDePasse}>
              <h1>{t("nouveau_mdp_titre")}</h1>
              <p className="connexion-formulaire__soustitre">{t("nouveau_mdp_soustitre")}</p>

              <ChampMotDePasse
                id="nouveau-mdp"
                label={t("nouveau_mot_de_passe")}
                value={nouveauMotDePasse}
                onChange={(e) => setNouveauMotDePasse(e.target.value)}
                required
                minLength={8}
              />
              <IndicateurForceMotDePasse motDePasse={nouveauMotDePasse} />

              <ChampMotDePasse
                id="nouveau-mdp-confirmation"
                label={t("label_confirmation_mot_de_passe")}
                value={nouveauMotDePasseConfirmation}
                onChange={(e) => setNouveauMotDePasseConfirmation(e.target.value)}
                onPaste={(e) => e.preventDefault()}
                required
              />

              <CaptchaLocal
                ref={captchaRef}
                endpoint="/auth/captcha-reinitialisation"
                valeur={captchaValeur}
                onChangeValeur={setCaptchaValeur}
              />

              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : t("bouton_reinitialiser")}
              </button>
            </form>
          )}

          {etape === 3 && (
            <div className="confirmation-finale">
              <h1>{t("reset_termine_titre")}</h1>
              <p className="connexion-formulaire__soustitre">{t("reset_termine_soustitre")}</p>
              <button className="bouton-principal" onClick={() => navigate("/")}>
                {t("bouton_se_connecter_maintenant")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
