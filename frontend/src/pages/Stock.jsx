import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["PRD-0021", "Écran 24 pouces", "43", "En stock"],
  ["PRD-0022", "Clavier sans fil", "6", "Stock faible"],
  ["PRD-0023", "Souris optique", "0", "Rupture"],
];

export default function Stock() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("stock")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par le
        vrai inventaire une fois le backend connecté.
      </p>
      <TableModule
        colonnes={["Référence", "Produit", "Quantité", "État"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
