import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import KpiCard from "../components/KpiCard";

export default function TableauDeBord() {
  const { t } = useTranslation();

  return (
    <PageLayout titre={t("tableau_de_bord")}>
      <div className="kpi-grille">
        <KpiCard label={t("chiffre_affaires")} valeur="1 245 670 MAD" variation="18,6%" positif />
        <KpiCard label={t("achats")} valeur="785 430 MAD" variation="12,4%" positif />
        <KpiCard label={t("tresorerie")} valeur="632 250 MAD" variation="3,7%" positif={false} />
        <KpiCard label={t("clients_actifs")} valeur="152" variation="6,2%" positif />
      </div>

      <div className="app-placeholder-zone">
        <p>{t("graphiques_a_venir")}</p>
      </div>
    </PageLayout>
  );
}
