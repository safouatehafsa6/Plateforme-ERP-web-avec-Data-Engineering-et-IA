import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { apiPost } from "../api/config";
import { LANGUES } from "../i18n";
import ReseauDecoratif from "../components/ReseauDecoratif";

export default function Connexion() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  function changerLangue(code, dir) {
    i18n.changeLanguage(code);
    document.documentElement.dir = dir;
    document.documentElement.lang = code;
  }

  async function gererConnexion(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);

    try {
      // Correspond au diagramme de séquence "Routage multi-tenant" :
      // le backend identifie l'entreprise depuis l'email, sélectionne sa
      // base dédiée, puis renvoie un token contenant les rôles.
      const data = await apiPost("/auth/login", { email, motDePasse });
      localStorage.setItem("token", data.token);
      navigate("/dashboard");
    } catch (err) {
      setErreur(t("erreur_identifiants"));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="connexion-layout">
      <aside className="connexion-marque">
        <ReseauDecoratif />
        <div className="connexion-marque__logo">BENJEDDOU ERP</div>
        <div className="connexion-marque__corps">
          <h1 className="connexion-marque__titre">{t("marque_titre")}</h1>
          <p className="connexion-marque__texte">{t("marque_texte")}</p>
        </div>
        <div className="connexion-marque__pied">© 2026 — Plateforme ERP SaaS</div>
      </aside>

      <div className="connexion-formulaire-zone">
        <form className="connexion-formulaire" onSubmit={gererConnexion}>
          <div className="connexion-formulaire__langues">
            {LANGUES.map((langue) => (
              <button
                key={langue.code}
                type="button"
                className="langue-bouton"
                aria-pressed={i18n.language === langue.code}
                onClick={() => changerLangue(langue.code, langue.dir)}
              >
                {langue.nom}
              </button>
            ))}
          </div>

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
