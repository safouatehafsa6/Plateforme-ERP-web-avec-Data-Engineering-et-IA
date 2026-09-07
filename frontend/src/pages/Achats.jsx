import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["ACH-2026-009", "Fournisseur Alpha", "02/09/2026", "réceptionné", "5 200 MAD"],
  ["ACH-2026-008", "Fournisseur Beta", "30/08/2026", "en cours", "14 800 MAD"],
];

export default function Achats() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("achats")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par les
        vraies commandes fournisseur une fois le backend connecté.
      </p>
      <TableModule
        colonnes={["Référence", "Fournisseur", "Date", "Statut", "Montant"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
