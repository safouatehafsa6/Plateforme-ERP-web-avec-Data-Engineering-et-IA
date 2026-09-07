import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLangue } from "../context/LangueContext";

export default function Header() {
  const { t } = useTranslation();
  const { langueActuelle, changerLangue, langues } = useLangue();
  const location = useLocation();

  // Le Header ne montre pas "Connexion / Inscription" quand on est déjà
  // dans un espace connecté (ex: le tableau de bord).
  const estEspacePublic = location.pathname === "/" || location.pathname === "/inscription";

  return (
    <header className="app-header">
      <div className="app-header__gauche">
        <Link to="/" className="app-header__logo">
          BENJEDDOU ERP
        </Link>
        <nav className="app-header__nav">
          <a href="#" className="app-header__lien">{t("nav_accueil")}</a>
          <a href="#" className="app-header__lien">{t("nav_fonctionnalites")}</a>
          <a href="#" className="app-header__lien">{t("nav_tarifs")}</a>
        </nav>
      </div>

      <div className="app-header__droite">
        <div className="app-header__langues">
          {langues.map((langue) => (
            <button
              key={langue.code}
              type="button"
              className="langue-bouton langue-bouton--header"
              aria-pressed={langueActuelle.code === langue.code}
              onClick={() => changerLangue(langue.code)}
            >
              {langue.code.toUpperCase()}
            </button>
          ))}
        </div>

        {estEspacePublic && (
          <div className="app-header__actions">
            <Link to="/" className="app-header__bouton app-header__bouton--secondaire">
              {t("nav_connexion")}
            </Link>
            <Link to="/inscription" className="app-header__bouton app-header__bouton--primaire">
              {t("nav_inscription")}
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
