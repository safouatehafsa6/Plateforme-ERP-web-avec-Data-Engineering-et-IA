import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Search, Bell, AlertTriangle } from "lucide-react";
import Sidebar from "../components/Sidebar";
import KpiCard from "../components/KpiCard";
import { API_BASE_URL } from "../api/config";

export default function TableauDeBord() {
  const { t } = useTranslation();
  const [essaiInfo, setEssaiInfo] = useState(null);
  const [email, setEmail] = useState("");

  useEffect(() => {
    const brut = localStorage.getItem("essaiInfo");
    if (brut) setEssaiInfo(JSON.parse(brut));
    const emailStocke = localStorage.getItem("email");
    if (emailStocke) setEmail(emailStocke);
  }, []);

  const visitesCritiques = essaiInfo && essaiInfo.visitesRestantes <= 5;

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="app-contenu">
        <header className="app-topbar">
          <div className="app-topbar__recherche">
            <Search size={16} strokeWidth={1.75} />
            <input type="text" placeholder={t("rechercher")} />
          </div>
          <div className="app-topbar__droite">
            <Bell size={18} strokeWidth={1.75} />
            <div className="app-topbar__avatar">A</div>
          </div>
        </header>

        <main className="app-main">
          {essaiInfo && !visitesCritiques && (
            <div className="bandeau-essai">
              <AlertTriangle size={16} strokeWidth={1.75} />
              <span>
                Visites restantes : <strong>{essaiInfo.visitesRestantes}</strong> / {essaiInfo.visitesMax}
              </span>
            </div>
          )}

          {essaiInfo && visitesCritiques && (
            <div className="bandeau-essai bandeau-essai--critique">
              <AlertTriangle size={18} strokeWidth={2} />
              <div className="bandeau-essai--critique__contenu">
                <p>
                  <strong>Visites restantes : {essaiInfo.visitesRestantes} / {essaiInfo.visitesMax}.</strong>{" "}
                  Votre période d'essai se termine bientôt. Souscrivez un
                  abonnement dès maintenant pour continuer à utiliser la
                  plateforme sans interruption. À l'expiration, votre compte
                  sera désactivé et l'accès à votre espace sera bloqué —
                  vos données resteront toutefois conservées et exportables.
                </p>
                <div className="bandeau-essai--critique__actions">
                  <Link className="bouton-principal" to={`/abonnement?email=${encodeURIComponent(email)}`}>
                    S'abonner maintenant
                  </Link>
                  <a
                    className="bouton-secondaire-large"
                    href={`${API_BASE_URL}/entreprises/export-donnees?email=${encodeURIComponent(email)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Exporter toutes mes données
                  </a>
                </div>
              </div>
            </div>
          )}

          <h1 className="app-main__titre">{t("tableau_de_bord")}</h1>

          <div className="kpi-grille">
            <KpiCard label={t("chiffre_affaires")} valeur="1 245 670 MAD" variation="18,6%" positif />
            <KpiCard label={t("achats")} valeur="785 430 MAD" variation="12,4%" positif />
            <KpiCard label={t("tresorerie")} valeur="632 250 MAD" variation="3,7%" positif={false} />
            <KpiCard label={t("clients_actifs")} valeur="152" variation="6,2%" positif />
          </div>

          <div className="app-placeholder-zone">
            <p>{t("graphiques_a_venir")}</p>
          </div>
        </main>
      </div>
    </div>
  );
}
