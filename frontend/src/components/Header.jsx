import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Menu, X, Sun, Moon, Briefcase } from "lucide-react";
import { useLangue } from "../context/LangueContext";
import { useTheme } from "../context/ThemeContext";

const ICONES_THEME = { clair: Sun, sombre: Moon, professionnel: Briefcase };

export default function Header() {
  const { t } = useTranslation();
  const { langueActuelle, changerLangue, langues } = useLangue();
  const { theme, changerTheme, themes } = useTheme();
  const location = useLocation();
  const [menuOuvert, setMenuOuvert] = useState(false);

  // Le Header ne montre pas "Connexion / Inscription" quand on est déjà
  // dans un espace connecté (ex: le tableau de bord).
  const estEspacePublic = location.pathname === "/" || location.pathname === "/inscription";

  return (
    <header className="app-header">
      <div className="app-header__gauche">
        <Link to="/" className="app-header__logo">
          BENJEDDOU ERP
        </Link>
        <nav className="app-header__nav app-header__nav--desktop">
          <a href="#" className="app-header__lien">{t("nav_accueil")}</a>
          <a href="#" className="app-header__lien">{t("nav_fonctionnalites")}</a>
          <a href="#" className="app-header__lien">{t("nav_tarifs")}</a>
        </nav>
      </div>

      <div className="app-header__droite app-header__droite--desktop">
        <div className="app-header__themes">
          {themes.map((th) => {
            const Icone = ICONES_THEME[th.code];
            return (
              <button
                key={th.code}
                type="button"
                className="theme-bouton"
                aria-pressed={theme === th.code}
                onClick={() => changerTheme(th.code)}
                title={th.nom}
                aria-label={th.nom}
              >
                <Icone size={14} strokeWidth={2} />
              </button>
            );
          })}
        </div>

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

      <button
        type="button"
        className="app-header__hamburger"
        onClick={() => setMenuOuvert((v) => !v)}
        aria-label="Menu"
        aria-expanded={menuOuvert}
      >
        {menuOuvert ? <X size={22} /> : <Menu size={22} />}
      </button>

      {menuOuvert && (
        <div className="app-header__menu-mobile">
          <nav className="app-header__nav-mobile">
            <a href="#" className="app-header__lien">{t("nav_accueil")}</a>
            <a href="#" className="app-header__lien">{t("nav_fonctionnalites")}</a>
            <a href="#" className="app-header__lien">{t("nav_tarifs")}</a>
          </nav>

          <div className="app-header__themes">
            {themes.map((th) => {
              const Icone = ICONES_THEME[th.code];
              return (
                <button
                  key={th.code}
                  type="button"
                  className="theme-bouton"
                  aria-pressed={theme === th.code}
                  onClick={() => changerTheme(th.code)}
                  aria-label={th.nom}
                >
                  <Icone size={14} strokeWidth={2} />
                </button>
              );
            })}
          </div>

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
            <div className="app-header__actions app-header__actions--mobile">
              <Link to="/" className="app-header__bouton app-header__bouton--secondaire">
                {t("nav_connexion")}
              </Link>
              <Link to="/inscription" className="app-header__bouton app-header__bouton--primaire">
                {t("nav_inscription")}
              </Link>
            </div>
          )}
        </div>
      )}
    </header>
  );
}
