import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["CMD-2026-014", "STE Sonatrach", "05/09/2026", "confirmée", "12 450 MAD"],
  ["CMD-2026-013", "Enem SPA", "04/09/2026", "en cours", "8 900 MAD"],
  ["CMD-2026-012", "Sarl Building", "03/09/2026", "livrée", "21 300 MAD"],
];

export default function Ventes() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("ventes")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par les
        vraies commandes une fois le backend connecté (semaine prochaine).
      </p>
      <TableModule
        colonnes={["Référence", "Client", "Date", "Statut", "Montant"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
