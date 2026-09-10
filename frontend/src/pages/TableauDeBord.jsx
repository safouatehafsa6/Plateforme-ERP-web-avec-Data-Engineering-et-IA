import { useTranslation } from "react-i18next";
import { Search, Bell } from "lucide-react";
import Sidebar from "../components/Sidebar";
import KpiCard from "../components/KpiCard";

export default function TableauDeBord() {
  const { t } = useTranslation();

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
