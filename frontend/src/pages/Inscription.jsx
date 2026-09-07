import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";

export default function Inscription() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [nom, setNom] = useState("");
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState(false);
  const [enCours, setEnCours] = useState(false);

  async function gererInscription(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      await apiPost("/auth/register", { nom, email, motDePasse });
      setSucces(true);
      setTimeout(() => navigate("/"), 1500);
    } catch (err) {
      setErreur(err.data?.message || "Une erreur est survenue.");
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
        <form className="connexion-formulaire" onSubmit={gererInscription}>
          <h1>Créer un compte</h1>
          <p className="connexion-formulaire__soustitre">
            Compte Super Administrateur (base centrale, environnement de test)
          </p>

          {erreur && <div className="erreur-message">{erreur}</div>}
          {succes && (
            <div className="succes-message">
              Compte créé avec succès — redirection vers la connexion...
            </div>
          )}

          <div className="champ">
            <label htmlFor="nom">Nom complet</label>
            <input
              id="nom"
              type="text"
              value={nom}
              onChange={(e) => setNom(e.target.value)}
              required
            />
          </div>

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
              autoComplete="new-password"
              minLength={8}
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              required
            />
            <span className="champ__aide">8 caractères minimum</span>
          </div>

          <button className="bouton-principal" type="submit" disabled={enCours || succes}>
            {enCours ? "..." : "Créer le compte"}
          </button>

          <Link className="lien-secondaire" to="/">
            Déjà un compte ? Se connecter
          </Link>
        </form>
      </div>
    </div>
  );
}
