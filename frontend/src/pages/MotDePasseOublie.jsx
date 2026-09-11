import { useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";
import CaptchaLocal from "../components/CaptchaLocal";
import ChampMotDePasse from "../components/ChampMotDePasse";
import IndicateurForceMotDePasse from "../components/IndicateurForceMotDePasse";

export default function MotDePasseOublie() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const captchaRef = useRef(null);

  const [etape, setEtape] = useState(1); // 1 = email, 2 = code, 3 = nouveau mot de passe, 4 = fini
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [nouveauMotDePasse, setNouveauMotDePasse] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [captchaValeur, setCaptchaValeur] = useState("");
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [enCours, setEnCours] = useState(false);

  async function gererDemandeCode(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      const data = await apiPost("/auth/mot-de-passe-oublie", { email });
      setMessage(data.message);
      setEtape(2);
    } catch (err) {
      setErreur(err.data?.message || "Une erreur est survenue.");
    } finally {
      setEnCours(false);
    }
  }

  async function gererVerificationCode(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      await apiPost("/auth/verifier-code-reinitialisation", { email, code });
      setEtape(3);
    } catch (err) {
      setErreur(err.data?.message || "Code incorrect.");
    } finally {
      setEnCours(false);
    }
  }

  async function gererNouveauMotDePasse(e) {
    e.preventDefault();
    setErreur("");

    if (nouveauMotDePasse !== confirmation) {
      setErreur("Les deux mots de passe ne correspondent pas.");
      return;
    }

    setEnCours(true);
    try {
      await apiPost("/auth/reinitialiser-mot-de-passe", {
        email,
        nouveauMotDePasse,
        nouveauMotDePasseConfirmation: confirmation,
        captchaId: captchaRef.current?.captchaId,
        captchaValeur,
      });
      setEtape(4);
      setTimeout(() => navigate("/"), 1500);
    } catch (err) {
      setErreur(err.data?.message || "Une erreur est survenue.");
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
          <h1 className="connexion-marque__titre">Mot de passe oublié</h1>
          <p className="connexion-marque__texte">
            Récupérez l'accès à votre compte en toute sécurité, en trois étapes simples.
          </p>
        </div>
        <div className="connexion-marque__pied">© 2026 — Plateforme ERP SaaS</div>
      </aside>

      <div className="connexion-formulaire-zone">
        <div className="connexion-formulaire">
          {erreur && <div className="erreur-message">{erreur}</div>}
          {message && etape === 2 && <div className="succes-message">{message}</div>}

          {etape === 1 && (
            <form onSubmit={gererDemandeCode}>
              <h1>Réinitialiser le mot de passe</h1>
              <p className="connexion-formulaire__soustitre">
                Saisissez l'adresse email associée à votre compte. Un code de
                vérification vous sera envoyé.
              </p>
              <div className="champ">
                <label htmlFor="email">{t("email")}</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : "Envoyer le code"}
              </button>
              <Link className="lien-secondaire" to="/">Retour à la connexion</Link>
            </form>
          )}

          {etape === 2 && (
            <form onSubmit={gererVerificationCode}>
              <h1>Code de vérification</h1>
              <p className="connexion-formulaire__soustitre">
                Saisissez le code à 6 chiffres reçu par email.
              </p>
              <div className="champ">
                <label htmlFor="code">Code</label>
                <input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  required
                  style={{ letterSpacing: "0.4em", textAlign: "center", fontSize: "1.2rem" }}
                />
              </div>
              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : "Vérifier le code"}
              </button>
            </form>
          )}

          {etape === 3 && (
            <form onSubmit={gererNouveauMotDePasse}>
              <h1>Nouveau mot de passe</h1>
              <p className="connexion-formulaire__soustitre">
                Choisissez un nouveau mot de passe, soumis aux mêmes règles de
                sécurité qu'à l'inscription.
              </p>
              <div className="champ">
                <label>Nouveau mot de passe</label>
                <ChampMotDePasse
                  value={nouveauMotDePasse}
                  onChange={(e) => setNouveauMotDePasse(e.target.value)}
                  required
                  minLength={8}
                />
                <IndicateurForceMotDePasse motDePasse={nouveauMotDePasse} />
              </div>
              <div className="champ">
                <label>Confirmation du mot de passe</label>
                <ChampMotDePasse
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  onPaste={(e) => e.preventDefault()}
                  required
                />
              </div>

              <CaptchaLocal
                ref={captchaRef}
                endpoint="/auth/captcha"
                valeur={captchaValeur}
                onChangeValeur={setCaptchaValeur}
              />

              <button className="bouton-principal" type="submit" disabled={enCours}>
                {enCours ? "..." : "Réinitialiser le mot de passe"}
              </button>
            </form>
          )}

          {etape === 4 && (
            <div className="confirmation-finale">
              <h1>Mot de passe mis à jour</h1>
              <p className="connexion-formulaire__soustitre">
                Redirection vers la page de connexion...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
