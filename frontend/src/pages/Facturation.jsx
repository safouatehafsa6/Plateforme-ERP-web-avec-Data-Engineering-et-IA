import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["FAC-2026-0031", "STE Sonatrach", "05/09/2026", "payée", "12 450 MAD"],
  ["FAC-2026-0030", "Enem SPA", "04/09/2026", "impayée", "8 900 MAD"],
];

export default function Facturation() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("facturation")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par les
        vraies factures une fois le backend connecté.
      </p>
      <TableModule
        colonnes={["Numéro", "Client", "Date", "Statut", "Montant"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
