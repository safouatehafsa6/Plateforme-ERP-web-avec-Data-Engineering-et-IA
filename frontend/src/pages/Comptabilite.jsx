import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["05/09/2026", "Vente CMD-2026-014", "Crédit", "12 450 MAD"],
  ["04/09/2026", "Achat ACH-2026-009", "Débit", "5 200 MAD"],
];

export default function Comptabilite() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("comptabilite")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par le
        vrai journal comptable une fois le backend connecté.
      </p>
      <TableModule
        colonnes={["Date", "Libellé", "Type", "Montant"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
